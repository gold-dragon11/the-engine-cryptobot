import asyncio
from binance import AsyncClient
import config

class BinanceStreamer:
    def __init__(self):
        self.api_key = config.BINANCE_API_KEY
        self.api_secret = config.BINANCE_API_SECRET
        self.tickers = ['BTCUSDT', 'SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']

    async def fetch_all_prices(self):
        # Deferred import to prevent circular dependency
        from main import db
        
        client = await AsyncClient.create(self.api_key, self.api_secret)
        try:
            tasks = [client.get_symbol_ticker(symbol=t) for t in self.tickers]
            results = await asyncio.gather(*tasks)
            
            for res in results:
                ticker = res['symbol']
                price = float(res['price'])
                db.update_market_price(ticker, price)
                
            return results
        finally:
            await client.close_connection()
