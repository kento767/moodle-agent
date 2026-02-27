"""
設定の読み込み。環境変数または .env から取得する。
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルート（config.py があるディレクトリ = 絶対パス）
PROJECT_ROOT = Path(__file__).resolve().parent

# .env の読み込み（絶対パスで複数候補を試す）
# 読み込んだ .env のパス（動作確認用・ログで使用）
_ENV_LOADED_FROM: str | None = None


def _load_env() -> None:
    global _ENV_LOADED_FROM
    candidates: list[Path] = [
        PROJECT_ROOT / ".env",   # 1) プロジェクトルート（最優先・絶対パス）
        Path.cwd().resolve() / ".env",  # 2) カレントディレクトリ（タスクスケジューラ等）
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent / ".env")
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=True)  # .env を優先（既存の環境変数を上書き）
            _ENV_LOADED_FROM = str(p)
            break
    else:
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        _ENV_LOADED_FROM = str(PROJECT_ROOT / ".env") if (PROJECT_ROOT / ".env").is_file() else None

_load_env()


def get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


# 設定項目
MOODLE_URL = get("MOODLE_URL").rstrip("/") or "https://moodle.example.ac.jp"
MOODLE_USER = get("MOODLE_USER")
MOODLE_PASSWORD = get("MOODLE_PASSWORD")

# 2FA（Moodle 直接ログインで 2段階認証が必要な場合）
# Base32 の秘密キーは通常 16 または 32 文字。誤って 2 回貼り付けた場合は先頭 32 文字を使用
_raw_totp = get("TOTP_SECRET")
TOTP_SECRET = _raw_totp[:32] if len(_raw_totp) > 32 else _raw_totp

LINE_CHANNEL_ACCESS_TOKEN = get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_IDS = [uid.strip() for uid in get("LINE_USER_ID").split(",") if uid.strip()]
REMINDER_DAYS = max(0, get_int("REMINDER_DAYS", 1))

# Moodle へのアクセス間隔（秒）。学校サーバーへの負荷軽減・バグ時の連打防止用
ACCESS_INTERVAL = max(0, get_int("ACCESS_INTERVAL", 2))

# HTTP リクエストのタイムアウト（秒）。ネットワークが遅い場合は 60 以上に
REQUEST_TIMEOUT = max(60, get_int("REQUEST_TIMEOUT", 60))
