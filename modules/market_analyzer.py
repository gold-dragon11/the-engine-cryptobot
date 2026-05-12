# ============================================================
#  modules/market_analyzer.py
#  BTC Trend Guard — uses ccxt (already in requirements.txt)
#  FIX: Removed python-binance dependency (was never installed).
# ============================================================

import logging
import asyncio
import ccxt
import config

logger = logging.getLogger(__name__)


def calculate_ema(prices: list, period: int = 200) -> float:
    """
    Calculates the Exponential Moving Average in pure Python.
    Returns last price as fallback when not enough data.
    """
    if not prices or len(prices) < period:
        logger.warning(
            "EMA(%d): not enough data (%d bars). Using last close as fallback.",
            period, len(prices) if prices else 0,
        )
        return prices[-1] if prices else 0.0

    sma = sum(prices[:period]) / period
    multiplier = 2 / (period + 1)
    ema = sma
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _fetch_btc_klines_sync() -> list:
    """
    Synchronous ccxt fetch of 250 x 1h BTC/USDT candles.
    Returns list of close prices.
    """
    exchange = ccxt.binance({"enableRateLimit": True})
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=250)
    return [float(c[4]) for c in ohlcv]   # index 4 = close price


async def check_btc_trend() -> str:
    """
    Fetches the last 250 x 1h closing prices for BTC/USDT via ccxt,
    computes EMA-200, and returns 'BULLISH' (price > EMA) or 'BEARISH'.
    Defaults to 'BEARISH' on any error so the system stays safe.
    """
    from main import db
    altcoins = ['SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']

    try:
        loop = asyncio.get_event_loop()
        prices = await loop.run_in_executor(None, _fetch_btc_klines_sync)

        if not prices:
            raise ValueError("Empty price list returned from Binance.")

        current_price = prices[-1]
        ema_200 = calculate_ema(prices, period=200)
        trend = "BULLISH" if current_price > ema_200 else "BEARISH"

        logger.info(
            "🛡️ BTC Guard: price=%.2f  EMA200=%.2f  → %s",
            current_price, ema_200, trend,
        )

        db.update_market_trend('BTCUSDT', trend)
        alt_trend = "BULLISH" if trend == "BULLISH" else "WAITING"
        for alt in altcoins:
            db.update_market_trend(alt, alt_trend)

        return trend

    except Exception as exc:
        logger.warning("⚠️ BTC Guard failed (%s) — defaulting to BEARISH.", exc)
        try:
            db.update_market_trend('BTCUSDT', 'BEARISH')
            for alt in altcoins:
                db.update_market_trend(alt, 'WAITING')
        except Exception as inner:
            logger.error("Failed to set safety fallback in DB: %s", inner)
        return "BEARISH"
