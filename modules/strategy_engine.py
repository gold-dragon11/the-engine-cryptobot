# ============================================================
#  modules/strategy_engine.py — Dragon Crypto Oracle
#
#  BUG-FIX LOG (Architecture Audit):
#  - FIX-01 (CRITICAL): Added CCXT symbol map. CCXT requires "SOL/USDT"
#    format; the DB/altcoin list uses "SOLUSDT". fetch_market_structure()
#    was receiving "SOLUSDT" and crashing with BadSymbol on every scan.
#  - FIX-02 (HIGH): Wrapped float()/int() casts for Gemini tp/sl/leverage
#    fields in try/except to guard against "N/A" or None responses.
#  - FIX-03 (MEDIUM): Added db.log_rejection() call in the DB anti-spam
#    branch so the daily reporter captures that category too.
#  - Deduplication guard, RSI window [30–70], detailed rejection logs.
# ============================================================

import logging
import time
from modules.finance import fetch_market_structure
from modules.ai_analyzer import analyze_strategy
from modules.risk_manager import calculate_trade_risk

logger = logging.getLogger(__name__)

# Minimum pause between consecutive Gemini calls (free-tier RPM guard).
_GEMINI_RATE_LIMIT_SLEEP = 5   # seconds

# RSI window that signals a tradeable setup.
RSI_MIN = 30
RSI_MAX = 70

# ── FIX-01: CCXT requires slash-format symbols ("SOL/USDT"), but the DB
#    and altcoin list use no-slash format ("SOLUSDT").
#    This map is the single source of truth for the conversion.
_DB_TO_CCXT: dict[str, str] = {
    'SOLUSDT':    'SOL/USDT',
    'TAOUSDT':    'TAO/USDT',
    'ONDOUSDT':   'ONDO/USDT',
    'RENDERUSDT': 'RENDER/USDT',
    'PEPEUSDT':   'PEPE/USDT',
    'TONUSDT':    'TON/USDT',
}


