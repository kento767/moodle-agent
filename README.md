# Moodle → LINE 課題リマインド

大学の Moodle の課題・期限を取得し、LINE Bot でリマインドを送るツールです。自分の PC 上で動作します。

## 事前準備

### 1. Moodle

- 大学の Moodle の URL を控えておく（例: `https://moodle.xxx.ac.jp/`）
- **2段階認証（学外 WiFi など）**: Google Authenticator の秘密キーを `TOTP_SECRET` に設定（2FA 不要なら空のままで OK）

### 2. LINE Bot（Messaging API）の準備

1. [LINE Developers](https://developers.line.biz/) にログイン
2. プロバイダーを作成（未作成の場合）
3. **Messaging API** のチャネルを新規作成
4. チャネル作成後:
   - **Messaging API** タブで **Channel access token** を発行し、控える
   - Bot を友だち追加し、**自分のユーザー ID** を取得する（Webhook の「検証」で送信されるイベントの `userId` を確認するか、後述の簡易取得方法を使う）
5. 必要に応じてグループに Bot を追加し、グループ ID を送信先に指定可能

### 3. 環境構築

```powershell
cd c:\Users\katoy\Downloads\moodle-agent
python -m venv venv
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

`.env.example` をコピーして `.env` を作成し、値を設定する:

```powershell
copy .env.example .env
# .env を編集して MOODLE_* / LINE_* / REMINDER_DAYS を設定
```

## 実行方法

- **手動実行（テスト）**

```powershell
.\venv\Scripts\activate
python main.py
```

- **毎日決まった時間に実行（タスクスケジューラ）**

「タスクスケジューラで毎日実行する」の手順は [タスクスケジューラで毎日実行する](#タスクスケジューラで毎日実行する) を参照。

## 設定項目（.env）

| 変数名 | 説明 |
|--------|------|
| MOODLE_URL | Moodle のベース URL（末尾の / を含む） |
| MOODLE_USER | ログイン ID（大阪公立大学 LMS の場合は OMUID） |
| MOODLE_PASSWORD | ログインパスワード |
| TOTP_SECRET | 2FA 用。Google Authenticator の秘密キー（Base32）。学外 WiFi 等で 2段階認証が必要な場合のみ。不要なら空 |
| LINE_CHANNEL_ACCESS_TOKEN | Messaging API のチャネルアクセストークン |
| LINE_USER_ID | 送信先の LINE ユーザー ID（自分 or グループ ID） |
| REMINDER_DAYS | 締切が何日以内の課題を送るか（整数）。デフォルト 1 |
| ACCESS_INTERVAL | Moodle へのアクセス間隔（秒）。学校サーバー負荷軽減・バグ時の連打防止用。デフォルト 2 |

## タスクスケジューラで毎日実行する

1. Windows の **タスクスケジューラ** を開く
2. **基本タスクの作成** で次を設定:
   - **トリガー**: 毎日、**17:00**（午後5時）
   - **操作**: プログラムの開始
   - **プログラム/スクリプト**:  
     - 方法A: `c:\Users\katoy\Downloads\moodle-agent\run_reminder.bat`  
     - 方法B: `c:\Users\katoy\Downloads\moodle-agent\venv\Scripts\python.exe`
   - **引数**（方法B の場合）: `c:\Users\katoy\Downloads\moodle-agent\main.py`
   - **開始**（オプション）: `c:\Users\katoy\Downloads\moodle-agent`
3. 作成したタスクを右クリック → **プロパティ** → **全般** で「ユーザーがログオンしているかどうかにかかわらず実行する」を選ぶと、ログオフ時も実行される（PC が起動している場合）

ログは `logs\moodle_reminder.log` に出力されます。失敗時はここを確認してください。

**PC がスリープやオフのときは実行されません。** 電源オフ時も通知を受けたい場合は [DEPLOYMENT.md](DEPLOYMENT.md) を参照し、Railway や PythonAnywhere 等でデプロイしてください。

## 自分の LINE ユーザー ID の取得方法

1. LINE Developers でチャネルの **Messaging API** タブを開く
2. **Webhook 設定** で Webhook URL を一時的に設定し「検証」する（ngrok 等でローカルサーバーを公開する必要あり）
3. または、Bot を友だち追加したあと、[LINE Bot SDK の get profile 用ツール](https://www.linebiz.com/jp/developer/)や、Webhook を受信する簡易サーバーを立てて、送られてくるイベントの `source.userId` を確認する
4. グループに送る場合は、Bot をグループに追加したときの Webhook イベントで `source.groupId` を取得し、`.env` の `LINE_USER_ID` にその ID を指定する（グループ ID で送信可能）

## 注意

- Moodle の利用規約・大学のポリシー、LINE の利用規約に従って利用してください
- 認証情報（.env）は Git にコミットしないでください
