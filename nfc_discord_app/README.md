# NFC Discord Notifier

Sony RC-S380 で NFC タグを読み取り、登録情報に基づいて Discord webhook に通知を送るコマンドラインアプリケーションです。

## 動作概要

1. RC-S380 に NFC タグ/カードをタッチ
2. 識別子（IDm / UID）を取得
3. `users.json` から対応するユーザーを検索
4. 登録済みなら Discord webhook にメッセージを送信
5. 未登録ならコンソールに警告表示
6. 同じタグの連続タッチはクールダウンでスキップ

## 前提条件

- **OS**: Windows 10 / 11
- **Python**: 3.11 以上
- **NFC リーダー**: Sony RC-S380
- **ドライバー**: WinUSB（Zadig で置き換え済みであること）
- **libusb**: `libusb-1.0.dll` がシステムに配置済みであること

## セットアップ

### 1. ドライバーの準備

nfcpy は標準の Sony ドライバーでは動作しません。以下の手順で WinUSB ドライバーに置き換える必要があります。

#### Zadig によるドライバー置き換え

1. [Zadig](https://zadig.akeo.ie/) をダウンロード・実行
2. `Options` → `List All Devices` を有効化
3. ドロップダウンから Sony RC-S380 を選択
4. 右側のドライバーを **WinUSB** に設定
5. **Replace Driver** をクリック

> ⚠️ WinUSB に置き換えると、Sony 公式ソフト（e-Tax 等）では使えなくなります。
> 元に戻すには、デバイスマネージャーから WinUSB をアンインストールし、公式ドライバーを再インストールしてください。

#### libusb の配置

1. [libusb](https://libusb.info/) から最新の Windows バイナリをダウンロード
2. 64bit 環境の場合:
   - `MS64\dll\libusb-1.0.dll` → `C:\Windows\System32`
   - `MS32\dll\libusb-1.0.dll` → `C:\Windows\SysWOW64`

### 2. Python 環境の構築

```powershell
cd nfc_discord_app
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 設定ファイルの準備

#### `.env` の作成

```powershell
copy .env.example .env
```

`.env` を開いて `DISCORD_WEBHOOK_URL` に実際の webhook URL を設定してください。

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
COOLDOWN_SECONDS=5
```

#### `users.json` の編集

NFC タグの識別子とユーザー情報を対応付けます。

```json
{
  "0123456789ABCDEF": {
    "name": "Taro Yamada",
    "discord_user_id": "123456789012345678",
    "message": "打刻しました"
  }
}
```

- **キー**: NFC タグの識別子（大文字16進数。区切り文字なし）
- **name**: 表示名
- **discord_user_id**: Discord のユーザー ID（メンションに使用。空文字なら name で送信）
- **message**: 送信メッセージ本文

> 💡 タグの識別子が不明な場合は、先にアプリを起動して適当なタグをタッチしてください。
> コンソールに `Unregistered tag: XXXX` と表示されるので、その値をキーとして登録できます。

## 実行

```powershell
cd nfc_discord_app
.\venv\Scripts\Activate.ps1
python app.py
```

起動すると NFC タグの待ち受けが始まります。`Ctrl+C` で終了できます。

### 出力例

```
2026-04-14 18:50:00 [INFO] __main__: === NFC Discord Notifier starting ===
2026-04-14 18:50:00 [INFO] registry: Loaded 2 user(s) from users.json
2026-04-14 18:50:01 [INFO] nfc_reader: NFC reader opened: ...
2026-04-14 18:50:01 [INFO] __main__: Watching for NFC tags (cooldown=5s). Press Ctrl+C to stop.
2026-04-14 18:50:05 [INFO] __main__: NFC tag detected: 0123456789ABCDEF
2026-04-14 18:50:05 [INFO] __main__: Registered user: Taro Yamada
2026-04-14 18:50:05 [INFO] notifier: Discord notification sent successfully
2026-04-14 18:50:07 [INFO] __main__: NFC tag detected: 0123456789ABCDEF
2026-04-14 18:50:07 [INFO] __main__: Cooldown active for 0123456789ABCDEF — skipping
2026-04-14 18:50:12 [WARNING] __main__: Unregistered tag: AAAAAAAAAAAAAAAA
```

## メッセージ生成ルール

送信される Discord メッセージは以下の優先順位で決定されます:

| 条件 | メッセージ例 |
|---|---|
| `discord_user_id` あり | `<@123456789012345678> 打刻しました` |
| `discord_user_id` なし、`name` あり | `Taro Yamada 打刻しました` |
| 両方なし | `登録済みユーザーがNFCをタッチしました` |

## 設定一覧

| 環境変数 | 説明 | デフォルト |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL（必須） | — |
| `COOLDOWN_SECONDS` | 同一タグの再送防止秒数 | `5` |
| `NFC_READER_PATH` | nfcpy デバイスパス | `usb:054c:06c1` |
| `WEBHOOK_TIMEOUT_SECONDS` | HTTP タイムアウト | `10` |
| `LOG_LEVEL` | ログレベル | `INFO` |

## ディレクトリ構成

```
nfc_discord_app/
├── app.py              # エントリーポイント・メインループ
├── config.py           # 設定読込・定数管理
├── nfc_reader.py       # NFC 読取
├── notifier.py         # Discord webhook 送信
├── registry.py         # ユーザー登録情報管理
├── users.json          # ユーザー登録データ
├── .env                # 環境変数（git 管理外）
├── .env.example        # .env のテンプレート
├── requirements.txt    # 依存パッケージ
└── README.md
```

## 既知の制約・注意事項

- **nfcpy の Windows 対応**: nfcpy は主に Linux 向けに開発されています。Windows では WinUSB + libusb の構成で動作しますが、環境によっては不安定になる場合があります。
- **MIFARE Classic**: RC-S380 は MIFARE Classic の暗号化領域を読めません。UID の取得は可能です。
- **FeliCa**: FeliCa カードの場合は IDm が識別子として使用されます。
- **ドライバー排他**: WinUSB ドライバーに置き換えると、e-Tax やモバイル Suica チャージなど Sony 公式ソフトは使えなくなります。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `Failed to open NFC reader` | Zadig でドライバーが WinUSB になっているか確認。RC-S380 が接続されているか確認 |
| `nfcpy is not installed` | `pip install nfcpy` を実行。仮想環境が有効か確認 |
| `DISCORD_WEBHOOK_URL is not set` | `.env` ファイルが存在し、URL が正しく設定されているか確認 |
| `Discord webhook returned HTTP 4xx` | webhook URL が正しいか、webhook が削除されていないか確認 |
| `users.json not found` | `users.json` がアプリと同じディレクトリにあるか確認 |

## 将来の拡張ポイント

- **GUI**: tkinter / PyQt で操作画面を追加
- **DB化**: SQLite / PostgreSQL でユーザー管理を高度化
- **Web 管理画面**: Flask / FastAPI で登録・編集を Web 化
- **Discord Bot 化**: webhook の代わりに Bot として双方向通信
- **複数 webhook 振り分け**: タグやユーザー属性に応じて送信先を切替
- **Windows サービス化**: 自動起動・バックグラウンド実行
- **ログファイル出力**: `RotatingFileHandler` でファイルにもログ保存
- **ユーザー登録 CLI**: コマンドラインからタグ登録を行うサブコマンド

## ライセンス

このプロジェクトは個人利用を想定しています。
