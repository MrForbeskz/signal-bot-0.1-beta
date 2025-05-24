import logging
import asyncio
from typing import List, Dict, Optional
from binance.async_client import AsyncClient
from binance.streams import BinanceSocketManager
import pandas as pd
from config import (
    BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_FUTURES_BASE_URL_REST,
    VOLUME_THRESHOLD_USD, KLINE_LIMIT, TIMEFRAME
)

logger = logging.getLogger(__name__)

class BinanceHandler:
    def __init__(self):
        """Initialize Binance handler with connection management"""
        self.is_testnet = "testnet" in BINANCE_FUTURES_BASE_URL_REST
        self.client = None
        self.bsm = None
        self.conn_keys = {}
        self.monitored_symbols_details = {}
        self._connection_lock = asyncio.Lock()

    async def initialize_client(self):
        """Initialize async client with proper error handling"""
        if self.client is None:
            async with self._connection_lock:
                if self.client is None:  # Double-check pattern
                    try:
                        self.client = await AsyncClient.create(
                            BINANCE_API_KEY, 
                            BINANCE_API_SECRET, 
                            testnet=self.is_testnet
                        )
                        self.bsm = BinanceSocketManager(self.client)
                        logger.info(f"Binance client initialized (testnet: {self.is_testnet})")
                    except Exception as e:
                        logger.error(f"Failed to initialize Binance client: {e}")
                        raise

    async def ensure_client(self):
        """Ensure client is initialized"""
        if self.client is None:
            await self.initialize_client()

    async def get_tradable_futures_symbols(self, max_retries: int = 3) -> List[str]:
        """
        Get list of tradable USDT futures symbols with retry logic
        
        Args:
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            List[str]: List of tradable symbol names
        """
        await self.ensure_client()
        
        for attempt in range(max_retries):
            try:
                exchange_info = await self.client.futures_exchange_info()
                symbols = [
                    s['symbol'] for s in exchange_info['symbols']
                    if (s['quoteAsset'] == 'USDT' and 
                        s['status'] == 'TRADING' and 
                        s['contractType'] == 'PERPETUAL')
                ]
                
                logger.info(f"Found {len(symbols)} tradable USDT futures symbols")
                return symbols
                
            except Exception as e:
                logger.error(f"Error getting futures symbols (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("Max retries reached for getting futures symbols")
                    return []

    async def filter_symbols_by_volume(self, symbols: List[str], max_retries: int = 3) -> List[str]:
        """
        Filter symbols by 24h volume threshold
        
        Args:
            symbols (List[str]): List of symbols to filter
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            List[str]: Filtered symbols that meet volume criteria
        """
        await self.ensure_client()
        
        if not symbols:
            logger.warning("No symbols provided for volume filtering")
            return []

        filtered_symbols = []
        
        for attempt in range(max_retries):
            try:
                # Get 24hr ticker statistics for all symbols
                ticker_stats = await self.client.futures_ticker()
                
                # Create a dictionary for quick lookup
                ticker_dict = {ticker['symbol']: ticker for ticker in ticker_stats}
                
                for symbol in symbols:
                    if symbol in ticker_dict:
                        ticker = ticker_dict[symbol]
                        try:
                            # Calculate 24h volume in USD
                            volume_usdt = float(ticker['quoteVolume'])
                            
                            if volume_usdt >= VOLUME_THRESHOLD_USD:
                                filtered_symbols.append(symbol)
                                logger.debug(f"{symbol}: ${volume_usdt:,.0f} volume (INCLUDED)")
                            else:
                                logger.debug(f"{symbol}: ${volume_usdt:,.0f} volume (excluded)")
                                
                        except (ValueError, KeyError) as e:
                            logger.warning(f"Error processing volume for {symbol}: {e}")
                            continue
                    else:
                        logger.warning(f"Symbol {symbol} not found in ticker data")
                
                logger.info(f"Filtered {len(filtered_symbols)} symbols from {len(symbols)} "
                           f"by volume threshold ${VOLUME_THRESHOLD_USD:,}")
                
                return filtered_symbols
                
            except Exception as e:
                logger.error(f"Error filtering symbols by volume (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error("Max retries reached for volume filtering")
                    return []

    async def get_initial_klines(self, symbol: str, max_retries: int = 3) -> pd.DataFrame:
        """
        Get initial historical kline data for a symbol
        
        Args:
            symbol (str): Symbol to get data for
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            pd.DataFrame: DataFrame with historical kline data
        """
        await self.ensure_client()
        
        for attempt in range(max_retries):
            try:
                # Get historical klines
                klines = await self.client.futures_klines(
                    symbol=symbol,
                    interval=TIMEFRAME,
                    limit=KLINE_LIMIT
                )
                
                if not klines:
                    logger.warning(f"No kline data received for {symbol}")
                    return pd.DataFrame()

                # Convert to DataFrame
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                
                # Convert data types
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                # Keep only needed columns
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                logger.debug(f"Loaded {len(df)} historical klines for {symbol}")
                return df
                
            except Exception as e:
                logger.error(f"Error getting initial klines for {symbol} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Max retries reached for getting klines for {symbol}")
                    return pd.DataFrame()

    async def get_open_interest(self, symbol: str, max_retries: int = 3) -> Optional[float]:
        """
        Get current open interest for a symbol
        
        Args:
            symbol (str): Symbol to get open interest for
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            Optional[float]: Current open interest value or None if failed
        """
        await self.ensure_client()
        
        for attempt in range(max_retries):
            try:
                oi_data = await self.client.futures_open_interest(symbol=symbol)
                open_interest = float(oi_data['openInterest'])
                logger.debug(f"Open interest for {symbol}: {open_interest}")
                return open_interest
                
            except Exception as e:
                logger.error(f"Error getting open interest for {symbol} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Max retries reached for getting open interest for {symbol}")
                    return None

    async def get_symbol_details(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get detailed information about symbols including current prices and volumes
        
        Args:
            symbols (List[str]): List of symbols to get details for
            
        Returns:
            Dict[str, Dict]: Dictionary with symbol details
        """
        await self.ensure_client()
        
        try:
            ticker_stats = await self.client.futures_ticker()
            symbol_details = {}
            
            for ticker in ticker_stats:
                symbol = ticker['symbol']
                if symbol in symbols:
                    symbol_details[symbol] = {
                        'price': float(ticker['lastPrice']),
                        'volume_24h': float(ticker['volume']),
                        'quote_volume_24h': float(ticker['quoteVolume']),
                        'price_change_24h': float(ticker['priceChangePercent']),
                        'high_24h': float(ticker['highPrice']),
                        'low_24h': float(ticker['lowPrice'])
                    }
            
            logger.info(f"Retrieved details for {len(symbol_details)} symbols")
            return symbol_details
            
        except Exception as e:
            logger.error(f"Error getting symbol details: {e}")
            return {}

    async def close_connection(self):
        """Close the Binance client connection"""
        if self.client:
            await self.client.close_connection()
            logger.info("Binance client connection closed")
            self.client = None
            self.bsm = None