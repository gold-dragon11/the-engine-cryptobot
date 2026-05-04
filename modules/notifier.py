import re
import requests
import logging
import config
from modules.i18n import i18n

logger = logging.getLogger(__name__)

# MarkdownV2 requires these 18 characters to be backslash-escaped.
_MD_SPECIAL = r'_*[]()~`>#+-=|{}.!'

def escape_md(text) -> str:
    """Escape all MarkdownV2 special characters in `text`.

    Converts the value to str first, so None / int / float are safe to pass.
    Example:  1.84%  ->  1\\.84%   (dot is escaped as required by MarkdownV2)
    """
    return re.sub(r'([%s])' % re.escape(_MD_SPECIAL), r'\\\1', str(text))

# Internal alias kept for backwards compat within this module.
_escape_md_v2 = escape_md

def _send_telegram_message(text: str):
    """Sends a raw MarkdownV2 message directly to the Admin."""
    if not config.TELEGRAM_BOT_TOKEN or not config.ADMIN_CHAT_ID:
        logger.warning("Telegram token or Admin Chat ID not set. Cannot send alert.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Notifier failed to send message: {response.text}")
    except Exception as e:
        logger.error(f"Notifier network error: {e}")

def send_signal_alert(signal_data: dict):
    """Refactored to use passed TP targets."""
    ticker = str(signal_data.get("ticker", "UNKNOWN"))
    trade_type = str(signal_data.get("type", "UNKNOWN"))
    entry = float(signal_data.get("entry_price", 0.0))
    tp1 = float(signal_data.get("tp1", 0.0))
    tp2 = float(signal_data.get("tp2", 0.0))
    tp3 = float(signal_data.get("tp3", 0.0))
    sl = float(signal_data.get("sl", 0.0))
    comment = signal_data.get("comment", "")

    header_icon = "🟢" if trade_type == "LONG" else "🔴"
    
    e_ticker = _escape_md_v2(f"#{ticker}")
    e_type = _escape_md_v2(trade_type)
    e_entry = _escape_md_v2(f"{entry:.4f}")
    e_tp1 = _escape_md_v2(f"{tp1:.4f}")
    e_tp2 = _escape_md_v2(f"{tp2:.4f}")
    e_tp3 = _escape_md_v2(f"{tp3:.4f}")
    e_sl = _escape_md_v2(f"{sl:.4f}")
    e_comment = _escape_md_v2(comment)

    msg = (
        f"{i18n.get('notifier.signal_header', icon=header_icon)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{i18n.get('notifier.asset', ticker=e_ticker)}\n"
        f"{i18n.get('notifier.action', type=e_type)}\n\n"
        f"{i18n.get('notifier.entry_price', entry=e_entry)}\n\n"
        f"{i18n.get('notifier.targets_title')}\n"
        f"{i18n.get('notifier.tp_level', level=1, tp=e_tp1)}\n"
        f"{i18n.get('notifier.tp_level', level=2, tp=e_tp2)}\n"
        f"{i18n.get('notifier.tp_level', level=3, tp=e_tp3)}\n\n"
        f"{i18n.get('notifier.stop_loss', sl=e_sl)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{i18n.get('notifier.ai_audit', comment=e_comment)}"
    )

    _send_telegram_message(msg)

def send_ledger_entry(ticker: str):
    """Notify admin that a virtual trade entry was triggered.

    The ledger locale strings are plain text (no MarkdownV2 markers), so we
    compose the message first and then escape the whole thing in one pass.
    """
    raw_msg = i18n.get("ledger.entry", ticker=ticker)
    _send_telegram_message(f"📥 {escape_md(raw_msg)}")

def send_ledger_close(ticker: str, pnl: float):
    """Notify admin that a virtual trade was closed with a PnL result.

    Same plain-text strategy: compose first, escape everything at once.
    """
    raw_msg = i18n.get("ledger.close", ticker=ticker, pnl=f"{pnl:+.2f}")
    _send_telegram_message(f"📊 {escape_md(raw_msg)}")

def send_status_update(active_count: int, btc_trend: str):
    e_count = _escape_md_v2(str(active_count))
    e_trend = _escape_md_v2(btc_trend)
    
    msg = (
        f"{i18n.get('notifier.status_header')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{i18n.get('notifier.status_system')}\n"
        f"{i18n.get('notifier.active_signals', count=e_count)}\n"
        f"{i18n.get('notifier.btc_trend', trend=e_trend)}\n"
    )

    _send_telegram_message(msg)
