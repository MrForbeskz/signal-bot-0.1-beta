import asyncio
import logging
import pandas as pd
from collections import deque
from datetime import datetime, timedelta
import signal
import sys
from binance.streams import BinanceSocketManager
from binance.async_client import AsyncClient

import config
from telegram_bot_handler import TelegramBotHandler
from binance_handler import BinanceHandler
from strategy import Strategy

# Настройка системы логирования
def setup_logging():
    """Настройка системы логирования"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = []
    
    # Всегда выводим в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(console_handler)
    
    # Если включено логирование в файл
    if config.LOG_TO_FILE:
        file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=log_format,
        handlers=handlers
    )

setup_logging()
logger = logging.getLogger(__name__)

class CryptoScalpingBot:
    def __init__(self):
        """Инициализация бота с всеми необходимыми компонентами"""
        # Хранилища данных
        self.symbol_kline_data = {}  # Исторические данные свечей
        self.symbol_open_interest_data = {}  # Данные открытого интереса
        self.last_signal_time = {}  # Отслеживание времени последнего сигнала (для cooldown)
        
        # Компоненты бота
        self.telegram_bot = TelegramBotHandler()
        self.binance_handler = BinanceHandler()
        self.strategy_checker = Strategy()
        
        # Состояние бота
        self.running = False
        self.reconnect_count = 0
        self.last_heartbeat = datetime.now()
        
        # WebSocket соединения
        self.client = None
        self.websocket_manager = None
        
        logger.info("Crypto Scalping Bot initialized")

    async def send_startup_message(self):
        """Отправляет сообщение о запуске бота"""
        startup_msg = (
            "🚀 *Crypto Scalping Bot Started*\n\n"
            f"Environment: {config.ENVIRONMENT.upper()}\n"
            f"Volume Filter: ${config.VOLUME_THRESHOLD_USD/1_000_000:.0f}M\n"
            f"Timeframe: {config.TIMEFRAME}\n"
            f"RSI Period: {config.RSI_PERIOD}\n"
            f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await self.telegram_bot.send_message(startup_msg)
        logger.info("Startup message sent")

    async def send_heartbeat(self):
        """Отправляет периодические обновления статуса бота"""
        current_time = datetime.now()
        if (current_time - self.last_heartbeat).total_seconds() >= config.HEARTBEAT_INTERVAL:
            active_symbols = len([s for s in self.symbol_kline_data.keys() 
                                if s in self.symbol_kline_data and len(self.symbol_kline_data[s]) > 0])
            
            status_msg = (
                f"💓 *Bot Status Update*\n\n"
                f"Active symbols: {active_symbols}\n"
                f"Reconnects: {self.reconnect_count}\n"
                f"Uptime: {current_time.strftime('%H:%M:%S')}\n"
                f"Environment: {config.ENVIRONMENT}\n"
                f"Memory usage: {len(self.symbol_kline_data)} symbols tracked"
            )
            await self.telegram_bot.send_message(status_msg)
            self.last_heartbeat = current_time
            logger.debug("Heartbeat sent")

    async def process_message(self, msg):
        """Обрабатывает сообщения из WebSocket"""
        try:
            stream_name = msg.get('stream', '')
            data = msg.get('data', {})
            event_type = data.get('e')

            if not event_type or not stream_name:
                logger.debug("Received message without event type or stream name")
                return

            # Извлекаем символ из названия стрима
            try:
                symbol = stream_name.split('@')[0].upper()
            except IndexError:
                logger.warning(f"Could not extract symbol from stream: {stream_name}")
                return

            # Обрабатываем разные типы событий
            if event_type == 'kline' and stream_name.endswith(f'@kline_{config.TIMEFRAME}'):
                await self.process_kline_data(symbol, data)
            elif event_type == 'forceOrder' and '@forceOrder' in stream_name:
                await self.process_open_interest_data(symbol, data)
            else:
                logger.debug(f"Unhandled event type: {event_type} for stream: {stream_name}")
                
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    async def process_kline_data(self, symbol, data):
        """Обрабатывает данные свечей (kline)"""
        try:
            kline_data = data.get('k')
            if not kline_data:
                logger.warning(f"No kline data in message for {symbol}")
                return

            # Проверяем, что свеча закрылась
            is_kline_closed = kline_data.get('x', False)
            if not is_kline_closed:
                logger.debug(f"Kline not closed yet for {symbol}")
                return

            # Парсим данные свечи
            try:
                new_kline_entry = {
                    'timestamp': pd.to_datetime(kline_data['t'], unit='ms'),
                    'open': float(kline_data['o']),
                    'high': float(kline_data['h']),
                    'low': float(kline_data['l']),
                    'close': float(kline_data['c']),
                    'volume': float(kline_data['v'])
                }
            except (KeyError, ValueError) as e:
                logger.error(f"Error parsing kline data for {symbol}: {e}")
                return

            # Проверяем, что у нас есть данные для этого символа
            if symbol not in self.symbol_kline_data:
                logger.warning(f"Symbol {symbol} not in tracked symbols")
                return

            # Добавляем новую свечу в очередь
            self.symbol_kline_data[symbol].append(new_kline_entry)
            logger.debug(f"Added new kline for {symbol}: close={new_kline_entry['close']}")
            
            # Создаем DataFrame для анализа
            klines_df = pd.DataFrame(list(self.symbol_kline_data[symbol]))
            
            # Получаем данные об открытом интересе
            current_oi_info = self.symbol_open_interest_data.get(symbol, {})
            current_oi = current_oi_info.get('current_oi')
            prev_oi = current_oi_info.get('prev_oi')

            # Проверяем cooldown (чтобы не спамить сигналами)
            if symbol in self.last_signal_time:
                time_since_last = (datetime.now() - self.last_signal_time[symbol]).total_seconds()
                if time_since_last < config.COOLDOWN_BETWEEN_SIGNALS:
                    logger.debug(f"Cooldown active for {symbol}: {time_since_last:.0f}s remaining")
                    return

            # Если у нас нет данных об открытом интересе, получаем их
            if current_oi is None:
                logger.debug(f"Getting initial open interest data for {symbol}")
                current_oi = await self.binance_handler.get_open_interest(symbol)
                if current_oi is not None:
                    self.symbol_open_interest_data[symbol] = {
                        'current_oi': current_oi,
                        'prev_oi': None,
                        'timestamp': datetime.now().timestamp()
                    }

            # Проверяем стратегию на сигнал
            signal = self.strategy_checker.process_kline_data(symbol, klines_df, current_oi, prev_oi)
            if signal:
                await self.telegram_bot.send_message(signal)
                self.last_signal_time[symbol] = datetime.now()
                logger.info(f"Trading signal sent for {symbol}")

            # Обновляем историю открытого интереса
            if current_oi is not None and symbol in self.symbol_open_interest_data:
                self.symbol_open_interest_data[symbol]['prev_oi'] = current_oi

        except Exception as e:
            logger.error(f"Error processing kline data for {symbol}: {e}")

    async def process_open_interest_data(self, symbol, data):
        """Обрабатывает данные открытого интереса из force order stream"""
        try:
            # Force order stream используется как прокси для изменений открытого интереса
            # Это не идеальное решение, но WebSocket для OI может быть нестабильным
            logger.debug(f"Force order event for {symbol} - updating OI data")
            
            # Получаем актуальные данные об открытом интересе через REST API
            current_oi = await self.binance_handler.get_open_interest(symbol)
            
            if current_oi is not None:
                # Обновляем данные открытого интереса
                if symbol not in self.symbol_open_interest_data:
                    self.symbol_open_interest_data[symbol] = {
                        'current_oi': current_oi,
                        'prev_oi': None,
                        'timestamp': datetime.now().timestamp()
                    }
                else:
                    # Сохраняем предыдущее значение
                    prev_oi = self.symbol_open_interest_data[symbol]['current_oi']
                    self.symbol_open_interest_data[symbol]['prev_oi'] = prev_oi
                    self.symbol_open_interest_data[symbol]['current_oi'] = current_oi
                    self.symbol_open_interest_data[symbol]['timestamp'] = datetime.now().timestamp()

                logger.debug(f"Updated open interest for {symbol}: {current_oi}")

        except Exception as e:
            logger.error(f"Error processing open interest data for {symbol}: {e}")

    async def initialize_symbols(self):
        """Инициализирует символы для мониторинга и загружает исторические данные"""
        logger.info("Starting symbol initialization...")
        
        try:
            # Получаем список символов для мониторинга
            if not config.SYMBOLS_TO_MONITOR:
                logger.info("Getting all tradable futures symbols...")
                all_symbols = await self.binance_handler.get_tradable_futures_symbols()
                if not all_symbols:
                    raise Exception("Failed to get tradable symbols")
                
                logger.info(f"Found {len(all_symbols)} tradable symbols, filtering by volume...")
                monitored_symbols = await self.binance_handler.filter_symbols_by_volume(all_symbols)
            else:
                monitored_symbols = config.SYMBOLS_TO_MONITOR
                logger.info(f"Using predefined symbols: {monitored_symbols}")

            if not monitored_symbols:
                logger.warning("No symbols found for monitoring")
                await self.telegram_bot.send_message("⚠️ No symbols found for monitoring")
                return []

            logger.info(f"Monitoring {len(monitored_symbols)} symbols: {', '.join(monitored_symbols[:10])}...")
            
            # Отправляем уведомление о начале отслеживания
            symbol_list_msg = f"✅ Starting to track {len(monitored_symbols)} coins:\n"
            if len(monitored_symbols) <= 20:
                symbol_list_msg += f"{', '.join(monitored_symbols)}"
            else:
                symbol_list_msg += f"{', '.join(monitored_symbols[:20])} and {len(monitored_symbols)-20} more..."
                
            await self.telegram_bot.send_message(symbol_list_msg)

            # Загружаем исторические данные для каждого символа
            successful_symbols = []
            for i, symbol in enumerate(monitored_symbols):
                try:
                    logger.info(f"Loading historical data for {symbol} ({i+1}/{len(monitored_symbols)})")
                    
                    # Загружаем исторические данные свечей
                    initial_klines_df = await self.binance_handler.get_initial_klines(symbol)
                    if not initial_klines_df.empty:
                        self.symbol_kline_data[symbol] = deque(
                            initial_klines_df.to_dict('records'),
                            maxlen=config.KLINE_LIMIT + 20  # Немного больше для безопасности
                        )
                        successful_symbols.append(symbol)
                        logger.debug(f"Loaded {len(initial_klines_df)} klines for {symbol}")
                    else:
                        logger.warning(f"No historical data available for {symbol}")
                        continue
                    
                    # Получаем начальные данные об открытом интересе
                    initial_oi = await self.binance_handler.get_open_interest(symbol)
                    self.symbol_open_interest_data[symbol] = {
                        'current_oi': initial_oi,
                        'prev_oi': None,
                        'timestamp': datetime.now().timestamp()
                    }
                    
                    # Небольшая задержка чтобы не перегружать API
                    if i % 10 == 0 and i > 0:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Failed to initialize {symbol}: {e}")
                    continue

            logger.info(f"Successfully initialized {len(successful_symbols)} symbols")
            return successful_symbols

        except Exception as e:
            logger.error(f"Error during symbol initialization: {e}")
            await self.telegram_bot.send_message(f"🚨 Error during initialization: {e}")
            return []

    async def setup_websocket_connection(self, symbols):
        """Настраивает WebSocket соединение со стримами"""
        try:
            # Определяем, тестовая ли сеть
            is_testnet = "testnet" in config.BINANCE_FUTURES_BASE_URL_REST
            
            # Инициализируем клиент
            self.client = await AsyncClient.create(
                config.BINANCE_API_KEY,
                config.BINANCE_API_SECRET,
                testnet=is_testnet
            )
            self.websocket_manager = BinanceSocketManager(self.client)

            # Создаем список стримов
            streams = []
            active_symbols = [s for s in symbols if s in self.symbol_kline_data]
            
            for symbol in active_symbols:
                # Стрим данных свечей
                streams.append(f"{symbol.lower()}@kline_{config.TIMEFRAME}")
                # Стрим force orders (как прокси для изменений OI)
                streams.append(f"{symbol.lower()}@forceOrder")

            if not streams:
                raise Exception("No streams available for subscription")

            logger.info(f"Prepared {len(streams)} streams for {len(active_symbols)} symbols")
            return streams

        except Exception as e:
            logger.error(f"Error setting up WebSocket connection: {e}")
            raise

    async def run_websocket_loop(self, streams):
        """Основной цикл WebSocket с логикой переподключения"""
        while self.running:
            try:
                logger.info("Connecting to WebSocket...")
                async with self.websocket_manager.multiplex_socket(streams) as socket:
                    logger.info("✅ WebSocket connected successfully")
                    await self.telegram_bot.send_message("🔗 WebSocket connected, monitoring started!")
                    self.reconnect_count = 0
                    
                    while self.running:
                        try:
                            # Ждем сообщение с таймаутом
                            msg = await asyncio.wait_for(socket.recv(), timeout=30.0)
                            await self.process_message(msg)
                            await self.send_heartbeat()
                            
                        except asyncio.TimeoutError:
                            logger.debug("WebSocket timeout, sending ping...")
                            continue
                        except Exception as e:
                            logger.error(f"Error processing WebSocket message: {e}")
                            await asyncio.sleep(1)

            except Exception as e:
                self.reconnect_count += 1
                logger.error(f"WebSocket connection error (attempt {self.reconnect_count}): {e}")
                
                if self.reconnect_count >= config.MAX_RECONNECT_ATTEMPTS:
                    logger.critical(f"Max reconnection attempts reached ({config.MAX_RECONNECT_ATTEMPTS})")
                    await self.telegram_bot.send_message("🚨 Max reconnection attempts reached. Bot stopping.")
                    break
                
                # Ждем перед повторным подключением
                wait_time = min(config.RECONNECT_DELAY * self.reconnect_count, 60)  # Максимум 60 сек
                logger.info(f"Waiting {wait_time} seconds before reconnection...")
                await asyncio.sleep(wait_time)

    async def start(self):
        """Запуск бота"""
        try:
            logger.info("🚀 Starting Crypto Scalping Bot...")
            self.running = True
            
            # Проверяем конфигурацию
            config.validate_config()
            logger.info("✅ Configuration validated")
            
            # Тестируем Telegram подключение
            if not await self.telegram_bot.test_connection():
                raise Exception("Failed to connect to Telegram")
            
            # Отправляем стартовое сообщение
            await self.send_startup_message()
            
            # Инициализируем символы
            symbols = await self.initialize_symbols()
            if not symbols:
                raise Exception("No symbols available for monitoring")
            
            # Настраиваем WebSocket
            streams = await self.setup_websocket_connection(symbols)
            
            # Запускаем основной цикл
            await self.run_websocket_loop(streams)
            
        except Exception as e:
            logger.critical(f"Critical error in bot startup: {e}")
            await self.telegram_bot.send_error_alert(str(e), "STARTUP ERROR")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Очистка ресурсов при завершении"""
        logger.info("Cleaning up resources...")
        self.running = False
        
        if self.client:
            await self.client.close_connection()
            logger.info("Binance client connection closed")
        
        if self.binance_handler:
            await self.binance_handler.close_connection()
            logger.info("Binance handler closed")

    def handle_signal(self, signum, frame):
        """Обработка сигналов завершения"""
        logger.info(f"Received signal {signum}, stopping bot...")
        self.running = False

# Основная функция запуска
async def main():
    """Главная функция запуска бота"""
    bot = CryptoScalpingBot()
    
    # Настраиваем обработку сигналов для корректного завершения
    signal.signal(signal.SIGINT, bot.handle_signal)
    signal.signal(signal.SIGTERM, bot.handle_signal)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user")
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        sys.exit(1)