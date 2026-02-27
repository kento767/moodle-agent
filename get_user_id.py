"""
LINE Webhook を受信して User ID を表示する簡易サーバー。
友だち追加やメッセージ送信時に source.userId をログに出力する。

使い方:
  1. python get_user_id.py で起動
  2. ngrok http 5000 で公開
  3. LINE Developers の Webhook URL に https://xxx.ngrok-free.app/webhook を設定
  4. 対象の人に Bot を友だち追加してもらう
  5. ターミナルに表示された User ID をコピー
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = 5000


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

        try:
            data = json.loads(body.decode("utf-8"))
            events = data.get("events", [])
            for event in events:
                event_type = event.get("type", "unknown")
                source = event.get("source", {})
                user_id = source.get("userId")
                group_id = source.get("groupId")

                print("-" * 50)
                print(f"イベント種別: {event_type}")
                if user_id:
                    print(f"User ID: {user_id}")
                if group_id:
                    print(f"Group ID: {group_id}")
                if not user_id and not group_id:
                    print("(userId/groupId なし)")
                print("-" * 50)
        except Exception as e:
            print(f"パースエラー: {e}")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Webhook server is running. POST to /webhook.")

    def log_message(self, format, *args):
        pass  # アクセスログを抑制（User ID 表示を邪魔しないため）


def main():
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"Webhook サーバー起動: http://127.0.0.1:{PORT}")
    print("ngrok で公開: ngrok http 5000")
    print("Webhook URL: https://xxx.ngrok-free.app/webhook")
    print("友だち追加やメッセージで User ID が表示されます。Ctrl+C で終了。\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
        server.shutdown()


if __name__ == "__main__":
    main()
