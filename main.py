# ============================================================
#  main.py — Dragon Crypto Oracle  (v3 – Market Structure)
#
#  Entry point. Wires together:
#    • Config validation
#    • Telegram bot (async, python-telegram-bot v21+)
#    • /start   and /help     — general commands
#    • /language              → inline keyboard language picker (EN/UA/ES/DE)
#    • /price                 → live BTC/USDT from Binance (ccxt)
#    • /risk    <b> <r%> <e> <sl> → manual position size, leverage, TP
#    • /analyze <COIN>        → price + structure + FnG + news + AI + risk
# ============================================================

import asyncio
import logging
import sys
from typing import Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
from modules.db_manager import DatabaseManager

# Global Database Instance accessible to future modules
db = DatabaseManager()

from modules.finance import (
    fetch_btc_price,
    fetch_fear_and_greed,
    fetch_market_structure,
)
from modules.risk_manager import calculate_trade_risk
from modules.news_utils import get_latest_news
from modules.ai_analyzer import analyze_sentiment, analyze_performance
from modules.i18n import i18n, LANGUAGE_NAMES
from modules.performance_tracker import run_performance_tracker

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Configuration Variables (The Watcher) ────────────────────
WATCHED_COINS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
MONITOR_INTERVAL = 1800  # 30 minutes
CONFIDENCE_THRESHOLD = 8

# ── User language preferences ──────────────────────────────────
# Language is persisted via user_profiles.json

def _lang(user_id: int) -> str:
    return db.get_user_language(user_id)


def _t(user_id: int, key: str, **kwargs) -> str:
    """Shorthand: translate `key` into the user's preferred language."""
    return i18n.get(key, lang=_lang(user_id), **kwargs)


# ── /start ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from modules.i18n import LANGUAGE_NAMES
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(LANGUAGE_NAMES["en"], callback_data="setlang_en"),
            InlineKeyboardButton(LANGUAGE_NAMES["uk"], callback_data="setlang_uk"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["es"], callback_data="setlang_es"),
            InlineKeyboardButton(LANGUAGE_NAMES["de"], callback_data="setlang_de"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["ru"], callback_data="setlang_ru"),
            InlineKeyboardButton(LANGUAGE_NAMES["fr"], callback_data="setlang_fr"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["pl"], callback_data="setlang_pl"),
        ],
    ])
    
    await update.message.reply_text(
        "Please select your language / Будь ласка, оберіть мову:",
        reply_markup=keyboard,
    )

# ── /about ───────────────────────────────────────────────────
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the business card / ecosystem details."""
    uid = update.effective_user.id
    await update.message.reply_html(_t(uid, "about_text"))

async def about_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the inline keyboard button press for about."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    await query.message.reply_html(_t(uid, "about_text"))


# ── /help ────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the full command reference."""
    uid = update.effective_user.id
    help_text = _t(uid, "help_text")
    await update.message.reply_html(help_text)


