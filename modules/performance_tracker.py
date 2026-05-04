import asyncio
import logging
from datetime import datetime
from modules.notifier import send_ledger_entry, send_ledger_close

logger = logging.getLogger(__name__)

async def run_performance_tracker(db):
    """
    Background loop that monitors PENDING and ACTIVE virtual trades.
    Runs every 30 seconds to sync with the Binance streamer frequency.
    """
    logger.info("📈 Virtual Performance Ledger Active.")
    
    while True:
        try:
            # 1. Fetch live prices from the DB (populated by Streamer)
            prices = db.get_market_prices()
            
            # 2. Process PENDING signals -> ACTIVE
            pending = db.get_signals_by_status('PENDING')
            for sig in pending:
                ticker = sig['ticker']
                price = prices.get(ticker)
                if not price or price <= 0: continue
                
                entry = sig['entry_price']
                side = sig['type'] # LONG/SHORT
                
                triggered = False
                if side == 'LONG' and price <= entry:
                    triggered = True
                elif side == 'SHORT' and price >= entry:
                    triggered = True
                
                if triggered:
                    logger.info(f"📥 Entry triggered for {ticker} at {price}")
                    db.update_signal_status(sig['id'], 'ACTIVE', start_time=datetime.now())
                    send_ledger_entry(ticker)

            # 3. Process ACTIVE signals -> CLOSED (or move SL)
            active = db.get_signals_by_status('ACTIVE')
            for sig in active:
                ticker = sig['ticker']
                price = prices.get(ticker)
                if not price or price <= 0: continue

                side = sig['type']
                entry = sig['entry_price']
                tp1 = sig['tp1']
                tp3 = sig['tp3']
                sl = sig['sl']
                tp1_hit = bool(sig['tp1_hit'])
                
                closed = False
                pnl = 0.0
                
                if side == 'LONG':
                    # TP1 Hit? (Move SL to Breakeven)
                    if not tp1_hit and price >= tp1:
                        logger.info(f"🎯 {ticker} TP1 hit. Moving SL to breakeven.")
                        db.mark_tp1_hit(sig['id'], entry)
                    
                    # TP3 Hit? (Strict hit)
                    if price >= tp3:
                        closed = True
                        pnl = ((tp3 / entry) - 1) * 100
                    # SL Hit?
                    elif price <= sl:
                        closed = True
                        pnl = ((sl / entry) - 1) * 100
                
                elif side == 'SHORT':
                    if not tp1_hit and price <= tp1:
                        logger.info(f"🎯 {ticker} TP1 hit (SHORT). Moving SL to breakeven.")
                        db.mark_tp1_hit(sig['id'], entry)
                    
                    if price <= tp3:
                        closed = True
                        pnl = (1 - (tp3 / entry)) * 100
                    elif price >= sl:
                        closed = True
                        pnl = (1 - (sl / entry)) * 100
                        
                if closed:
                    pnl = round(pnl, 2)
                    logger.info(f"📊 {ticker} Closed. PnL: {pnl}%")
                    db.update_signal_status(sig['id'], 'CLOSED', close_time=datetime.now(), pnl=pnl)
                    send_ledger_close(ticker, pnl)

        except Exception as e:
            logger.error(f"Performance Tracker Error: {e}")
            
        await asyncio.sleep(30) # Sync with Streamer frequency
