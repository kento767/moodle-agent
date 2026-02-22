# Moodle → LINE 課題リマインド 進捗

## 要件・設計
- [x] Moodle の課題・締切を取得する要件
- [x] LINE Bot でリマインド送信する要件
- [x] 自分の PC 上で動作する前提

## Moodle 連携
- [x] Moodle ログインページへのアクセス
- [x] SSO ゲートウェイ対応（MultiDomainAuth → ConfirmationAuth → AuthRequest）
- [x] OMUID/Password による直接ログイン
- [x] 2FA（TOTP）対応
- [x] 2FA 再認証（カレンダー/マイページ取得時の SSO 経路）
- [x] SAML リダイレクト対応
- [x] カレンダーページからの課題取得
- [x] マイページからの課題取得

## LINE 連携
- [x] LINE Messaging API によるプッシュ送信
- [x] リマインドメッセージの整形・送信
- [x] 長文時の分割送信

## 設定・運用
- [x] .env による設定読み込み（override=True）
- [x] REMINDER_DAYS による締切フィルタ
- [x] ログ出力（ファイル + 標準エラー）
- [x] 取得確認モード削除
- [x] 1日以内の課題のみリマインドに変更
- [x] デバッグ用 HTML 保存を削除（本番運用向け）
- [x] タスクスケジューラ: 毎日 17:00 に実行する設定を README に記載
- [ ] PC オフ時も通知（[DEPLOYMENT.md](DEPLOYMENT.md) 参照。Railway / PythonAnywhere / Raspberry Pi）
