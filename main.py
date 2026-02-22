"""
Moodle の課題を取得し、締切が N 日以内のものを LINE に送信する。
タスクスケジューラから毎日実行する想定。
"""
import logging
import sys
from pathlib import Path

from config import MOODLE_URL, PROJECT_ROOT, REMINDER_DAYS, _ENV_LOADED_FROM
from line_sender import send_reminder
from moodle_scraper import fetch_assignments

# ログを標準エラー＋ファイルに出力（プロジェクトルート基準の絶対パス）
# Railway 等ではファイル書き込みができない場合があるため、ファイルはオプション
handlers = [logging.StreamHandler(sys.stderr)]
try:
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    LOG_FILE = LOG_DIR / "moodle_reminder.log"
    handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
except OSError:
    pass  # ファイルに書けない環境（Railway 等）では stderr のみ

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=handlers,
)
logger = logging.getLogger(__name__)


def main() -> int:
    """0: 成功, 1: エラー"""
    logger.info("Moodle リマインドを開始（REMINDER_DAYS=%d 日以内の課題）", REMINDER_DAYS)
    if _ENV_LOADED_FROM:
        logger.info(".env 読み込み元: %s", _ENV_LOADED_FROM)

    if not MOODLE_URL or MOODLE_URL == "https://moodle.example.ac.jp":
        logger.error(".env の MOODLE_URL を設定してください")
        return 1

    assignments = fetch_assignments()
    logger.info("取得した課題数: %d", len(assignments))

    due_soon = [a for a in assignments if a.is_due_within_days(REMINDER_DAYS)]
    logger.info("締切 %d 日以内の課題数: %d", REMINDER_DAYS, len(due_soon))
    if not send_reminder(due_soon, REMINDER_DAYS):
        logger.error("LINE 送信に失敗しました")
        return 1

    logger.info("LINE 送信完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
