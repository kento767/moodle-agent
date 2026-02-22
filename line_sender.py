"""
LINE Messaging API でプッシュメッセージを送信する。
"""
import logging
from typing import List

import requests

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, MOODLE_URL
from models import Assignment

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
# テキストメッセージは最大 5000 文字（LINE の仕様）
MAX_TEXT_LENGTH = 5000


def send_text(to_user_id: str, text: str) -> bool:
    """
    指定ユーザー（またはグループ）にテキストを 1 通送信する。
    Returns:
        成功なら True。
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN が設定されていません")
        return False
    if not to_user_id:
        logger.error("送信先 LINE_USER_ID が設定されていません")
        return False

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": to_user_id,
        "messages": [{"type": "text", "text": text[:MAX_TEXT_LENGTH]}],
    }

    try:
        r = requests.post(LINE_PUSH_URL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.exception("LINE 送信に失敗: %s", e)
        if hasattr(e, "response") and e.response is not None:
            try:
                logger.error("Response: %s", e.response.text)
            except Exception:
                pass
        return False


def format_reminder_message(assignments: List[Assignment], reminder_days: int) -> str:
    """課題リストを LINE 用のリマインド文に整形する。"""
    if not assignments:
        return "締切が近い課題はありません。"

    lines = [f"【Moodle リマインド】締切 {reminder_days} 日以内の課題", ""]
    for a in assignments:
        lines.append(a.format_for_line(MOODLE_URL))
        lines.append("")
    return "\n".join(lines).strip()


def send_reminder(assignments: List[Assignment], reminder_days: int) -> bool:
    """
    リマインドメッセージを LINE で送信する。
    長い場合は複数メッセージに分割する。
    """
    body = format_reminder_message(assignments, reminder_days)
    # 1 通で送れる長さを超える場合は分割（簡易: 前半のみ送る or 複数 push）
    if len(body) <= MAX_TEXT_LENGTH:
        return send_text(LINE_USER_ID, body)
    # 分割送信
    sent = True
    chunk = ""
    for line in body.split("\n"):
        if len(chunk) + len(line) + 1 > MAX_TEXT_LENGTH and chunk:
            if not send_text(LINE_USER_ID, chunk):
                sent = False
            chunk = ""
        chunk += (line + "\n") if chunk else line
    if chunk and sent:
        sent = send_text(LINE_USER_ID, chunk.strip())
    return sent
