import pandas as pd
import numpy as np

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Рассчитывает RSI для последней цены в серии."""
    if len(prices) < period + 1:
        return np.nan  # Недостаточно данных
    delta = prices.diff().astype(float)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    if avg_loss.iloc[-1] == 0:
        return 100.0 if avg_gain.iloc[-1] > 0 else 50.0
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_atr(high_prices: pd.Series, low_prices: pd.Series, close_prices: pd.Series, period: int = 14) -> float:
    """Рассчитывает ATR для последней свечи."""
    if len(high_prices) < period or len(low_prices) < period or len(close_prices) < period:
        return np.nan
    prev_close = close_prices.shift(1)
    tr1 = high_prices - low_prices
    tr2 = abs(high_prices - prev_close)
    tr3 = abs(low_prices - prev_close)
    true_range = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
    atr = true_range.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return atr.iloc[-1]