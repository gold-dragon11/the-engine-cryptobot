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
from modules.risk_manager import calculate_position, calculate_dynamic_position
from modules.news_utils import get_latest_news
from modules.ai_analyzer import analyze_sentiment, analyze_performance
from modules.i18n import i18n, LANGUAGE_NAMES
from modules.profile_manager import get_user_profile, update_user_profile
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
    """Return the stored language code for this user (default: English)."""
    prof = get_user_profile(user_id)
    return prof.get("language", "en")


def _t(user_id: int, key: str, **kwargs) -> str:
    """Shorthand: translate `key` into the user's preferred language."""
    return i18n.get(key, lang=_lang(user_id), **kwargs)


# ── /start ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the user first starts the bot."""
    user = update.effective_user
    uid = user.id
    welcome_text = _t(uid, "welcome_message", name=user.first_name)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(uid, "btn_about_project"), callback_data="action_about")]
    ])
    
    await update.message.reply_html(welcome_text, reply_markup=keyboard)

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
    """Handle the inline keyboard button press for language selection."""
    query = update.callback_query
    await query.answer()   # Acknowledge the tap immediately (removes the spinner)

    lang_code = query.data.replace("setlang_", "")
    if lang_code not in LANGUAGE_NAMES:
        return   # Unknown code — ignore silently

    uid = query.from_user.id
    update_user_profile(uid, {"language": lang_code})
    logger.info("User %d set language to '%s'", uid, lang_code)

    await query.edit_message_text(
        i18n.get("language_set", lang=lang_code, language=LANGUAGE_NAMES[lang_code])
    )


# ── Profile Management ───────────────────────────────────────
async def set_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_html(_t(uid, "usage_set_balance"))
        return
    try:
        val = float(context.args[0])
        if val <= 0: raise ValueError
        update_user_profile(uid, {"balance": val})
        await update.message.reply_html(_t(uid, "balance_updated", amount=f"${val:,.2f}"))
    except ValueError:
        await update.message.reply_html(_t(uid, "error_positive_number"))

async def set_risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_html(_t(uid, "usage_set_risk"))
        return
    try:
        val = float(context.args[0])
        if val <= 0 or val > 100: raise ValueError
        update_user_profile(uid, {"risk_percent": val})
        await update.message.reply_html(_t(uid, "risk_updated", percent=val))
    except ValueError:
        await update.message.reply_html(_t(uid, "error_percentage"))

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    prof = get_user_profile(uid)
    await update.message.reply_html(
        _t(uid, "settings_text", balance=prof['balance'], risk_percent=prof['risk_percent'])
    )

# ── /stats ───────────────────────────────────────────────────
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays virtual strategy performance statistics with an AI tip."""
    uid = update.effective_user.id
    lang = _lang(uid)
    
    stats = db.get_stats()
    
    # Get Gemini tip
    loop = asyncio.get_event_loop()
    ai_tip = await loop.run_in_executor(None, analyze_performance, stats, lang)
    
    msg = (
        f"📊 <b>{i18n.get('stats.header', lang=lang)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 {i18n.get('stats.win_rate', lang=lang)}: <b>{stats['win_rate']}%</b>\n"
        f"💰 {i18n.get('stats.balance', lang=lang)}: <b>{stats['total_pnl']:+.2f}%</b>\n"
        f"🏆 {i18n.get('stats.best_coin', lang=lang)}: <b>#{stats['best_coin']}</b>\n\n"
        f"💡 <i>{ai_tip}</i>"
    )
    
    await update.message.reply_html(msg)

# ── /guide ───────────────────────────────────────────────────
async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    guide_text = _t(uid, "guide_text")
    await update.message.reply_html(guide_text)


# ── /price ───────────────────────────────────────────────────
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display the live BTC/USDT price from Binance."""
    await update.message.reply_text(_t(update.effective_user.id, "fetching_price"))

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, fetch_btc_price)
    except Exception as e:
        logger.error("Failed to fetch BTC price: %s", e)
        await update.message.reply_text(_t(update.effective_user.id, "binance_error"))
        return

    change_sign = "▲" if (data["change_pct"] or 0) >= 0 else "▼"
    msg = _t(
        update.effective_user.id, 
        "price_report",
        last=data['last'],
        change_sign=change_sign,
        change_pct=abs(data['change_pct'] or 0),
        high=data['high_24h'],
        low=data['low_24h'],
        volume=data['volume_24h'],
        bid=data['bid'],
        ask=data['ask']
    )
    await update.message.reply_html(msg)


