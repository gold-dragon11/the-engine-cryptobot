import logging
from binance import AsyncClient
import config

logger = logging.getLogger(__name__)

def calculate_ema(prices, period=200):
    """
    Calculates the Exponential Moving Average in pure Python.
    """
    if not prices or len(prices) < period:
        return prices[-1] if prices else 0.0

    # Start with simple moving average as the initial EMA seed
    sma = sum(prices[:period]) / period
    multiplier = 2 / (period + 1)
    ema = sma

    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return ema

async def check_btc_trend():
    """
    Fetches the last 250 closing prices for BTCUSDT (1h), counts EMA 200,
    and returns 'BULLISH' if Price > EMA else 'BEARISH'.
    If it fails, defaults to 'BEARISH'.
    """
    try:
        from main import db
        client = await AsyncClient.create(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
        
        try:
            klines = await client.get_klines(symbol='BTCUSDT', interval=AsyncClient.KLINE_INTERVAL_1HOUR, limit=250)
            
            # The close price is the 4th element in a kline list index[4]
            prices = [float(k[4]) for k in klines]
            
            if not prices:
                raise ValueError("No price data returned")
                
            current_price = prices[-1]
            ema_200 = calculate_ema(prices, period=200)
            
            trend = "BULLISH" if current_price > ema_200 else "BEARISH"
            logger.info(f"Market Analyzer: BTC at {current_price:.2f}, EMA200 at {ema_200:.2f}. Calculated Trend: {trend}")
            
        finally:
            await client.close_connection()

        # Update BTC trend in DB
        db.update_market_trend('BTCUSDT', trend)
        
        # Altcoins derived state
        alt_trend = "WAITING" if trend == "BEARISH" else "BULLISH"
        altcoins = ['SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']
        for alt in altcoins:
            db.update_market_trend(alt, alt_trend)

        return trend

    except Exception as e:
        logger.warning(f"⚠️ BTC Guard failed ({e}), defaulting to BEARISH.")
        from main import db
        # Safety default update for DB
        try:
            db.update_market_trend('BTCUSDT', 'BEARISH')
            altcoins = ['SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']
            for alt in altcoins:
                db.update_market_trend(alt, 'WAITING')
        except Exception as inner_e:
            logger.error(f"Failed to set safety fallback defaults in DB: {inner_e}")
            
        return "BEARISH"
