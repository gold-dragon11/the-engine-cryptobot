import re
import requests
import logging
import config
from modules.i18n import i18n

logger = logging.getLogger(__name__)

def escape_html(text) -> str:
    """Escape HTML special characters in `text`."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _send_telegram_message(text: str):
    """Sends a raw HTML message directly to the Admin."""
    if not config.TELEGRAM_BOT_TOKEN or not config.ADMIN_CHAT_ID:
        logger.warning("Telegram token or Admin Chat ID not set. Cannot send alert.")
        return

    from main import db
    if not db.is_bot_activated():
        logger.info("Bot is inactive. Notification suppressed.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Notifier failed to send message: {response.text}")
    except Exception as e:
        logger.error(f"Notifier network error: {e}")

def send_signal_alert(signal_data: dict):
    ticker = str(signal_data.get("ticker", "UNKNOWN"))
    trade_type = str(signal_data.get("type", "UNKNOWN"))
    entry = float(signal_data.get("entry_price", 0.0))
    sl = float(signal_data.get("sl", 0.0))
    tp = float(signal_data.get("tp", 0.0))
    rr = float(signal_data.get("rr_ratio", 0.0))
    leverage = int(signal_data.get("leverage", 1))
    comment = signal_data.get("comment", "")

    header_icon = "🟢" if trade_type == "LONG" else "🔴"
    
    e_ticker = escape_html(ticker)
    e_type = escape_html(trade_type)
    e_entry = escape_html(f"{entry:.4f}")
    e_sl = escape_html(f"{sl:.4f}")
    e_tp = escape_html(f"{tp:.4f}")
    e_rr = escape_html(f"1:{rr:.2f}")
    e_leverage = escape_html(str(leverage))
    e_comment = escape_html(comment)

    msg = (
        f"🐉 <b>[SHADOW OF THE DRAGON - СИГНАЛ]</b> 🐉\n"
        f"<b>Монета:</b> {e_ticker}\n"
        f"<b>Напрямок:</b> {e_type} {header_icon}\n\n"
        f"📍 <b>Вхід:</b> ${e_entry}\n"
        f"🛑 <b>Stop Loss:</b> ${e_sl}\n"
        f"🎯 <b>Take Profit:</b> ${e_tp}\n\n"
        f"⚙️ <b>Налаштування:</b>\n"
        f"- <b>Плече:</b> {e_leverage}x (Isolated)\n"
        f"- <b>Risk/Reward:</b> {e_rr}\n\n"
        f"🧠 <b>Аргументація:</b> {e_comment}"
    )

    _send_telegram_message(msg)

def send_ledger_entry(ticker: str):
    raw_msg = i18n.get("ledger.entry", ticker=ticker)
    _send_telegram_message(f"📥 {escape_html(raw_msg)}")

def send_ledger_close(ticker: str, pnl: float):
    raw_msg = i18n.get("ledger.close", ticker=ticker, pnl=f"{pnl:+.2f}")
    _send_telegram_message(f"📊 {escape_html(raw_msg)}")

def send_status_update(active_count: int, btc_trend: str):
    trend_icon = "🟢" if btc_trend == "BULLISH" else "🔴" if btc_trend == "BEARISH" else "🟡"
    msg = (
        f"🐉 <b>Shadow of the Dragon — Статус Системи</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>Стан:</b> <code>ONLINE</code>\n"
        f"📊 <b>Активних сигналів:</b> <code>{escape_html(str(active_count))}/3</code>\n"
        f"₿ <b>BTC Тренд:</b> {trend_icon} <code>{escape_html(btc_trend)}</code>\n"
    )
    _send_telegram_message(msg)
