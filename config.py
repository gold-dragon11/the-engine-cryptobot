# ============================================================
#  config.py — Dragon Crypto Oracle
#  Loads all environment variables and exposes typed constants.
# ============================================================

import logging
import os
from dotenv import load_dotenv

# Load variables from the .env file into the process environment.
# This must run before any module reads os.getenv().
load_dotenv()

logger = logging.getLogger(__name__)


# ── Telegram ────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID: str = os.getenv("ADMIN_CHAT_ID", "")

# ── Binance ─────────────────────────────────────────────────
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

# ── Google Gemini (free LLM for sentiment analysis) ──────────
# Get a free key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

DB_PATH: str = os.getenv("DB_PATH", "engine.db")

# ── RSS News Feeds (no API key required) ─────────────────────
# These are parsed by feedparser to retrieve the latest crypto headlines.
RSS_FEEDS: list[str] = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/feed",           # arc/outboundfeed URL is 404
    "https://cryptopotato.com/feed/",
    "https://decrypt.co/feed",                 # Additional quality source
]


def validate_config() -> None:
    """
    Raise a descriptive RuntimeError if any required key is missing.
    Call this once at startup so the bot fails fast with a clear message.

    Note: GEMINI_API_KEY is optional — if absent, /analyze will skip
    AI sentiment and show a warning in the report.
    """
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "BINANCE_API_KEY": BINANCE_API_KEY,
        "BINANCE_API_SECRET": BINANCE_API_SECRET,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        error_msg = (
            f"[CRITICAL] Missing required environment variables: {', '.join(missing)}. "
            "Please fill them in your .env file and restart the bot."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
