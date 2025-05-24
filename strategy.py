import pandas as pd
import logging
from utils import calculate_rsi, calculate_atr
from config import RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD, ATR_PERIOD

logger = logging.getLogger(__name__)

class Strategy:
    def __init__(self):
        pass

    def process_kline_data(self, symbol: str, klines_df: pd.DataFrame, current_oi: float, prev_oi: float):
        """
        Обрабатывает данные свечей и открытого интереса для генерации сигнала.
        :param symbol: Символ монеты (например, "BTCUSDT")
        :param klines_df: DataFrame с историческими данными свечей (должен содержать 'close', 'high', 'low')
        :param current_oi: Текущее значение открытого интереса
        :param prev_oi: Предыдущее значение открытого интереса (на момент закрытия предыдущей свечи)
        :return: Строка с сигналом или None, если сигнала нет.
        """
        if klines_df.empty or len(klines_df) < max(RSI_PERIOD + 1, ATR_PERIOD + 1):  # +1 для diff() в RSI и shift() в ATR
            logger.debug(f"Недостаточно данных для анализа {symbol}: {len(klines_df)} свечей")
            return None

        klines_df = klines_df.reset_index(drop=True)

        rsi = calculate_rsi(klines_df['close'], RSI_PERIOD)
        atr = calculate_atr(klines_df['high'], klines_df['low'], klines_df['close'], ATR_PERIOD)

        if pd.isna(rsi) or pd.isna(atr):
            logger.debug(f"Не удалось рассчитать индикаторы для {symbol}. RSI: {rsi}, ATR: {atr}")
            return None

        last_close_price = klines_df['close'].iloc[-1]
        signal_message = None

        oi_grew = current_oi > prev_oi if prev_oi is not None and current_oi is not None else False

        logger.debug(f"{symbol} | Цена: {last_close_price:.2f} | RSI({RSI_PERIOD}): {rsi:.2f} | ATR({ATR_PERIOD}): {atr:.4f} | OI: {current_oi} (prev: {prev_oi}, grew: {oi_grew})")

        if rsi < RSI_OVERSOLD and oi_grew:
            stop_loss = last_close_price - 1.5 * atr
            take_profit = last_close_price + 2.0 * atr
            signal_message = (
                f"*ЛОНГ СИГНАЛ для {symbol}*\n"
                f"Цена входа: {last_close_price:.4f}\n"
                f"RSI({RSI_PERIOD}): {rsi:.2f}\n"
                f"ATR({ATR_PERIOD}): {atr:.4f}\n"
                f"Открытый интерес: РАСТЕТ ({prev_oi} -> {current_oi})\n"
                f"Stop-Loss: {stop_loss:.4f}\n"
                f"Take-Profit: {take_profit:.4f}"
            )
        elif rsi > RSI_OVERBOUGHT and oi_grew:
            stop_loss = last_close_price + 1.5 * atr
            take_profit = last_close_price - 2.0 * atr
            signal_message = (
                f"*ШОРТ СИГНАЛ для {symbol}*\n"
                f"Цена входа: {last_close_price:.4f}\n"
                f"RSI({RSI_PERIOD}): {rsi:.2f}\n"
                f"ATR({ATR_PERIOD}): {atr:.4f}\n"
                f"Открытый интерес: РАСТЕТ ({prev_oi} -> {current_oi})\n"
                f"Stop-Loss: {stop_loss:.4f}\n"
                f"Take-Profit: {take_profit:.4f}"
            )

        return signal_message