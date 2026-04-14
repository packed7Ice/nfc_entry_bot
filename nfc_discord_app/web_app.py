import queue
import json
import requests
from flask import Flask, request, redirect, session, url_for, render_template, Response

from config import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, FLASK_SECRET_KEY, get_logger

logger = get_logger(__name__)

class EventManager:
    """Manages SSE subscribers and broadcasts events."""
    def __init__(self):
        self.listeners = []
        
    def subscribe(self):
        q = queue.Queue(maxsize=10)
        self.listeners.append(q)
        return q
        
    def emit(self, event_type: str, data: dict):
        for q in self.listeners:
            try:
                q.put_nowait({"type": event_type, "data": data})
            except queue.Full:
                pass

# Global events instance
events = EventManager()

def create_app(registry):
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY

    # OAuth2 Settings
    AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
    TOKEN_URL = "https://discord.com/api/oauth2/token"
    USER_API = "https://discord.com/api/users/@me"

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/stream")
    def stream():
        def event_stream():
            q = events.subscribe()
            try:
                while True:
                    event = q.get()
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                if q in events.listeners:
                    events.listeners.remove(q)
        return Response(event_stream(), content_type="text/event-stream")

    @app.route("/register_start")
    def register_start():
        tag_id = request.args.get("tag_id")
        if not tag_id:
            return "Missing tag_id", 400
        
        if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
            return "Discord OAuth2 クレデンシャルが .env に設定されていません。", 500
        
        redirect_uri = url_for("callback", _external=True)
        session["register_tag_id"] = tag_id

        discord_url = (
            f"{AUTHORIZE_URL}?client_id={DISCORD_CLIENT_ID}"
            f"&redirect_uri={requests.utils.quote(redirect_uri)}"
            f"&response_type=code&scope=identify"
        )
        return redirect(discord_url)

    @app.route("/callback")
    def callback():
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
            "redirect_uri": redirect_uri
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        r = requests.post(TOKEN_URL, data=data, headers=headers)
        if not r.ok:
            msg = f"アクセストークンの取得に失敗しました: {r.text}"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500
        
        token = r.json().get("access_token")
        
        r_user = requests.get(USER_API, headers={"Authorization": f"Bearer {token}"})
        if not r_user.ok:
            msg = "ユーザー情報の取得に失敗しました"
            events.emit("register_failed", {"message": msg})
            return render_template("error.html", message=msg), 500
            
        user_info = r_user.json()
        discord_user_id = user_info["id"]
        name = user_info.get("global_name") or user_info.get("username")

        registry.add_user(tag_id, name, discord_user_id)
        session.pop("register_tag_id", None)
        
        # 通知
        events.emit("registered", {"tag_id": tag_id, "name": name})

        return render_template("success.html", name=name)

    return app
