import pandas as pd
import logging
from utils import calculate_rsi, calculate_atr
from config import (
    RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD, ATR_PERIOD,
    MIN_OI_CHANGE_PERCENT, MIN_VOLUME_MULTIPLIER,
    STOP_LOSS_ATR_MULTIPLIER, TAKE_PROFIT_ATR_MULTIPLIER
)

logger = logging.getLogger(__name__)

class Strategy:
    def __init__(self):
        """Инициализация стратегии с улучшенными параметрами"""
        self.min_oi_change_percent = MIN_OI_CHANGE_PERCENT
        self.min_volume_multiplier = MIN_VOLUME_MULTIPLIER
        
        logger.info(f"Strategy initialized with parameters:")
        logger.info(f"  - RSI period: {RSI_PERIOD} (oversold: {RSI_OVERSOLD}, overbought: {RSI_OVERBOUGHT})")
        logger.info(f"  - ATR period: {ATR_PERIOD}")
        logger.info(f"  - Min OI change: {self.min_oi_change_percent}%")
        logger.info(f"  - Min volume multiplier: {self.min_volume_multiplier}x")
        
    def calculate_oi_change_percent(self, current_oi, prev_oi):
        """
        Рассчитывает процентное изменение открытого интереса
        
        Args:
            current_oi (float): Текущий открытый интерес
            prev_oi (float): Предыдущий открытый интерес
            
        Returns:
            float: Процентное изменение (положительное = рост, отрицательное = падение)
        """
        if prev_oi is None or prev_oi == 0 or current_oi is None:
            return 0.0
        
        change_percent = ((current_oi - prev_oi) / prev_oi) * 100
        logger.debug(f"OI change: {prev_oi:.0f} -> {current_oi:.0f} ({change_percent:+.2f}%)")
        return change_percent

    def is_strong_volume(self, klines_df):
        """
        Проверяет, есть ли сильный объем на последних свечах
        
        Args:
            klines_df (pd.DataFrame): DataFrame с данными свечей
            
        Returns:
            tuple: (bool, float) - (является ли объём сильным, отношение к среднему)
        """
        if len(klines_df) < 20:
            return True, 1.0  # Если мало данных, не фильтруем по объему
            
        # Берем последние 20 свечей для расчета среднего объема
        recent_volumes = klines_df['volume'].tail(20)
        avg_volume = recent_volumes.mean()
        last_volume = klines_df['volume'].iloc[-1]
        
        if avg_volume == 0:
            return True, 1.0
            
        volume_ratio = last_volume / avg_volume
        is_strong = volume_ratio >= self.min_volume_multiplier
        
        logger.debug(f"Volume analysis: last={last_volume:.0f}, avg={avg_volume:.0f}, ratio={volume_ratio:.2f}x")
        return is_strong, volume_ratio

    def is_trend_confirmation(self, klines_df, signal_type):
        """
        Подтверждает направление тренда по последним свечам
        
        Args:
            klines_df (pd.DataFrame): DataFrame с данными свечей
            signal_type (str): 'LONG' или 'SHORT'
            
        Returns:
            tuple: (bool, str) - (подтверждается ли тренд, описание)
        """
        if len(klines_df) < 5:
            return True, "insufficient data"
            
        # Берем последние 5 свечей
        recent_closes = klines_df['close'].tail(5)
        recent_highs = klines_df['high'].tail(5)
        recent_lows = klines_df['low'].tail(5)
        
        # Анализируем движение цены
        price_momentum = (recent_closes.iloc[-1] - recent_closes.iloc[-3]) / recent_closes.iloc[-3]
        
        if signal_type == 'LONG':
            # Для лонга: цена не должна сильно падать и должен быть хотя бы небольшой отскок
            trend_ok = price_momentum > -0.01  # Падение не более 1%
            bounce_ok = recent_closes.iloc[-1] >= recent_lows.iloc[-2]  # Цена выше предыдущего минимума
            confirmation = trend_ok and bounce_ok
            description = f"momentum: {price_momentum:.3f}, bounce: {bounce_ok}"
        else:  # SHORT
            # Для шорта: цена не должна сильно расти и должен быть хотя бы небольшой откат
            trend_ok = price_momentum < 0.01  # Рост не более 1%
            pullback_ok = recent_closes.iloc[-1] <= recent_highs.iloc[-2]  # Цена ниже предыдущего максимума
            confirmation = trend_ok and pullback_ok
            description = f"momentum: {price_momentum:.3f}, pullback: {pullback_ok}"
        
        logger.debug(f"Trend confirmation for {signal_type}: {confirmation} ({description})")
        return confirmation, description

    def calculate_dynamic_levels(self, klines_df, atr):
        """
        Рассчитывает динамические уровни стоп-лосса и тейк-профита
        
        Args:
            klines_df (pd.DataFrame): DataFrame с данными свечей
            atr (float): Значение ATR
            
        Returns:
            tuple: (stop_multiplier, take_multiplier, volatility_info)
        """
        if len(klines_df) < 20:
            return (STOP_LOSS_ATR_MULTIPLIER, TAKE_PROFIT_ATR_MULTIPLIER, "insufficient data")
            
        # Анализируем волатильность последних 20 свечей
        recent_highs = klines_df['high'].tail(20)
        recent_lows = klines_df['low'].tail(20)
        recent_closes = klines_df['close'].tail(20)
        avg_close = recent_closes.mean()
        
        volatility = (recent_highs.max() - recent_lows.min()) / avg_close
        
        # Адаптируем мультипликаторы в зависимости от волатильности
        if volatility > 0.05:  # Высокая волатильность (>5%)
            stop_mult, take_mult = 2.0, 2.5
            vol_level = "high"
        elif volatility > 0.02:  # Средняя волатильность (2-5%)
            stop_mult, take_mult = STOP_LOSS_ATR_MULTIPLIER, TAKE_PROFIT_ATR_MULTIPLIER
            vol_level = "medium"
        else:  # Низкая волатильность (<2%)
            stop_mult, take_mult = 1.2, 1.8
            vol_level = "low"
        
        vol_info = f"{vol_level} ({volatility:.3f})"
        logger.debug(f"Volatility analysis: {vol_info}, multipliers: SL={stop_mult}, TP={take_mult}")
        
        return (stop_mult, take_mult, vol_info)

    def calculate_signal_strength(self, rsi, oi_change_percent, volume_ratio, trend_confirmed):
        """
        Рассчитывает силу сигнала от 1 до 5 звёзд
        
        Args:
            rsi (float): Значение RSI
            oi_change_percent (float): Изменение открытого интереса в %
            volume_ratio (float): Отношение текущего объёма к среднему
            trend_confirmed (bool): Подтверждён ли тренд
            
        Returns:
            tuple: (int, str) - (количество звёзд, описание)
        """
        strength = 0
        factors = []
        
        # RSI фактор (max 2 звезды)
        if rsi <= 25 or rsi >= 75:  # Экстремальные значения
            strength += 2
            factors.append("extreme RSI")
        elif rsi <= RSI_OVERSOLD or rsi >= RSI_OVERBOUGHT:
            strength += 1
            factors.append("RSI signal")
        
        # OI фактор (max 2 звезды)
        if oi_change_percent >= 5.0:  # Очень сильный рост OI
            strength += 2
            factors.append("strong OI growth")
        elif oi_change_percent >= self.min_oi_change_percent:
            strength += 1
            factors.append("OI growth")
        
        # Volume фактор (max 1 звезда)
        if volume_ratio >= 2.0:  # Объём в 2+ раза выше среднего
            strength += 1
            factors.append("high volume")
        
        # Trend фактор (бонус/штраф)
        if trend_confirmed:
            strength += 0  # Нейтрально, это базовое требование
        else:
            strength = max(0, strength - 1)  # Штраф за неподтверждённый тренд
            factors.append("weak trend")
        
        strength = min(5, max(1, strength))  # Ограничиваем от 1 до 5
        description = " + ".join(factors) if factors else "basic signal"
        
        return strength, description

    def format_signal_message(self, signal_type, symbol, klines_df, rsi, atr, 
                            oi_change_percent, stop_loss, take_profit, 
                            volume_ratio, vol_info, signal_strength, strength_desc):
        """
        Форматирует сообщение с торговым сигналом
        """
        last_close_price = klines_df['close'].iloc[-1]
        risk = abs(last_close_price - stop_loss)
        reward = abs(take_profit - last_close_price)
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        # Эмодзи для силы сигнала
        stars = "⭐" * signal_strength
        signal_emoji = "🟢" if signal_type == "LONG" else "🔴"
        
        signal_message = (
            f"{signal_emoji} *{signal_type} SIGNAL* {stars}\n"
            f"📊 *{symbol}*\n\n"
            f"💰 Entry: `{last_close_price:.4f}`\n"
            f"🛑 Stop Loss: `{stop_loss:.4f}` ({(risk/last_close_price*100):.2f}%)\n"
            f"🎯 Take Profit: `{take_profit:.4f}` ({(reward/last_close_price*100):.2f}%)\n"
            f"⚖️ Risk/Reward: `1:{risk_reward_ratio:.2f}`\n\n"
            f"📈 *Technical Analysis:*\n"
            f"• RSI({RSI_PERIOD}): `{rsi:.1f}`\n"
            f"• ATR({ATR_PERIOD}): `{atr:.6f}`\n"
            f"• Open Interest: `+{oi_change_percent:.2f}%`\n"
            f"• Volume: `{volume_ratio:.1f}x` above avg\n"
            f"• Volatility: `{vol_info}`\n\n"
            f"🎯 *Signal Strength:* {strength_desc}\n"
            f"⏰ `{pd.Timestamp.now().strftime('%H:%M:%S')}`"
        )
        
        return signal_message

    def process_kline_data(self, symbol: str, klines_df: pd.DataFrame, current_oi: float, prev_oi: float):
        """
        Обрабатывает данные свечей и открытого интереса для генерации сигнала.
        
        Args:
            symbol (str): Символ монеты (например, "BTCUSDT")
            klines_df (pd.DataFrame): DataFrame с историческими данными свечей
            current_oi (float): Текущее значение открытого интереса
            prev_oi (float): Предыдущее значение открытого интереса
            
        Returns:
            str: Строка с сигналом или None, если сигнала нет.
        """
        # Проверяем достаточность данных
        required_data_length = max(RSI_PERIOD + 1, ATR_PERIOD + 1)
        if klines_df.empty or len(klines_df) < required_data_length:
            logger.debug(f"Insufficient data for {symbol}: {len(klines_df)} candles")
            return None

        # Сбрасываем индекс для правильной работы с данными
        klines_df = klines_df.reset_index(drop=True)

        # Рассчитываем технические индикаторы
        try:
            rsi = calculate_rsi(klines_df['close'], RSI_PERIOD)
            atr = calculate_atr(klines_df['high'], klines_df['low'], klines_df['close'], ATR_PERIOD)
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return None

        # Проверяем валидность индикаторов
        if pd.isna(rsi) or pd.isna(atr) or atr == 0:
            logger.debug(f"Invalid indicators for {symbol}. RSI: {rsi}, ATR: {atr}")
            return None

        # Получаем текущую цену
        last_close_price = klines_df['close'].iloc[-1]
        
        # Рассчитываем изменение открытого интереса
        oi_change_percent = self.calculate_oi_change_percent(current_oi, prev_oi)
        oi_grew_significantly = oi_change_percent >= self.min_oi_change_percent

        # Дополнительные фильтры
        strong_volume, volume_ratio = self.is_strong_volume(klines_df)
        
        # Логируем текущее состояние
        logger.debug(
            f"{symbol} | Price: {last_close_price:.4f} | "
            f"RSI: {rsi:.2f} | ATR: {atr:.6f} | "
            f"OI: {oi_change_percent:+.2f}% | Vol: {volume_ratio:.2f}x"
        )

        signal_message = None
        
        # Проверяем условия для LONG сигнала
        if rsi < RSI_OVERSOLD and oi_grew_significantly and strong_volume:
            trend_confirmed, trend_desc = self.is_trend_confirmation(klines_df, 'LONG')
            
            if trend_confirmed:
                # Рассчитываем динамические уровни
                stop_multiplier, take_multiplier, vol_info = self.calculate_dynamic_levels(klines_df, atr)
                
                stop_loss = last_close_price - (stop_multiplier * atr)
                take_profit = last_close_price + (take_multiplier * atr)
                
                # Рассчитываем силу сигнала
                signal_strength, strength_desc = self.calculate_signal_strength(
                    rsi, oi_change_percent, volume_ratio, trend_confirmed
                )
                
                signal_message = self.format_signal_message(
                    "LONG", symbol, klines_df, rsi, atr, oi_change_percent,
                    stop_loss, take_profit, volume_ratio, vol_info,
                    signal_strength, strength_desc
                )
                
                logger.info(f"LONG signal generated for {symbol} (strength: {signal_strength}/5)")
            
        # Проверяем условия для SHORT сигнала
        elif rsi > RSI_OVERBOUGHT and oi_grew_significantly and strong_volume:
            trend_confirmed, trend_desc = self.is_trend_confirmation(klines_df, 'SHORT')
            
            if trend_confirmed:
                # Рассчитываем динамические уровни
                stop_multiplier, take_multiplier, vol_info = self.calculate_dynamic_levels(klines_df, atr)
                
                stop_loss = last_close_price + (stop_multiplier * atr)
                take_profit = last_close_price - (take_multiplier * atr)
                
                # Рассчитываем силу сигнала
                signal_strength, strength_desc = self.calculate_signal_strength(
                    rsi, oi_change_percent, volume_ratio, trend_confirmed
                )
                
                signal_message = self.format_signal_message(
                    "SHORT", symbol, klines_df, rsi, atr, oi_change_percent,
                    stop_loss, take_profit, volume_ratio, vol_info,
                    signal_strength, strength_desc
                )
                
                logger.info(f"SHORT signal generated for {symbol} (strength: {signal_strength}/5)")

        return signal_message