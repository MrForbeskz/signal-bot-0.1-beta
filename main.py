import asyncio
import logging
import pandas as pd
from collections import deque
from binance import BinanceSocketManager
from binance.async_client import AsyncClient
import config
from telegram_bot_handler import TelegramBotHandler
from binance_handler import BinanceHandler
from strategy import Strategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

symbol_kline_data = {}  
symbol_open_interest_data = {}  

telegram_bot = TelegramBotHandler()
strategy_checker = Strategy()

async def process_message(msg):
    global symbol_kline_data, symbol_open_interest_data
    stream_name = msg.get('stream', '')
    data = msg.get('data', {})
    event_type = data.get('e')

    if not event_type or not stream_name:
        return

    try:
        symbol = stream_name.split('@')[0].upper()
    except IndexError:
        logger.warning(f"Не удалось извлечь символ из потока: {stream_name}")
        return

    if event_type == 'kline' and stream_name.endswith(f'@kline_{config.TIMEFRAME}'):
        kline_data = data.get('k')
        if not kline_data:
            return
        is_kline_closed = kline_data.get('x', False)
        if is_kline_closed:
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
                logger.error(f"Ошибка парсинга данных свечи для {symbol}: {e}")
                return

            if symbol not in symbol_kline_data:
                return

            symbol_kline_data[symbol].append(new_kline_entry)
            klines_df = pd.DataFrame(list(symbol_kline_data[symbol]))
            current_oi_info = symbol_open_interest_data.get(symbol, {})
            current_oi = current_oi_info.get('current_oi')
            prev_oi = current_oi_info.get('prev_oi')
            signal = strategy_checker.process_kline_data(symbol, klines_df, current_oi, prev_oi)
            if signal:
                await telegram_bot.send_message(signal)  # Добавлен await

            if current_oi is not None and symbol in symbol_open_interest_data:
                symbol_open_interest_data[symbol]['prev_oi'] = current_oi

    elif event_type == 'openInterestUpdate' and stream_name.endswith('@openinterest'):
        oi_payload = data.get('i')
        if not oi_payload or oi_payload.get('symbol') != symbol:
            return
        try:
            oi_value = float(oi_payload['openInterest'])
            oi_timestamp = oi_payload['timestamp']
        except (KeyError, ValueError) as e:
            logger.error(f"Ошибка парсинга данных openInterest для {symbol}: {e}")
            return

        if symbol not in symbol_open_interest_data:
            symbol_open_interest_data[symbol] = {'current_oi': oi_value, 'prev_oi': None, 'timestamp': oi_timestamp}
        else:
            symbol_open_interest_data[symbol]['current_oi'] = oi_value
            symbol_open_interest_data[symbol]['timestamp'] = oi_timestamp

async def main():
    logger.info("Запуск бота...")
    await telegram_bot.send_message("🚀 Бот для скальпинга запускается...")  # Добавлен await

    sync_binance_handler = BinanceHandler()
    async_client = None

    try:
        if not config.SYMBOLS_TO_MONITOR:
            all_symbols = await sync_binance_handler.get_tradable_futures_symbols()
            monitored_symbols = await sync_binance_handler.filter_symbols_by_volume(all_symbols)
        else:
            monitored_symbols = config.SYMBOLS_TO_MONITOR

        if not monitored_symbols:
            logger.warning("Нет символов для мониторинга")
            await telegram_bot.send_message("⚠️ Нет символов для мониторинга")  # Добавлен await
            return

        logger.info(f"Символы для мониторинга ({len(monitored_symbols)}): {', '.join(monitored_symbols)}")
        await telegram_bot.send_message(f"✅ Начинаю отслеживать {len(monitored_symbols)} монет(ы)")  # Добавлен await

        for symbol in monitored_symbols:
            initial_klines_df = await sync_binance_handler.get_initial_klines(symbol)
            if not initial_klines_df.empty:
                symbol_kline_data[symbol] = deque(initial_klines_df.to_dict('records'), maxlen=config.KLINE_LIMIT + 20)
            symbol_open_interest_data[symbol] = {'current_oi': None, 'prev_oi': None, 'timestamp': None}

        is_testnet = "testnet" in config.BINANCE_FUTURES_BASE_URL_REST
        async_client = await AsyncClient.create(
            config.BINANCE_API_KEY,
            config.BINANCE_API_SECRET,
            testnet=is_testnet
        )
        bsm = BinanceSocketManager(async_client)

        streams = []
        active_monitored_symbols = [s for s in monitored_symbols if s in symbol_kline_data]
        for symbol_to_watch in active_monitored_symbols:
            streams.append(f"{symbol_to_watch.lower()}@kline_{config.TIMEFRAME}")
            streams.append(f"{symbol_to_watch.lower()}@openinterest")

        if not streams:
            logger.error("Нет потоков для подписки")
            await telegram_bot.send_message("⚠️ Ошибка: нет данных для подписки")  # Добавлен await
            return

        logger.info(f"Подписка на потоки: {streams}")

        # Исправленная часть с WebSocket
        async with bsm.multiplex_socket(streams) as ms:
            while True:
                try:
                    msg = await ms.recv()
                    await process_message(msg)
                except Exception as e:
                    logger.error(f"Ошибка в основном цикле: {e}")
                    await asyncio.sleep(5)

    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        await telegram_bot.send_message(f"🆘 Критическая ошибка: {e}")  # Добавлен await
    finally:
        if async_client:
            await async_client.close_connection()
            logger.info("Соединение закрыто")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
        await telegram_bot.send_message("🛑 Бот остановлен")  # Добавлен await
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        await telegram_bot.send_message(f"🆘 Критическая ошибка: {e}")  # Добавлен await