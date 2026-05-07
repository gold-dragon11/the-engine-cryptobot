import logging
import time
from modules.finance import fetch_market_structure
from modules.ai_analyzer import analyze_strategy
from modules.risk_manager import calculate_trade_risk

logger = logging.getLogger(__name__)

# Minimum pause between consecutive Gemini calls to stay within free-tier RPM limits.
_GEMINI_RATE_LIMIT_SLEEP = 5  # seconds

def process_market_signals():
    """
    Core strategy brain.
    1. Check BTC Trend. If BEARISH, skip all.
    2. Check Active Signals count. If >= 3, skip all.
    3. Evaluate altcoins (RSI/market structure).
    4. Gemini Audit.
    5. Calculate risk & db insert.
    """
    logger.info("🧠 Strategy Brain: Scanning for opportunities...")

    from main import db
    
    if not db.is_bot_activated():
        logger.info("🧠 Strategy Brain: Bot is inactive. Skipping scan.")
        return
    
    # 1. Fetch current state of all tickers
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, current_price, trend_direction FROM market_state")
    rows = cursor.fetchall()
    conn.close()

    market_data = {row[0]: {"price": row[1], "trend": row[2]} for row in rows}

    # CHECK 1: BTC Trend
    btc_state = market_data.get('BTCUSDT')
    if not btc_state or btc_state['trend'] == 'BEARISH':
        logger.info("🧠 Strategy Brain: BTC is BEARISH or Unknown. Halting new signals.")
        return

    # CHECK 2: Active Signals
    active_count = db.get_active_signals_count()
    if active_count >= 3:
        logger.info(f"🧠 Strategy Brain: Max signals reached ({active_count}/3). Halting.")
        return

    # Evaluate altcoins
    altcoins = ['SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']
    
    for alt in altcoins:
        if db.get_active_signals_count() >= 3:
            logger.info("🧠 Strategy Brain: Reached max signals during scan.")
            break

        # ── ONE ACTIVE TRADE PER TICKER LOCK ──────────────────────
        active_signals = db.get_signals_by_status('ACTIVE') + db.get_signals_by_status('PENDING')
        if any(s.get('ticker') == alt for s in active_signals):
            logger.info(f"Skipping {alt}: Active trade already exists.")
            continue

        state = market_data.get(alt)
        if not state or state['price'] <= 0.0:
            continue
            
        current_price = state['price']
        
        # Signal Trigger Logic: Fetch market structure
        mkt_struct = fetch_market_structure(alt)
        if not mkt_struct or mkt_struct.rsi_14 is None:
            continue
            
        rsi = mkt_struct.rsi_14
        
        # Setup Trigger: Look for bounces/pullbacks (RSI between 30 and 50)
        # We assume long bias since BTC is bullish.
        if 35 <= rsi <= 55:
            logger.info(f"🧠 Strategy Brain: Setup found for {alt} (RSI {rsi}). Sending Context to Gemini.")
            
            # Gemini Final Audit
            decision_data = analyze_strategy(
                ticker=alt,
                price=current_price,
                btc_trend=btc_state['trend'],
                support=mkt_struct.support,
                resistance=mkt_struct.resistance,
                atr=mkt_struct.atr_14 or 0.0,
                rsi=rsi
            )
            # Rate-limit guard: pause after every Gemini call to avoid 429 errors.
            logger.debug("🕐 Rate-limit pause: sleeping %ds after Gemini call for %s", _GEMINI_RATE_LIMIT_SLEEP, alt)
            time.sleep(_GEMINI_RATE_LIMIT_SLEEP)
            
            if decision_data.get("decision") == "GO":
                trade_type = str(decision_data.get("type", "LONG")).upper()
                
                try:
                    # Risk Management Integration — AUTHORITATIVE source for TP/SL
                    risk_result = calculate_trade_risk(
                        entry_price=current_price,
                        support=mkt_struct.support,
                        resistance=mkt_struct.resistance,
                        atr_14=mkt_struct.atr_14 or 0.001,
                        ai_direction=trade_type
                    )
                    
                    # Use risk manager's TP as the MINIMUM floor.
                    # The AI's TP is only accepted if it is MORE ambitious.
                    ai_tp = float(decision_data.get("tp", 0.0))
                    ai_sl = float(decision_data.get("sl", 0.0))
                    
                    if trade_type == "LONG":
                        tp = max(ai_tp, risk_result.take_profit) if ai_tp > 0 else risk_result.take_profit
                        sl = ai_sl if 0 < ai_sl < current_price else risk_result.stop_loss
                    else:  # SHORT
                        tp = min(ai_tp, risk_result.take_profit) if ai_tp > 0 else risk_result.take_profit
                        sl = ai_sl if ai_sl > current_price else risk_result.stop_loss
                    
                    leverage = int(decision_data.get("leverage", 1))
                    
                    # ── HARD R/R BLOCK — calculated on final TP/SL ────────
                    actual_risk = current_price - sl if trade_type == "LONG" else sl - current_price
                    potential_reward = tp - current_price if trade_type == "LONG" else current_price - tp
                    rr_ratio = potential_reward / actual_risk if actual_risk > 0 else 0

                    if rr_ratio < 1.5:
                        logger.warning(f"Trade aborted: R/R < 1.5 for {alt} (R/R={rr_ratio:.2f}, TP={tp:.4f}, SL={sl:.4f})")
                        continue

                    # Multi-TP Calculation (for the virtual ledger)
                    if trade_type == "LONG":
                        dist = tp - current_price
                        tp1 = current_price + (dist * 0.33)
                        tp2 = current_price + (dist * 0.66)
                        tp3 = tp
                    else:
                        dist = current_price - tp
                        tp1 = current_price - (dist * 0.33)
                        tp2 = current_price - (dist * 0.66)
                        tp3 = tp

                    # Safely insert the finalized signal (now as PENDING for virtual tracker)
                    if tp > 0 and sl > 0:
                        db.add_signal(alt, trade_type, current_price, tp1, tp2, tp3, sl)
                        logger.info(f"🚀 SIGNAL GENERATED: {alt} | Type: {trade_type} | TP: {tp:.4f} | SL: {sl:.4f} | R/R: 1:{rr_ratio:.2f} | AI Comment: {decision_data.get('comment')}")
                        
                        from modules.notifier import send_signal_alert
                        send_signal_alert({
                            "ticker": alt,
                            "type": trade_type,
                            "entry_price": current_price,
                            "tp": tp,
                            "sl": sl,
                            "rr_ratio": rr_ratio,
                            "leverage": leverage,
                            "comment": decision_data.get('comment', '')
                        })
                        
                except Exception as e:
                    logger.warning(f"Strategy Brain: Risk calculation failed for {alt} - {e}")
            else:
                logger.info(f"🧠 Strategy Brain: Gemini decided WAIT for {alt}. Reason: {decision_data.get('comment')}")

