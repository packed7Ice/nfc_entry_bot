# NFC Entry Bot

Sony RC-S380 / RC-S956 NFC リーダーでタグを読み取り、入退室状態を管理しながら Discord へリアルタイム通知を送る Windows 向けアプリケーションです。未登録タグをタッチすると Discord OAuth2 によるセルフ登録フローが起動し、ユーザーが自分で紐づけを完了できます。

---

## 目的

- NFC カード（交通系 IC・FeliCa カード等）を物理キーとして利用し、入退室を自動記録する
- Discord webhook でリアルタイムにチームへ通知する
- 管理者不要のセルフ登録で運用コストを下げる

---

## 機能一覧

| 機能 | 説明 |
|------|------|
| NFC タグ読み取り | FeliCa (IDm) / 標準 RFID (UID) を自動判別 |
| 入退室トグル | タッチごとに IN/OUT を切り替え。一定時間後に自動リセット |
| Discord 通知 | webhook 経由でユーザーメンション付き入退室メッセージを送信 |
| セルフ登録 | 未登録タグ検出時にブラウザを起動し、Discord OAuth2 で自動登録 |
| Web ダッシュボード | Flask 製のリアルタイム UI（SSE によるプッシュ更新） |
| ログ記録 | CSV 形式のエントリログを 6 時間ローテーションで保存 |
| クールダウン | 同一タグの連続タッチによる重複送信を防止 |

---

## システム構成

```
┌─────────────────────────────────────────────────────┐
│  Windows PC                                         │
│                                                     │
│  ┌──────────────┐   NFC タッチ   ┌──────────────┐  │
│  │  NFC Reader  │ ─────────────> │  app.py      │  │
│  │ (RC-S380/    │                │  メインループ │  │
│  │  RC-S956)    │                └──────┬───────┘  │
│  └──────────────┘                       │           │
│                                  ┌──────┴───────┐  │
│                            ┌─────┤  registry.py │  │
│                            │     │  users.json  │  │
│                            │     └──────────────┘  │
│                            │                        │
│                     ┌──────┴───────┐               │
│                     │  notifier.py │               │
│                     │  webhook 送信 │               │
│                     └──────┬───────┘               │
│                            │                        │
│                     ┌──────┴───────┐               │
│                     │  web_app.py  │               │
│                     │  Flask + SSE │               │
│                     └──────────────┘               │
└─────────────────────────────────────────────────────┘
         │ Discord webhook          │ OAuth2
         ▼                         ▼
    Discord サーバー           Discord API
```

アプリケーションは 2 つのスレッドで動作します。

- **NFC 監視スレッド**: NFC リーダーを常時ポーリングし、タグを検出するとイベントを処理する
- **Flask サーバー（メインスレッド）**: Web ダッシュボードと OAuth2 コールバックを提供する

---

## 使用技術

| カテゴリ | 技術 |
|----------|------|
| 言語 | Python 3.11+ |
| NFC インターフェース | nfcpy >= 1.0.4 |
| Web フレームワーク | Flask >= 3.0.0 |
| HTTP クライアント | requests >= 2.31.0 |
| 設定管理 | python-dotenv >= 1.0.0 |
| リアルタイム通信 | Server-Sent Events (SSE) |
| 認証 | Discord OAuth2 (scope: identify) |
| ストレージ | JSON ファイル (users.json) |
| ログ | TimedRotatingFileHandler (6h ローテーション) |

---

## ハードウェア要件

- **NFC リーダー**: Sony RC-S380 または RC-S956 (USB 接続)
- **OS**: Windows 10 / 11
- **ドライバー**: WinUSB（Zadig で置き換え済みであること）
- **libusb**: `libusb-1.0.dll` がシステムに配置済みであること

---

## セットアップ

### 1. WinUSB ドライバーへの置き換え

nfcpy は標準の Sony ドライバーでは動作しないため、WinUSB へ置き換えます。

