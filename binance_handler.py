import logging
from binance.async_client import AsyncClient  # Используем AsyncClient
from binance.websocket import BinanceSocketManager
import pandas as pd
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_FUTURES_BASE_URL_REST, VOLUME_THRESHOLD_USD, KLINE_LIMIT, TIMEFRAME

logger = logging.getLogger(__name__)

class BinanceHandler:
    def __init__(self):
        is_testnet = "testnet" in BINANCE_FUTURES_BASE_URL_REST
        self.client = AsyncClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=is_testnet)  # Используем AsyncClient
        self.bsm = BinanceSocketManager(self.client)
        self.conn_keys = {}
        self.monitored_symbols_details = {}

    async def get_tradable_futures_symbols(self):
        """Получает список торгуемых фьючерсов USDT"""
        try:
            exchange_info = await self.client.futures_exchange_info()
            symbols = [
                s['symbol'] for s in exchange_info['symbols']
                if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING' and s['contractType'] == 'PERPETUAL'
            ]
            logger.info(f"Найдено {len(symbols)} торгуемых USDT фьючерсных символов.")
            return symbols
        except Exception as e:
            logger.error(f"Ошибка получения информации о фьючерсных символах: {e}")
            return []

    async def filter_symbols_by_volume(self, symbols):
        """Фильтрует символы по объему торгов"""
        filtered_symbols = []
        try:
            tickers = await self.client.futures_ticker()
            for ticker in tickers:
                symbol = ticker['symbol']
                if symbol in symbols:
                    volume_usd = float(ticker['quoteVolume'])
                    if volume_usd >= VOLUME_THRESHOLD_USD:
                        filtered_symbols.append(symbol)
                        self.monitored_symbols_details[symbol] = {'volume_24h_usd': volume_usd}
            logger.info(f"Отфильтровано {len(filtered_symbols)} символов по объему >= ${VOLUME_THRESHOLD_USD/1_000_000:.0f}M.")
            return filtered_symbols
        except Exception as e:
            logger.error(f"Ошибка фильтрации символов по объему: {e}")
            return []

    async def get_initial_klines(self, symbol):
        """Загружает исторические данные свечей"""
        try:
            klines = await self.client.futures_klines(
                symbol=symbol,
                interval=TIMEFRAME,
                limit=KLINE_LIMIT
            )
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
            ])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            logger.debug(f"Загружены начальные {len(df)} свечей для {symbol}.")
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            logger.error(f"Ошибка загрузки начальных свечей для {symbol}: {e}")
            return pd.DataFrame()