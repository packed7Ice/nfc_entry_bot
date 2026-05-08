import json
import queue
import secrets
import threading

import requests
from flask import Flask, Response, redirect, render_template, request, session, url_for

from config import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    FLASK_SECRET_KEY,
    WEBHOOK_TIMEOUT_SECONDS,
    get_logger,
)

logger = get_logger(__name__)

AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_API = "https://discord.com/api/users/@me"


class EventManager:
    """Manages SSE subscribers and broadcasts events. Thread-safe."""

    def __init__(self) -> None:
        self._listeners: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> "queue.Queue[dict]":
        q: queue.Queue[dict] = queue.Queue(maxsize=10)
        with self._lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict]") -> None:
        with self._lock:
            try:
                self._listeners.remove(q)
            except ValueError:
                pass

    def emit(self, event_type: str, data: dict) -> None:
        with self._lock:
            snapshot = list(self._listeners)
        for q in snapshot:
            try:
                q.put_nowait({"type": event_type, "data": data})
            except queue.Full:
                pass


# Global events instance
events = EventManager()


def create_app(registry) -> Flask:
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/stream")
    def stream():
        def event_stream():
            q = events.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=20)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        # キープアライブ: クライアントの切断検知とタイムアウト防止
                        yield ": keepalive\n\n"
            except GeneratorExit:
                pass
            finally:
                events.unsubscribe(q)

        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        return Response(event_stream(), content_type="text/event-stream", headers=headers)

    @app.route("/register_start")
    def register_start():
        tag_id = request.args.get("tag_id")
        if not tag_id:
            return "Missing tag_id", 400

        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            return "Discord OAuth2 クレデンシャルが .env に設定されていません。", 500

        redirect_uri = url_for("callback", _external=True)
        state = secrets.token_urlsafe(16)
        session["register_tag_id"] = tag_id
        session["oauth_state"] = state

        discord_url = (
            f"{AUTHORIZE_URL}?client_id={DISCORD_CLIENT_ID}"
            f"&redirect_uri={requests.utils.quote(redirect_uri)}"
            f"&response_type=code&scope=identify"
            f"&state={state}"
        )
        return redirect(discord_url)

    @app.route("/callback")
    def callback():
        # CSRF: state パラメータを検証
        expected_state = session.get("oauth_state")
        received_state = request.args.get("state")
        if not expected_state or expected_state != received_state:
            msg = "不正なリクエストです（state 不一致）。もう一度タグをタッチしてください。"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 400
        session.pop("oauth_state", None)

        tag_id = session.get("register_tag_id")
        if not tag_id:
            msg = "登録セッションの有効期限が切れています。もう一度タグをタッチしてください"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 400

        code = request.args.get("code")
        if not code:
            msg = "認証がキャンセルされました"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 400

        redirect_uri = url_for("callback", _external=True)

        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            r = requests.post(TOKEN_URL, data=data, headers=headers, timeout=WEBHOOK_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            msg = f"アクセストークンの取得中にエラーが発生しました: {exc}"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        if not r.ok:
            msg = f"アクセストークンの取得に失敗しました: {r.text[:200]}"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        token = r.json().get("access_token")
        if not token:
            msg = "アクセストークンが取得できませんでした"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        try:
            r_user = requests.get(
                USER_API,
                headers={"Authorization": f"Bearer {token}"},
                timeout=WEBHOOK_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            msg = f"ユーザー情報の取得中にエラーが発生しました: {exc}"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        if not r_user.ok:
            msg = "ユーザー情報の取得に失敗しました"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        user_info = r_user.json()
        discord_user_id = user_info.get("id")
        if not discord_user_id:
            msg = "Discord ユーザー ID の取得に失敗しました"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500

        name = user_info.get("global_name") or user_info.get("username", "")

        registry.add_user(tag_id, name, discord_user_id)
        session.pop("register_tag_id", None)

        events.emit("registered", {"tag_id": tag_id, "name": name})

        return render_template("success.html", name=name)

    @app.route("/register_cancel", methods=["POST"])
    def register_cancel():
        session.pop("register_tag_id", None)
        session.pop("oauth_state", None)
        return "", 204

    return app