1. [Zadig](https://zadig.akeo.ie/) をダウンロード・実行
2. `Options` → `List All Devices` を有効化
3. ドロップダウンから Sony RC-S380（または RC-S956）を選択
4. 右側のドライバーを **WinUSB** に設定し、**Replace Driver** をクリック

> WinUSB に置き換えると、Sony 公式ソフト（e-Tax 等）では使えなくなります。元に戻すには、デバイスマネージャーから WinUSB をアンインストールし、公式ドライバーを再インストールしてください。

### 2. libusb の配置

1. [libusb](https://libusb.info/) から最新の Windows バイナリをダウンロード
2. 64bit 環境:
   - `MS64\dll\libusb-1.0.dll` → `C:\Windows\System32`
   - `MS32\dll\libusb-1.0.dll` → `C:\Windows\SysWOW64`

### 3. Discord アプリケーションの作成

OAuth2 セルフ登録機能を使う場合は Discord Developer Portal での設定が必要です。

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを作成
2. **OAuth2** タブ → **Client ID** と **Client Secret** を控える
3. **Redirects** に `http://127.0.0.1:5000/callback` を追加
4. **webhook**: 通知先サーバーのチャンネルで webhook URL を作成して控える

### 4. Python 環境の構築

```powershell
cd nfc_discord_app
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5. 設定ファイルの準備

#### `.env` の作成

```powershell
copy .env.example .env
```

`.env` を編集して各値を設定します（設定一覧は後述）。

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
DISCORD_CLIENT_ID=123456789012345678
DISCORD_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxx
FLASK_SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))"> の出力値
```

#### `users.json` の作成

```powershell
copy users.json.example users.json
```

初回はファイルを空のオブジェクトで作成しても構いません。

```json
{}
```

登録済みユーザーは以下の形式で管理されます。

```json
{
  "0123456789ABCDEF": {
    "name": "山田 太郎",
    "discord_user_id": "123456789012345678"
  }
}
```

| フィールド | 説明 |
|-----------|------|
| キー（タグ ID） | 大文字16進数、区切り文字なし |
| `name` | 表示名（Discord の global_name を自動取得） |
| `discord_user_id` | Discord ユーザー ID（メンションに使用） |

---

## 起動

```powershell
cd nfc_discord_app
.\venv\Scripts\Activate.ps1
python app.py
```

起動後、ブラウザで `http://127.0.0.1:5000` を開くとダッシュボードが表示されます。`Ctrl+C` で終了します。

### 起動ログの例

```
2026-05-14 10:00:00 [INFO] __main__: === NFC Discord Notifier (Web UI) starting ===
2026-05-14 10:00:00 [INFO] registry: Loaded 3 user(s) from users.json
2026-05-14 10:00:01 [INFO] nfc_reader: NFC reader opened: usb:054c:06c1
2026-05-14 10:00:01 [INFO] __main__: Starting Flask server on http://127.0.0.1:5000
2026-05-14 10:00:01 [INFO] __main__: Watching for NFC tags (cooldown=5s, state reset=12h).
2026-05-14 10:00:10 [INFO] __main__: NFC tag detected: 0123456789ABCDEF
2026-05-14 10:00:10 [INFO] __main__: 入室: 山田 太郎 (0123456789ABCDEF)
2026-05-14 10:00:10 [INFO] notifier: Discord notification sent successfully
```

---

## 動作フロー

### 登録済みユーザーのタッチ

```
NFC タグ検出
    │
    ├─ クールダウン中? → スキップ
    │
    ├─ users.json で検索
    │
    ├─ 状態トグル (OUT → IN, または IN → OUT)
    │   ※ 最終タッチから STATE_RESET_HOURS 以上経過した場合は OUT にリセット
    │
    ├─ Discord webhook に通知
    │   例: <@123456789012345678> 入室しました
    │
    ├─ SSE イベント送信 (type: "touch")
    │
    └─ CSV ログ記録
```

### 未登録タグのタッチ

```
NFC タグ検出 → users.json に未登録
    │
    ├─ SSE イベント送信 (type: "unregistered")
    │   → ダッシュボードに登録プロンプトを表示
    │
    └─ Microsoft Edge (InPrivate) で登録 URL を起動
           │
           └─ /register_start?tag_id=XXXX
                   │
                   └─ Discord OAuth2 認証画面へリダイレクト
                           │
                           └─ /callback (コールバック)
                                   │
                                   ├─ state 検証 (CSRF 対策)
                                   ├─ アクセストークン取得
                                   ├─ Discord ユーザー情報取得
                                   ├─ users.json に保存
                                   ├─ SSE イベント送信 (type: "registered")
                                   └─ success.html 表示 (3 秒後に自動クローズ)
```

---

## 設定一覧

| 環境変数 | 説明 | デフォルト |
|----------|------|-----------|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL（必須） | — |
| `DISCORD_CLIENT_ID` | OAuth2 クライアント ID | — |
| `DISCORD_CLIENT_SECRET` | OAuth2 クライアントシークレット | — |
| `FLASK_SECRET_KEY` | セッション暗号化キー（必須・要変更） | `default-dev-secret-key` |
| `COOLDOWN_SECONDS` | 同一タグの再送防止秒数 | `5` |
| `STATE_RESET_HOURS` | 入室状態の自動リセット時間（時） | `12` |
| `NFC_READER_PATH` | nfcpy デバイスパス（カンマ区切りで複数指定可） | `usb:054c:06c1,usb:054c:0dc8` |
| `WEBHOOK_TIMEOUT_SECONDS` | HTTP タイムアウト（秒） | `10` |
| `LOG_LEVEL` | ログレベル (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `SERVER_HOST` | Flask バインドアドレス | `127.0.0.1` |
| `SERVER_PORT` | Flask ポート番号 | `5000` |

`NFC_READER_PATH` の主な値:

| NFC リーダー | デバイスパス |
|-------------|-------------|
| Sony RC-S380 | `usb:054c:06c1` |
| Sony RC-S956 | `usb:054c:0dc8` |
| 自動検出 | `usb` |

---

## Discord 通知メッセージ仕様

送信メッセージは以下の優先順位で決定されます。

| 条件 | メッセージ例 |
|------|-------------|
| `discord_user_id` あり + 入室 | `<@123456789012345678> 入室しました` |
| `discord_user_id` あり + 退室 | `<@123456789012345678> 退室しました` |
| `discord_user_id` なし、`name` あり | `山田 太郎 入室しました` |
| 両方なし | `登録済みユーザーが NFC をタッチしました (入室)` |

---

## SSE イベント仕様

`GET /stream` エンドポイントが Server-Sent Events を配信します。フロントエンドはこのストリームを購読してリアルタイムに UI を更新します。

| イベント type | データ | タイミング |
|--------------|--------|-----------|
| `touch` | `{tag_id, name, direction}` | 登録済みユーザーのタッチ時 |
| `unregistered` | `{tag_id}` | 未登録タグ検出時 |
| `registered` | `{tag_id, name}` | OAuth2 登録完了時 |
| `register_failed` | `{message}` | OAuth2 登録失敗時 |

接続維持のため 20 秒ごとにキープアライブコメント (`: keepalive`) を送信します。

---

## ログ仕様

### コンソールログ

```
YYYY-MM-DD HH:MM:SS [LEVEL] モジュール名: メッセージ
```

### エントリログ (`logs/entry_history.log`)

CSV 形式で入退室イベントを記録します。

```
2026-05-14 10:00:10,入室,山田 太郎,0123456789ABCDEF
2026-05-14 18:30:00,退室,山田 太郎,0123456789ABCDEF
```

- 6 時間ごとにローテーション
- 過去 30 世代保持（約 1 週間分）
- UTF-8 エンコード

---

## ディレクトリ構成

```
nfc_entry_bot/
├── README.md
├── .gitignore
└── nfc_discord_app/
    ├── app.py              # エントリーポイント・NFC 監視ループ・Flask 起動
    ├── config.py           # 設定読込・ログ設定・バリデーション
    ├── nfc_reader.py       # NFC リーダー制御 (nfcpy ラッパー)
    ├── notifier.py         # Discord webhook 送信
    ├── registry.py         # ユーザー登録情報の CRUD (users.json)
    ├── web_app.py          # Flask アプリ・SSE・OAuth2 コールバック
    ├── requirements.txt    # Python 依存パッケージ
    ├── .env.example        # 環境変数テンプレート
    ├── users.json.example  # ユーザー登録データのサンプル
    ├── logs/               # エントリログ（実行時に自動生成）
    └── templates/
        ├── index.html      # ダッシュボード（待機画面・登録プロンプト）
        ├── success.html    # 登録成功ページ（3 秒後に自動クローズ）
        └── error.html      # エラーページ（3 秒後に自動クローズ）
```

---

## セキュリティ

- OAuth2 の `state` パラメータによる CSRF 対策
- `FLASK_SECRET_KEY` による Flask セッションの暗号化
- subprocess をリスト渡し (`shell=False`) でコマンドインジェクションを防止
- `.env` / `users.json` / `logs/` は `.gitignore` で管理対象外
- webhook URL はログ・レスポンスに出力しない

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `Failed to open NFC reader` | Zadig でドライバーが WinUSB になっているか確認。デバイスが接続されているか確認 |
| `nfcpy is not installed` | `pip install nfcpy` を実行。仮想環境が有効か確認 |
| `DISCORD_WEBHOOK_URL is not set` | `.env` が存在し、URL が正しく設定されているか確認 |
| `Discord webhook returned HTTP 4xx` | webhook URL が正しいか、webhook が削除されていないか確認 |
| `users.json not found` | `users.json` が `nfc_discord_app/` ディレクトリに存在するか確認 |
| `FLASK_SECRET_KEY は既定値のまま` | `.env` に強力な秘密鍵を設定する（`python -c "import secrets; print(secrets.token_hex(32))"` で生成） |
| OAuth2 登録が完了しない | `.env` の `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` と、Developer Portal の Redirect URI を確認 |
| タグを読み取らない | RC-S956 の場合はデバイスマネージャーでハードウェア ID を確認し、`NFC_READER_PATH` を修正する |

---

## 既知の制約

- **nfcpy の Windows 対応**: nfcpy は主に Linux 向けに開発されています。Windows では WinUSB + libusb の構成で動作しますが、環境によって不安定になる場合があります。
- **MIFARE Classic**: RC-S380 は MIFARE Classic の暗号化領域を読めません。UID の取得は可能です。
- **FeliCa**: FeliCa カードの場合は IDm が識別子として使用されます。
- **ドライバー排他**: WinUSB ドライバーに置き換えると、e-Tax・モバイル Suica チャージなど Sony 公式ソフトは使えなくなります。
- **ブラウザ**: 未登録タグ検出時の自動起動は Microsoft Edge (InPrivate) 固定です。
- **シングルホスト**: Flask サーバーはデフォルトでループバックアドレス (`127.0.0.1`) のみでリッスンします。
