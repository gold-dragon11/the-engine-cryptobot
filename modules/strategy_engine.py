import logging
import time
from modules.finance import fetch_market_structure
from modules.ai_analyzer import analyze_strategy
from modules.risk_manager import calculate_dynamic_position

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
                    # Risk Management Integration: calculate risk based on 5% of $1000
                    risk_result = calculate_dynamic_position(
                        balance=1000.0,
                        risk_percent=5.0,
                        entry_price=current_price,
                        support=mkt_struct.support,
                        resistance=mkt_struct.resistance,
                        atr_14=mkt_struct.atr_14 or 0.001,
                        ai_direction=trade_type
                    )
                    
                    tp = float(decision_data.get("tp", risk_result.take_profit_price))
                    sl = float(decision_data.get("sl", risk_result.stop_loss_price))

                    # Multi-TP Calculation (for the virtual ledger)
                    dist = tp - current_price
                    tp1 = current_price + (dist * 0.33)
                    tp2 = current_price + (dist * 0.66)
                    tp3 = tp

                    # Safely insert the finalized signal (now as PENDING for virtual tracker)
                    if tp > 0 and sl > 0:
                        db.add_signal(alt, trade_type, current_price, tp1, tp2, tp3, sl)
                        logger.info(f"🚀 SIGNAL GENERATED: {alt} | Type: {trade_type} | TP3: {tp3:.4f} | SL: {sl:.4f} | AI Comment: {decision_data.get('comment')}")
                        
                        from modules.notifier import send_signal_alert
                        send_signal_alert({
                            "ticker": alt,
                            "type": trade_type,
                            "entry_price": current_price,
                            "tp1": tp1,
                            "tp2": tp2,
                            "tp3": tp3,
                            "sl": sl,
                            "comment": decision_data.get('comment', '')
                        })
                        
                except Exception as e:
                    logger.warning(f"Strategy Brain: Risk calculation failed for {alt} - {e}")
            else:
                logger.info(f"🧠 Strategy Brain: Gemini decided WAIT for {alt}. Reason: {decision_data.get('comment')}")