def _safe_float(value, default: float = 0.0) -> float:
    """FIX-02: Safely cast a Gemini response field to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 1) -> int:
    """FIX-02: Safely cast a Gemini response field to int."""
    try:
        return int(float(value))   # handles "3.0" strings too
    except (TypeError, ValueError):
        return default


def process_market_signals():
    """
    Core strategy brain — runs every 30 minutes via run_in_executor.
    1. Check BTC Trend. If BEARISH / WAITING, skip all.
    2. Check Active Signals count. If >= 3, skip all.
    3. Evaluate altcoins (RSI/market structure).
    4. Gemini Audit.
    5. Calculate risk & DB insert.
    """
    logger.info("🧠 Strategy Brain: ── Starting 30-min market scan ──────────────")

    from main import db

    # ── Activation gate ──────────────────────────────────────────────────────
    if not db.is_bot_activated():
        logger.info("🧠 REJECTED [ALL]: Bot is inactive. Send /start to activate.")
        return

    # ── Fetch current DB snapshot ────────────────────────────────────────────
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, current_price, trend_direction FROM market_state")
    rows = cursor.fetchall()
    conn.close()

    market_data = {row[0]: {"price": row[1], "trend": row[2]} for row in rows}

    # ── CHECK 1: BTC Trend Guard ─────────────────────────────────────────────
    btc_state = market_data.get('BTCUSDT')
    if not btc_state:
        logger.info("🧠 REJECTED [ALL]: BTCUSDT not found in market_state table.")
        return
    if btc_state['trend'] != 'BULLISH':
        logger.info(
            "🧠 REJECTED [ALL]: BTC trend is '%s' (need BULLISH). Holding no new signals.",
            btc_state['trend'],
        )
        return

    # ── CHECK 2: Active Signals Cap ──────────────────────────────────────────
    active_count = db.get_active_signals_count()
    if active_count >= 3:
        logger.info("🧠 REJECTED [ALL]: Max open signals reached (%d/3). Holding.", active_count)
        return

    # ── Per-cycle deduplication set ──────────────────────────────────────────
    _scanned_this_cycle: set = set()

    altcoins = list(_DB_TO_CCXT.keys())   # ['SOLUSDT', 'TAOUSDT', ...]

    for alt in altcoins:

        # ── Re-check signal cap per iteration ────────────────────────────
        if db.get_active_signals_count() >= 3:
            logger.info("🧠 REJECTED [%s]: Max signals reached mid-scan.", alt)
            break

        # ── Deduplication guard ───────────────────────────────────────────
        if alt in _scanned_this_cycle:
            logger.info("🧠 SKIPPED  [%s]: Already scanned this cycle — duplicate guard.", alt)
            continue
        _scanned_this_cycle.add(alt)

        # ── One active trade per ticker ───────────────────────────────────
        if db.has_active_trade(alt):
            reason = f"Active trade already open in DB"
            logger.info("🧠 REJECTED [%s]: %s.", alt, reason)
            db.log_rejection(alt, reason)   # FIX-03: was missing
            continue

        # ── Market data freshness ─────────────────────────────────────────
        state = market_data.get(alt)
        if not state or state['price'] <= 0.0:
            reason = f"Price is zero/missing in DB for {alt}"
            logger.info("🧠 REJECTED [%s]: %s (streamer may not have run yet).", alt, reason)
            db.log_rejection(alt, reason)
            continue

        current_price = state['price']

        # ── FIX-01: Convert DB ticker to CCXT symbol format ───────────────
        ccxt_symbol = _DB_TO_CCXT.get(alt)
        if not ccxt_symbol:
            logger.warning("🧠 REJECTED [%s]: No CCXT symbol mapping defined.", alt)
            continue

        # ── Market structure fetch (using correct CCXT symbol) ────────────
        mkt_struct = fetch_market_structure(ccxt_symbol)
        if not mkt_struct:
            reason = "fetch_market_structure returned None"
            logger.info("🧠 REJECTED [%s]: %s.", alt, reason)
            db.log_rejection(alt, reason)
            continue
        if mkt_struct.rsi_14 is None:
            reason = "RSI(14) unavailable"
            logger.info("🧠 REJECTED [%s]: %s (ta library or data issue).", alt, reason)
            db.log_rejection(alt, reason)
            continue

        rsi = mkt_struct.rsi_14

        # ── RSI filter ────────────────────────────────────────────────────
        if not (RSI_MIN <= rsi <= RSI_MAX):
            reason = f"RSI {rsi:.1f} outside window [{RSI_MIN}–{RSI_MAX}]"
            logger.info("🧠 REJECTED [%s]: %s.", alt, reason)
            db.log_rejection(alt, reason)
            continue

        logger.info(
            "🧠 SETUP    [%s]: RSI=%.1f  Support=%.4f  Resistance=%.4f  Price=%.4f — sending to Gemini…",
            alt, rsi, mkt_struct.support, mkt_struct.resistance, current_price,
        )

        # ── Gemini Final Audit ────────────────────────────────────────────
        decision_data = analyze_strategy(
            ticker=alt,
            price=current_price,
            btc_trend=btc_state['trend'],
            support=mkt_struct.support,
            resistance=mkt_struct.resistance,
            atr=mkt_struct.atr_14 or 0.0,
            rsi=rsi,
        )

        # Rate-limit guard: pause after every Gemini call.
        logger.debug("🕐 Rate-limit pause: %ds after Gemini call for %s", _GEMINI_RATE_LIMIT_SLEEP, alt)
        time.sleep(_GEMINI_RATE_LIMIT_SLEEP)

        gemini_decision = str(decision_data.get("decision", "WAIT")).upper()
        gemini_comment  = str(decision_data.get("comment", "No comment"))

        if gemini_decision != "GO":
            reason = f"Gemini said {gemini_decision}: {gemini_comment[:80]}"
            logger.info("🧠 REJECTED [%s]: Gemini said '%s'. Reason: %s", alt, gemini_decision, gemini_comment)
            db.log_rejection(alt, reason)
            continue

        # ── Direction & Risk Calculation ─────────────────────────────────
        trade_type = str(decision_data.get("type", "LONG")).upper()
        if trade_type not in ("LONG", "SHORT"):
            reason = f"Gemini returned invalid trade type: '{trade_type}'"
            logger.warning("🧠 REJECTED [%s]: %s", alt, reason)
            db.log_rejection(alt, reason)
            continue

        try:
            risk_result = calculate_trade_risk(
                entry_price=current_price,
                support=mkt_struct.support,
                resistance=mkt_struct.resistance,
                atr_14=mkt_struct.atr_14 or 0.001,
                ai_direction=trade_type,
            )
        except Exception as exc:
            reason = f"Risk calculation error: {exc}"
            logger.warning("🧠 REJECTED [%s]: %s", alt, reason)
            db.log_rejection(alt, reason)
            continue

        # ── FIX-02: Safe cast of Gemini TP/SL/Leverage fields ────────────
        ai_tp    = _safe_float(decision_data.get("tp"),       0.0)
        ai_sl    = _safe_float(decision_data.get("sl"),       0.0)
        leverage = _safe_int(decision_data.get("leverage"),   1)

        if trade_type == "LONG":
            tp = max(ai_tp, risk_result.take_profit) if ai_tp > 0 else risk_result.take_profit
            sl = ai_sl if 0 < ai_sl < current_price else risk_result.stop_loss
        else:
            tp = min(ai_tp, risk_result.take_profit) if ai_tp > 0 else risk_result.take_profit
            sl = ai_sl if ai_sl > current_price else risk_result.stop_loss

        # ── Hard R/R Block ────────────────────────────────────────────────
        actual_risk      = current_price - sl   if trade_type == "LONG" else sl - current_price
        potential_reward = tp - current_price   if trade_type == "LONG" else current_price - tp
        rr_ratio         = potential_reward / actual_risk if actual_risk > 0 else 0

        if rr_ratio < 1.5:
            reason = f"R/R={rr_ratio:.2f} < 1.5 (TP={tp:.4f} SL={sl:.4f})"
            logger.warning("🧠 REJECTED [%s]: %s. Trade structurally unfavorable.", alt, reason)
            db.log_rejection(alt, reason)
            continue

        # ── Multi-TP Calculation ──────────────────────────────────────────
        if trade_type == "LONG":
            dist = tp - current_price
            tp1, tp2, tp3 = current_price + dist * 0.33, current_price + dist * 0.66, tp
        else:
            dist = current_price - tp
            tp1, tp2, tp3 = current_price - dist * 0.33, current_price - dist * 0.66, tp

        # ── Insert signal & fire Telegram alert ──────────────────────────
        if tp > 0 and sl > 0:
            db.add_signal(alt, trade_type, current_price, tp1, tp2, tp3, sl)
            logger.info(
                "🚀 SIGNAL   [%s]: %s | Entry=%.4f | TP=%.4f | SL=%.4f | R/R=1:%.2f | Leverage=%dx | %s",
                alt, trade_type, current_price, tp, sl, rr_ratio, leverage, gemini_comment,
            )

            from modules.notifier import send_signal_alert
            send_signal_alert({
                "ticker":      alt,
                "type":        trade_type,
                "entry_price": current_price,
                "tp":          tp,
                "sl":          sl,
                "rr_ratio":    rr_ratio,
                "leverage":    leverage,
                "comment":     gemini_comment,
            })
        else:
            reason = f"Final TP={tp:.4f} or SL={sl:.4f} resolved to zero"
            logger.warning("🧠 REJECTED [%s]: %s — skipping DB insert.", alt, reason)
            db.log_rejection(alt, reason)

    logger.info("🧠 Strategy Brain: ── Scan complete ─────────────────────────────")