# ── /risk (manual mode) ─────────────────────────────────────
async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manual position sizing: user provides entry + stop-loss explicitly.

    Usage: /risk <balance> <risk_percent> <entry_price> <stop_loss_price>
    Example: /risk 10000 1 65000 63500
    """
    args = context.args
    uid = update.effective_user.id

    if len(args) != 4:
        await update.message.reply_html(_t(uid, "usage_risk"))
        return

    try:
        balance         = float(args[0])
        risk_percent    = float(args[1])
        entry_price     = float(args[2])
        stop_loss_price = float(args[3])
    except ValueError:
        await update.message.reply_text(_t(uid, "error_numbers"))
        return

    try:
        result = calculate_position(balance, risk_percent, entry_price, stop_loss_price)
    except ValueError as e:
        await update.message.reply_text(_t(uid, "invalid_input", error=e))
        return

    direction = "LONG 📈" if entry_price > stop_loss_price else "SHORT 📉"

    msg = _t(
        uid,
        "manual_risk_report",
        direction=direction,
        balance=balance,
        risk_percent=risk_percent,
        risk_amount=result.risk_amount_usd,
        entry=entry_price,
        stop_loss=stop_loss_price,
        take_profit=result.take_profit_price,
        risk_per_unit=result.risk_per_unit,
        position_size=result.position_size_units,
        position_value=result.position_value_usd,
        leverage=result.recommended_leverage,
        breakeven=result.breakeven_fee_pct
    )
    await update.message.reply_html(msg)


# ── /analyze ─────────────────────────────────────────────────
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Full intelligence report for a coin, in the user's chosen language.

    Usage: /analyze <COIN> [balance] [risk_percent]
    Example: /analyze BTC 10000 1

    Pipeline (v3):
      1. Live price + 24h volume    (ccxt Binance ticker)
      2. Market Structure           (OHLCV → Support/Resistance/ATR/RSI)
      3. Fear & Greed Index         (alternative.me)
      4. RSS news — micro + macro   (feedparser, 24h strict filter)
      5. AI sentiment via Gemini    (enriched market context prompt)
      6. Dynamic Risk Management    (SL=Support−ATR×1.5, TP=Resistance)
      7. Localized HTML report      → Telegram
    """
    args    = context.args
    uid     = update.effective_user.id
    lang    = _lang(uid)

    if not args:
        await update.message.reply_html(_t(uid, "usage_analyze"))
        return

    coin     = args[0].upper()
    prof     = get_user_profile(uid)
    balance  = float(args[1]) if len(args) > 1 else prof["balance"]
    risk_pct = float(args[2]) if len(args) > 2 else prof["risk_percent"]

    symbol_map = {
        "BTC": "BTC/USDT",  "ETH": "ETH/USDT",  "SOL": "SOL/USDT",
        "BNB": "BNB/USDT",  "XRP": "XRP/USDT",  "ADA": "ADA/USDT",
        "DOGE": "DOGE/USDT", "AVAX": "AVAX/USDT", "DOT": "DOT/USDT",
        "MATIC": "MATIC/USDT", "LINK": "LINK/USDT", "LTC": "LTC/USDT",
    }
    symbol = symbol_map.get(coin, f"{coin}/USDT")

    # ── Step 0: Immediate acknowledgement ────────────────────
    status_msg = await update.message.reply_html(_t(uid, "analyzing_status", symbol=coin))

    loop = asyncio.get_event_loop()

    # ── Step 1: Live price (Binance ticker) ──────────────────
    from modules.finance import _fetch_ticker_safe

    def _fetch_symbol_price():
        ticker = _fetch_ticker_safe(symbol)
        return {
            "symbol":     ticker["symbol"],
            "last":       ticker["last"],
            "change_pct": ticker["percentage"],
            "high_24h":   ticker["high"],
            "low_24h":    ticker["low"],
            "volume_24h": ticker["baseVolume"],
        }

    price_data = None
    try:
        price_data = await loop.run_in_executor(None, _fetch_symbol_price)
    except Exception as e:
        logger.error("Price fetch failed for %s: %s", symbol, e)

    # ── Step 1b: Market Structure (OHLCV → S/R + ATR + RSI) ──
    mkt_structure = None
    try:
        mkt_structure = await loop.run_in_executor(
            None, fetch_market_structure, symbol
        )
    except Exception as e:
        logger.error("Market structure fetch failed for %s: %s", symbol, e)

    # ── Step 1c: Fear & Greed Index ──────────────────────────
    fng_data = {"value": None, "label": "N/A", "display": "N/A"}
    try:
        fng_data = await loop.run_in_executor(None, fetch_fear_and_greed)
    except Exception as e:
        logger.warning("Fear & Greed fetch error: %s", e)

    # ── Step 2: RSS news (micro + macro streams) ─────────────
    price_status = (
        "✅ [1/5] Price + Structure fetched"
        if price_data and mkt_structure
        else "⚠️ [1/5] Partial data"
    )
    await status_msg.edit_text(
        f"🔮 Analyzing {coin}…\n\n"
        f"{price_status}\n"
        "⏳ [2/5] Scanning RSS feeds (24h filter, micro + macro)…"
    )

    news_items, news_text, micro_items, macro_items = await loop.run_in_executor(
        None, get_latest_news, coin
    )

    # Build separate text blocks for Gemini
    def _fmt_news_block(items) -> str:
        if not items:
            return ""
        lines = [
            f"{i}. [{it.source}] {it.title} ({it.published_fmt})\n   {it.summary}"
            for i, it in enumerate(items, 1)
        ]
        return "\n\n".join(lines)

    micro_text = _fmt_news_block(micro_items[:4])
    macro_text = _fmt_news_block(macro_items[:4])

    # ── Step 3: AI sentiment ─────────────────────────────────
    await status_msg.edit_text(
        f"🔮 Analyzing {coin}…\n\n"
        f"{price_status}\n"
        "✅ [2/5] News collected\n"
        "⏳ [3/5] Running AI sentiment analysis…"
    )

    current_price  = price_data["last"]       if price_data else None
    volume_24h     = price_data["volume_24h"] if price_data else None
    fng_display    = fng_data.get("display", "N/A")

    sentiment = await loop.run_in_executor(
        None,
        lambda: analyze_sentiment(
            coin_name   = coin,
            news_text   = micro_text,
            price       = current_price,
            volume_24h  = volume_24h,
            fng_display = fng_display,
            macro_text  = macro_text,
            atr_14      = mkt_structure.atr_14 if mkt_structure else None,
            rsi_14      = mkt_structure.rsi_14 if mkt_structure else None,
            support     = mkt_structure.support if mkt_structure else None,
            resistance  = mkt_structure.resistance if mkt_structure else None,
            lang        = lang,
        ),
    )

    # ── Step 4: Dynamic Risk Management ──────────────────────
    await status_msg.edit_text(
        f"🔮 Analyzing {coin}…\n\n"
        f"{price_status}\n"
        "✅ [2/5] News collected\n"
        "✅ [3/5] AI sentiment done\n"
        "⏳ [4/5] Computing dynamic risk (ATR + Structure)…"
    )

    dyn_result = None
    if price_data and price_data["last"] and mkt_structure and mkt_structure.atr_14:
        if sentiment.direction != "WAIT":
            entry = price_data["last"]
            try:
                dyn_result = calculate_dynamic_position(
                    balance       = balance,
                    risk_percent  = risk_pct,
                    entry_price   = entry,
                    support       = mkt_structure.support,
                    resistance    = mkt_structure.resistance,
                    atr_14        = mkt_structure.atr_14,
                    ai_direction  = sentiment.direction,
                )
            except ValueError as e:
                logger.warning("Dynamic risk calc error: %s", e)

    # ── Step 5: Build the localized report ───────────────────
    await status_msg.edit_text(
        f"🔮 Analyzing {coin}…\n\n"
        f"{price_status}\n"
        "✅ [2/5] News collected\n"
        "✅ [3/5] AI sentiment done\n"
        "✅ [4/5] Risk computed\n"
        "⏳ [5/5] Building report…"
    )

    # --- Price block (includes volume + Fear & Greed) ---
    if price_data:
        change_sign = "▲" if (price_data["change_pct"] or 0) >= 0 else "▼"
        fng_emoji   = _fng_emoji(fng_data.get("value"))
        price_block = (
            f"💵 Price:      <b>${price_data['last']:,.4f}</b>\n"
            f"📈 24h Change: {change_sign} {abs(price_data['change_pct'] or 0):.2f}%\n"
            f"🔺 High / Low: ${price_data['high_24h']:,.2f} / ${price_data['low_24h']:,.2f}\n"
            f"📦 {i18n.get('volume_24h', lang=lang)}: {price_data['volume_24h']:,.2f} {coin}\n"
            f"{fng_emoji} {i18n.get('fear_greed', lang=lang)}: <b>{fng_display}</b>"
        )
    else:
        price_block = i18n.get("price_unavailable", lang=lang)

    # --- Market Structure block ---
    if mkt_structure:
        rsi_display = f"{mkt_structure.rsi_14:.1f}" if mkt_structure.rsi_14 else "N/A"
        atr_display = f"${mkt_structure.atr_14:,.4f}" if mkt_structure.atr_14 else "N/A"
        # RSI emoji: overbought (>70) / oversold (<30) / neutral
        rsi_emoji = "🔴" if (mkt_structure.rsi_14 or 50) > 70 else (
            "🟢" if (mkt_structure.rsi_14 or 50) < 30 else "⚪"
        )
        structure_block = (
            f"🟩 {i18n.get('support', lang=lang)}: <b>${mkt_structure.support:,.4f}</b>\n"
            f"🟥 {i18n.get('resistance', lang=lang)}: <b>${mkt_structure.resistance:,.4f}</b>\n"
            f"📐 {i18n.get('atr', lang=lang)}: {atr_display}\n"
            f"{rsi_emoji} {i18n.get('rsi', lang=lang)}: <b>{rsi_display}</b>"
        )
    else:
        structure_block = i18n.get("structure_unavail", lang=lang)

    # --- News block (top 4, strict 24h, with timestamps) ---
    if news_items:
        news_lines = []
        for item in news_items[:4]:
            tag   = "🔵" if item.stream == "micro" else "🌐"
            ts    = f" · <i>{item.published_fmt}</i>" if item.published_fmt else ""
            news_lines.append(
                f"{tag} <b>{item.title}</b>{ts}\n"
                f"   <i>{item.source}</i>"
            )
        news_block = "\n\n".join(news_lines)
    else:
        news_block = i18n.get("no_news", lang=lang)

    # --- Sentiment block ---
    ai_status = "⏳ WAIT" if sentiment.direction == "WAIT" else f"🎯 {sentiment.direction}"
    sentiment_block = (
        f"<b>{ai_status}</b> (Confidence: {sentiment.confidence}/10)\n"
        f"<i>{sentiment.reasoning}</i>"
    )

    # --- Dynamic Risk block (market-structure-based) ---
    if dyn_result:
        direction_str = i18n.get("long" if dyn_result.direction == "LONG" else "short", lang=lang)
        is_long = dyn_result.direction == "LONG"

        # Direction-aware SL label
        sl_label = i18n.get("sl_basis_long" if is_long else "sl_basis_short", lang=lang)

        # Direction-aware TP label
        if dyn_result.rr_forced:
            tp_label = i18n.get("tp_forced", lang=lang, rr=f"{dyn_result.rr_ratio:.1f}")
        else:
            tp_label = i18n.get("tp_basis_long" if is_long else "tp_basis_short", lang=lang)

        risk_block = (
            f"🔷 {i18n.get('direction', lang=lang)}: {direction_str}\n"
            f"💼 {i18n.get('balance', lang=lang)}: ${balance:,.2f}  ·  Risk {risk_pct}%  →  <b>${dyn_result.risk_amount_usd:,.2f}</b>\n"
            f"📍 Entry: ${price_data['last']:,.4f}\n"
            f"🛑 SL: <b>${dyn_result.stop_loss_price:,.4f}</b>"
            f"  <i>({sl_label})</i>\n"
            f"🏆 TP: <b>${dyn_result.take_profit_price:,.4f}</b>"
            f"  <i>({tp_label})</i>\n"
            f"📊 {i18n.get('rr_ratio', lang=lang)}: <b>1:{dyn_result.rr_ratio:.1f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 {i18n.get('position_size', lang=lang)}: <b>{dyn_result.position_size_units:,.6f} {coin}</b>\n"
            f"💵 {i18n.get('notional', lang=lang)}: <b>${dyn_result.position_value_usd:,.2f}</b>\n"
            f"🏦 {i18n.get('margin', lang=lang)}: <b>${dyn_result.margin_usd:,.2f}</b>\n"
            f"⛓ {i18n.get('margin_type', lang=lang)}: <b>{i18n.get(dyn_result.margin_type.lower(), lang=lang)}</b> {i18n.get('recommended', lang=lang)} 🛡\n"
            f"⚡ {i18n.get('leverage', lang=lang)}: <b>{dyn_result.recommended_leverage}x</b>"
        )
    else:
        risk_block = i18n.get("risk_unavailable", lang=lang)

    # --- Full report ---
    if sentiment.direction == "WAIT":
        report = (
            f"🐉 <b>{i18n.get('report_title', lang=lang, coin=coin)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{i18n.get('section_price', lang=lang)}\n{price_block}\n\n"
            f"{i18n.get('section_structure', lang=lang)}\n{structure_block}\n\n"
            f"{i18n.get('section_news', lang=lang)}\n{news_block}\n\n"
            f"🛑 <b>Dragon advises to WAIT:</b>\n"
            f"<i>{sentiment.reasoning}</i>\n\n"
            f"<i>⚠️ {i18n.get('disclaimer', lang=lang)}</i>"
        )
    else:
        report = (
            f"🐉 <b>{i18n.get('report_title', lang=lang, coin=coin)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{i18n.get('section_price', lang=lang)}\n{price_block}\n\n"
            f"{i18n.get('section_structure', lang=lang)}\n{structure_block}\n\n"
            f"{i18n.get('section_news', lang=lang)}\n{news_block}\n\n"
            f"🧠 <b>AI Decision:</b>\n{sentiment_block}\n\n"
            f"{i18n.get('section_risk', lang=lang)}\n{risk_block}\n\n"
            f"<i>⚠️ {i18n.get('disclaimer', lang=lang)}</i>"
        )

    await status_msg.delete()
    await update.message.reply_html(report)


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
                        dyn_result = None
                        prof = {"balance": 1000.0, "risk_percent": 2.0} # Fallback
                        
                        if mkt_structure.atr_14:
                            admin_id = config.ADMIN_CHAT_ID
                            if admin_id and str(admin_id).lstrip('-').isdigit():
                                prof = get_user_profile(int(admin_id))
                                
                            try:
                                dyn_result = calculate_dynamic_position(
                                    balance=prof["balance"],
                                    risk_percent=prof["risk_percent"],
                                    entry_price=current_price,
                                    support=mkt_structure.support,
                                    resistance=mkt_structure.resistance,
                                    atr_14=mkt_structure.atr_14,
                                    ai_direction=sentiment.direction
                                )
                            except Exception as e:
                                logger.warning(f"Watcher dynamic risk calc error for {coin}: {e}")

                        from modules.i18n import i18n
                        
                        msg = f"{i18n.get('watcher.signal_header')}\n\n"
                        msg += f"{i18n.get('watcher.triggered', coin=coin)}\n"
                        msg += f"{i18n.get('watcher.ai_decision', direction=sentiment.direction, confidence=sentiment.confidence)}\n"
                        msg += f"<i>{sentiment.reasoning}</i>\n\n"
                        
                        if dyn_result:
                            msg += f"{i18n.get('watcher.risk_profile_title')}\n"
                            msg += f"{i18n.get('watcher.balance_risk', balance=f'{prof['balance']:,.2f}', risk_percent=prof['risk_percent'])}\n"
                            msg += f"{i18n.get('watcher.entry', entry=f'{current_price:,.4f}')}\n"
                            msg += f"{i18n.get('watcher.sl', sl=f'{dyn_result.stop_loss_price:,.4f}')}\n"
                            msg += f"{i18n.get('watcher.tp', tp=f'{dyn_result.take_profit_price:,.4f}', rr_ratio=f'{dyn_result.rr_ratio:.1f}')}\n"
                            msg += f"{i18n.get('watcher.size_margin', size=f'{dyn_result.position_size_units:,.6f}', coin=coin, margin=f'{dyn_result.margin_usd:,.2f}')}\n"
                            
                            admin_lang = _lang(int(config.ADMIN_CHAT_ID)) if config.ADMIN_CHAT_ID and str(config.ADMIN_CHAT_ID).lstrip('-').isdigit() else "en"
                            msg += f"⛓ {i18n.get('margin_type', lang=admin_lang)}: <b>{i18n.get(dyn_result.margin_type.lower(), lang=admin_lang)}</b> {i18n.get('recommended', lang=admin_lang)} 🛡\n"
                            
                            msg += f"{i18n.get('watcher.leverage', leverage=dyn_result.recommended_leverage)}"

                        if config.ADMIN_CHAT_ID:
                            await app.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
                        else:
                            logger.warning(f"No ADMIN_CHAT_ID found in config. Cannot send alert for {coin}.")
                    else:
                        print(f"[{coin}] Silently passed. Reason: {sentiment.direction}, Conf: {sentiment.confidence}")

                except Exception as e:
                    logger.error(f"Error watching {coin}: {e}")
                    await asyncio.sleep(5)  # Brief backoff on per-coin errors

        except Exception as e:
            logger.error(f"Market watcher loop error: {e}")

        # Sleep Cycle
        await asyncio.sleep(MONITOR_INTERVAL)


# ── Helpers ───────────────────────────────────────────────────

def _fng_emoji(value: int | None) -> str:
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
    app.add_handler(CommandHandler("price",    price_command))
    app.add_handler(CommandHandler("risk",     risk_command))
    app.add_handler(CommandHandler("analyze",  analyze_command))
    app.add_handler(CommandHandler("set_balance", set_balance_command))
    app.add_handler(CommandHandler("set_risk", set_risk_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("stats",    stats_command))
    app.add_handler(CommandHandler("guide",    guide_command))
    app.add_handler(CommandHandler("academy",  guide_command))

    # Inline-keyboard callback: language selector buttons
    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^setlang_"))
    
    # Inline-keyboard callback: about
    app.add_handler(CallbackQueryHandler(about_callback, pattern=r"^action_about$"))

    logger.info("Handlers registered. Starting polling…")

    # Python 3.14 compatibility: create and set the event loop explicitly
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
