# ============================================================
#  modules/data_streamer.py
#  FIX: Replaced python-binance (not in requirements.txt / not installed)
#       with ccxt public-mode calls so prices actually update in the DB.
# ============================================================

import asyncio
import logging
import ccxt

logger = logging.getLogger(__name__)

TICKERS_CCXT   = ['BTC/USDT', 'SOL/USDT', 'TAO/USDT', 'ONDO/USDT', 'RENDER/USDT', 'PEPE/USDT', 'TON/USDT']
# Map ccxt symbol → DB ticker key
_SYMBOL_TO_DB  = {
    'BTC/USDT':    'BTCUSDT',
    'SOL/USDT':    'SOLUSDT',
    'TAO/USDT':    'TAOUSDT',
    'ONDO/USDT':   'ONDOUSDT',
    'RENDER/USDT': 'RENDERUSDT',
    'PEPE/USDT':   'PEPEUSDT',
    'TON/USDT':    'TONUSDT',
}


def _fetch_prices_sync() -> dict:
    """Synchronous ccxt price fetch for all tracked tickers. Returns {db_ticker: price}."""
    exchange = ccxt.binance({"enableRateLimit": True})
    prices = {}
    for symbol in TICKERS_CCXT:
        try:
            ticker = exchange.fetch_ticker(symbol)
            db_key = _SYMBOL_TO_DB[symbol]
            prices[db_key] = float(ticker["last"])
        except Exception as exc:
            logger.warning("Streamer: failed to fetch %s — %s", symbol, exc)
    return prices


class BinanceStreamer:
    async def fetch_all_prices(self):
        """Fetch all ticker prices via ccxt and persist them in the DB."""
        from main import db

        loop = asyncio.get_event_loop()
        prices = await loop.run_in_executor(None, _fetch_prices_sync)

        for db_ticker, price in prices.items():
            db.update_market_price(db_ticker, price)

        price_str = "  ".join(f"{k}={v:.4f}" for k, v in prices.items())
        logger.info("📡 Streamer prices updated: %s", price_str)
        return prices
