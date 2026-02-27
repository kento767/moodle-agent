"""
LINE Messaging API でプッシュメッセージを送信する。
"""
import logging
import re
from typing import List

import requests

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_IDS, MOODLE_URL
from models import Assignment

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
# テキストメッセージは最大 5000 文字（LINE の仕様）
MAX_TEXT_LENGTH = 5000

# LINE User ID: U + 英数字32文字（改行・スペース等の混入を防ぐ）
LINE_USER_ID_PATTERN = re.compile(r"^U[a-zA-Z0-9]{32}$")


def _sanitize_user_id(uid: str) -> str:
    """改行・スペース・制御文字を除去し、LINE API が受け付ける形式にする。"""
    return "".join(c for c in uid if c.isalnum() or c == "_")


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

    # 改行・BOM・余分な空白などが混入していると LINE API が "to" invalid を返す
    to_user_id = _sanitize_user_id(to_user_id.strip())
    if not LINE_USER_ID_PATTERN.match(to_user_id):
        logger.error(
            "LINE_USER_ID の形式が不正です（U+英数字32文字である必要があります）: "
            "len=%d repr=%r",
            len(to_user_id),
            to_user_id[:20] + "..." if len(to_user_id) > 20 else to_user_id,
        )
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


def _send_text_to_all(text: str) -> bool:
    """全ユーザーにテキストを送信する。1人でも失敗したら False を返す。"""
    if not LINE_USER_IDS:
        logger.error("LINE_USER_ID が設定されていません")
        return False
    results = [send_text(uid, text) for uid in LINE_USER_IDS]
    return all(results)


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
    長い場合は複数メッセージに分割して全ユーザーに送る。
    """
    body = format_reminder_message(assignments, reminder_days)
    if len(body) <= MAX_TEXT_LENGTH:
        return _send_text_to_all(body)
    # 分割送信
    sent = True
    chunk = ""
    for line in body.split("\n"):
        if len(chunk) + len(line) + 1 > MAX_TEXT_LENGTH and chunk:
            if not _send_text_to_all(chunk):
                sent = False
            chunk = ""
        chunk += (line + "\n") if chunk else line
    if chunk and sent:
        sent = _send_text_to_all(chunk.strip())
    return sent