# ── /language ────────────────────────────────────────────────
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show an inline keyboard so the user can pick their interface language."""
    uid = update.effective_user.id
    # Present options across rows for 7 languages
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(LANGUAGE_NAMES["en"], callback_data="setlang_en"),
            InlineKeyboardButton(LANGUAGE_NAMES["uk"], callback_data="setlang_uk"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["es"], callback_data="setlang_es"),
            InlineKeyboardButton(LANGUAGE_NAMES["de"], callback_data="setlang_de"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["ru"], callback_data="setlang_ru"),
            InlineKeyboardButton(LANGUAGE_NAMES["fr"], callback_data="setlang_fr"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["pl"], callback_data="setlang_pl"),
        ],
    ])
    await update.message.reply_text(
        i18n.get("choose_language", lang=_lang(uid)),
        reply_markup=keyboard,
    )


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    lang_code = query.data.replace("setlang_", "")
    from modules.i18n import LANGUAGE_NAMES
    if lang_code not in LANGUAGE_NAMES:
        return

    uid = query.from_user.id
    db.set_user_language(uid, lang_code)
    db.activate_user(uid)
    logger.info("User %d set language to '%s' and activated the bot.", uid, lang_code)

    await query.edit_message_text(
        "🐉 Систему активовано. Фонове сканування ринку розпочато..."
    )


# ── Background Streams ─────────────────────────────────────────

async def binance_stream_watcher() -> None:
    """Live Binance data stream background loop."""
    await asyncio.sleep(3)
    from modules.data_streamer import BinanceStreamer
    from modules.market_analyzer import check_btc_trend
    import time
    
    streamer = BinanceStreamer()
    logger.info("🚀 Live Market Streamer Active [7 Tickers]")
    
    last_trend_check = 0
    TREND_CHECK_INTERVAL = 300  # 5 minutes
    
    last_strategy_run_time = 0
    STRATEGY_CHECK_INTERVAL = 1800  # 30 minutes
    
    backoff = 10
    while True:
        try:
            from main import db
            if not db.is_bot_activated():
                await asyncio.sleep(60)
                continue
                
            await streamer.fetch_all_prices()
            backoff = 10  # reset on success
            
            now = time.time()
            if now - last_trend_check >= TREND_CHECK_INTERVAL:
                trend = await check_btc_trend()
                allowed = "[Signals Allowed]" if trend == "BULLISH" else "[Signals Blocked]"
                logger.info(f"🛡️ BTC GUARD: Trend is {trend}. {allowed}.")
                last_trend_check = now
                
            if now - last_strategy_run_time >= STRATEGY_CHECK_INTERVAL:
                logger.info("🔔 30-min window reached. Starting full market audit...")
                from modules.strategy_engine import process_market_signals
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, process_market_signals)
                last_strategy_run_time = time.time()
            else:
                remaining_mins = int((STRATEGY_CHECK_INTERVAL - (now - last_strategy_run_time)) / 60)
                logger.info(f"⏳ Strategy Brain: Cooldown active. Next scan in {remaining_mins} minutes.")
                
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            logger.info("binance_stream_watcher: shutdown signal received.")
            return
        except Exception as e:
            logger.warning(f"⚠️ Connection lost, retrying in {backoff}s... ({e})")
            await asyncio.sleep(backoff)
            backoff = min(300, backoff * 2)

# ── The Watcher (Background Monitor) ─────────────────────────
async def market_watcher(app: Application) -> None:
    """Autonomous background loop scanning the market."""
    await asyncio.sleep(5)  # Let the bot connect and start polling smoothly
    logger.info("👁️ THE WATCHER: Background market monitor started")
    
    from modules.finance import _fetch_ticker_safe
    
    while True:
        try:
            from main import db
            if not db.is_bot_activated():
                await asyncio.sleep(60)
                continue
                
            for symbol in WATCHED_COINS:
                coin = symbol.split('/')[0]
                try:
                    loop = asyncio.get_event_loop()
                    
                    # a) Fetch Technicals
                    ticker = await loop.run_in_executor(None, _fetch_ticker_safe, symbol)
                    mkt_structure = await loop.run_in_executor(None, fetch_market_structure, symbol)
                    
                    if not ticker or 'last' not in ticker or not mkt_structure:
                        logger.warning(f"Watcher: Missing technical data for {symbol}")
                        await asyncio.sleep(2)  # Brief pause before next coin
                        continue

                    current_price = ticker["last"]
                    volume_24h = ticker.get("baseVolume", 0)
                    
                    fng_data = await loop.run_in_executor(None, fetch_fear_and_greed)
                    fng_display = fng_data.get("display", "N/A")

                    # b) Fetch News
                    _, _, micro_items, macro_items = await loop.run_in_executor(None, get_latest_news, coin)
                    
                    def _fmt_news_block(items) -> str:
                        if not items:
                            return ""
                        return "\n\n".join(f"{i}. [{it.source}] {it.title}\n   {it.summary}" for i, it in enumerate(items, 1))

                    micro_text = _fmt_news_block(micro_items[:4])
                    macro_text = _fmt_news_block(macro_items[:4])

                    # c) Call ai_analyzer — rate-limit guard follows immediately after
                    sentiment = await loop.run_in_executor(
                        None,
                        lambda: analyze_sentiment(
                            coin_name=coin,
                            news_text=micro_text,
                            price=current_price,
                            volume_24h=volume_24h,
                            fng_display=fng_display,
                            macro_text=macro_text,
                            atr_14=mkt_structure.atr_14,
                            rsi_14=mkt_structure.rsi_14,
                            support=mkt_structure.support,
                            resistance=mkt_structure.resistance,
                            lang=_lang(int(config.ADMIN_CHAT_ID)) if config.ADMIN_CHAT_ID and str(config.ADMIN_CHAT_ID).lstrip('-').isdigit() else "en"
                        ),
                    )
                    # Gemini rate-limit cooldown: pause 15s between coins so the
                    # Watcher's 6-coin scan stays comfortably within free-tier RPM.
                    await asyncio.sleep(15)

                    # Filter: Direction LONG/SHORT AND confidence >= CONFIDENCE_THRESHOLD
                    if sentiment.direction in ["LONG", "SHORT"] and sentiment.confidence >= CONFIDENCE_THRESHOLD:
                        # Anti-Spam check
                        active_signals = db.get_signals_by_status('ACTIVE') + db.get_signals_by_status('PENDING')
                        if any(s.get('ticker') == coin or s.get('ticker') == symbol.replace('/', '') for s in active_signals):
                            logger.info(f"Anti-spam: Signal for {coin} already active/pending.")
                            continue

                        dyn_result = None
                        prof = {"balance": 1000.0, "risk_percent": 2.0} # Fallback
                        
                        if mkt_structure.atr_14:
                            try:
                                dyn_result = calculate_trade_risk(
                                    entry_price=current_price,
                                    support=mkt_structure.support,
                                    resistance=mkt_structure.resistance,
                                    atr_14=mkt_structure.atr_14,
                                    ai_direction=sentiment.direction
                                )
                            except Exception as e:
                                logger.warning(f"Watcher dynamic risk calc error for {coin}: {e}")

                        if dyn_result:
                            signal_data = {
                                "ticker": coin,
                                "type": sentiment.direction,
                                "entry_price": dyn_result.entry_price,
                                "sl": dyn_result.stop_loss,
                                "tp": dyn_result.take_profit,
                                "rr_ratio": dyn_result.rr_ratio,
                                "leverage": sentiment.leverage,
                                "comment": sentiment.reasoning
                            }
                            
                            from modules.notifier import send_signal_alert
                            if config.ADMIN_CHAT_ID:
                                send_signal_alert(signal_data)
                                db.add_signal(coin, sentiment.direction, dyn_result.entry_price, dyn_result.take_profit, 0.0, 0.0, dyn_result.stop_loss)
                            else:
                                logger.warning(f"No ADMIN_CHAT_ID found in config. Cannot send alert for {coin}.")
                    else:
                        print(f"[{coin}] Silently passed. Reason: {sentiment.direction}, Conf: {sentiment.confidence}")

                except Exception as e:
                    logger.error(f"Error watching {coin}: {e}")
                    await asyncio.sleep(5)  # Brief backoff on per-coin errors

        except asyncio.CancelledError:
            logger.info("market_watcher: shutdown signal received.")
            return
        except Exception as e:
            logger.error(f"Market watcher loop error: {e}")

        # Sleep Cycle
        await asyncio.sleep(MONITOR_INTERVAL)


# ── Helpers ───────────────────────────────────────────────────

def _fng_emoji(value: Optional[int]) -> str:
    """Return an emoji that visually maps to the Fear & Greed value."""
    if value is None:
        return "❓"
    if value >= 75:
        return "🤑"   # Extreme Greed
    if value >= 55:
        return "😄"   # Greed
    if value >= 45:
        return "😐"   # Neutral
    if value >= 25:
        return "😨"   # Fear
    return "😱"       # Extreme Fear


# ── Application entry point ──────────────────────────────────
def main() -> None:
    """
    Build the Telegram Application, register all handlers, and start polling.

    python-telegram-bot v21 uses asyncio internally. Python 3.14 removed
    implicit event loop creation, so we create and set one explicitly before
    calling run_polling().
    """
    try:
        config.validate_config()
    except RuntimeError as exc:
        logger.critical("Bot startup aborted: %s", exc)
        sys.exit(1)
    
    # Initialize Database System
    db.init_db()
    db.initialize_market_state()
    db.reset_all_activations()  # Always boot dormant — requires fresh /start activation
    active_count = db.get_active_signals_count()
    
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT trend_direction FROM market_state WHERE ticker='BTCUSDT'")
    row = cursor.fetchone()
    btc_trend = row[0] if row else "UNKNOWN"
    conn.close()
    
    logger.info("--- Database System Online ---")
    print(f"Active Signals in DB: {active_count} | BTC Trend: {btc_trend}")
    
    # Fire startup status to telegram Admin
    from modules.notifier import send_status_update
    send_status_update(active_count, btc_trend)
    
    logger.info(f"🐉 Dragon Crypto Oracle v3 (Market Structure) is starting… [Model: {config.GEMINI_MODEL}]")

    async def post_init(application: Application) -> None:
        application.create_task(binance_stream_watcher())
        application.create_task(market_watcher(application))
        application.create_task(run_performance_tracker(db))

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("about",    about_command))
    app.add_handler(CommandHandler("language", language_command))

    # Inline-keyboard callback: language selector buttons
    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^setlang_"))
    
    # Inline-keyboard callback: about
    app.add_handler(CallbackQueryHandler(about_callback, pattern=r"^action_about$"))

    logger.info("Handlers registered. Starting polling…")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
