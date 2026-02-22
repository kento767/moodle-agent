# クラウドデプロイ（PC オフ時も通知）

PC の電源がオフでも毎日 17:00 に通知を受け取るには、クラウドで本プログラムを動かします。

## 推奨: Railway

**Railway** は Cron ジョブに対応しており、毎日決まった時刻に実行できます。

### 前提

- GitHub アカウント
- Railway アカウント（[railway.app](https://railway.app) で無料登録、クレジットカード不要で $5 クレジット付与）

### 手順

#### 1. リポジトリを GitHub にプッシュ

```powershell
cd c:\Users\katoy\Downloads\moodle-agent
git init
git add .
git commit -m "Initial commit"
# GitHub でリポジトリを作成後
git remote add origin https://github.com/あなたのユーザー名/moodle-agent.git
git push -u origin main
```

**重要**: `.env` は `.gitignore` に含まれているため、Git には含めません。認証情報は Railway の環境変数で設定します。

#### 2. Railway でプロジェクト作成

1. [railway.app](https://railway.app) にログイン
2. **New Project** → **Deploy from GitHub repo**
3. リポジトリ `moodle-agent` を選択
4. デプロイが開始される（初回は失敗する場合あり。環境変数設定後に再デプロイ）

#### 3. 環境変数を設定

Railway のプロジェクト → サービス → **Variables** で以下を追加:

| 変数名 | 値 |
|--------|-----|
| MOODLE_URL | `https://lms.omu.ac.jp/` |
| MOODLE_USER | あなたの OMUID |
| MOODLE_PASSWORD | あなたのパスワード |
| TOTP_SECRET | Google Authenticator の秘密キー（Base32、先頭 32 文字） |
| LINE_CHANNEL_ACCESS_TOKEN | LINE Messaging API のチャネルアクセストークン |
| LINE_USER_ID | 送信先の LINE ユーザー ID |
| REMINDER_DAYS | `1` |

#### 4. Cron スケジュールを設定

1. サービス → **Settings**
2. **Cron Schedule** に `0 8 * * *` を入力  
   - 意味: 毎日 08:00 UTC = **17:00 JST（日本時間）**
3. **Start Command** に `python main.py` を設定（未設定の場合は自動検出される場合あり）
4. **Deploy** を保存

#### 5. 動作確認

- **Deployments** タブでログを確認
- 手動で **Redeploy** して即時実行し、LINE に通知が届くか確認

---

## 代替: PythonAnywhere

**PythonAnywhere** の無料アカウントでは、1 日 1 回のスケジュールタスクが使える場合があります（アカウント作成時期により制限あり）。

### 手順概要

1. [pythonanywhere.com](https://www.pythonanywhere.com) で無料登録
2. **Files** でプロジェクトをアップロード（ZIP または Git）
3. **Consoles** で `pip install -r requirements.txt`
4. **Tasks** で毎日 17:00（JST）に `python main.py` を実行するタスクを作成
5. **Environment variables** で MOODLE_* / LINE_* 等を設定

※ PythonAnywhere の時刻は UTC。17:00 JST = 08:00 UTC で設定。

---

## 代替: Raspberry Pi

自宅に Raspberry Pi があれば、常時起動で cron を設定できます。

```bash
# crontab -e で編集
0 17 * * * cd /home/pi/moodle-agent && /home/pi/moodle-agent/venv/bin/python main.py
```

---

## 注意事項

- **認証情報**: `.env` やパスワードは Git にコミットしないでください
- **Railway の課金**: $5 クレジットは数ヶ月持つ想定。Cron は実行時間のみ課金
- **ログ**: Railway の Deployments タブで実行ログを確認できます
