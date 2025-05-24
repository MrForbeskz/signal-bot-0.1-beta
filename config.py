import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Binance API Configuration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'testnet')

# Binance URLs based on environment
if ENVIRONMENT == 'testnet':
    BINANCE_FUTURES_BASE_URL_REST = "https://testnet.binancefuture.com"
    BINANCE_FUTURES_BASE_URL_WS = "wss://stream.binancefuture.com"
else:
    BINANCE_FUTURES_BASE_URL_REST = "https://fapi.binance.com"
    BINANCE_FUTURES_BASE_URL_WS = "wss://fstream.binance.com"

# Strategy Parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
ATR_PERIOD = 14
VOLUME_THRESHOLD_USD = 200_000_000  # 200 million USD
TIMEFRAME = "1m"  # Timeframe for analysis (1m, 5m, 15m, 1h etc.)
KLINE_LIMIT = 100  # Number of historical candles to load for indicator calculations

# Symbol Configuration
SYMBOLS_TO_MONITOR = []  # Leave empty to monitor all suitable symbols, or specify like ["BTCUSDT", "ETHUSDT"]

# Bot Configuration
RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_ATTEMPTS = 10
HEARTBEAT_INTERVAL = 300  # 5 minutes - send status updates
COOLDOWN_BETWEEN_SIGNALS = 300  # 5 minutes - prevent spam

# Logging Configuration
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True
LOG_FILE = "bot.log"

# Risk Management
MIN_OI_CHANGE_PERCENT = 2.0  # Minimum Open Interest change for signal
MIN_VOLUME_MULTIPLIER = 1.2  # Volume should be 20% above average
STOP_LOSS_ATR_MULTIPLIER = 1.5  # Stop loss = ATR * 1.5
TAKE_PROFIT_ATR_MULTIPLIER = 2.0  # Take profit = ATR * 2.0

# Validation
def validate_config():
    """Validate that all required configuration is present"""
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID', 
        'BINANCE_API_KEY',
        'BINANCE_API_SECRET'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not globals().get(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    print("✅ Configuration validated successfully")
    print(f"📊 Environment: {ENVIRONMENT}")
    print(f"💰 Volume threshold: ${VOLUME_THRESHOLD_USD/1_000_000:.0f}M")
    print(f"⏰ Timeframe: {TIMEFRAME}")
    print(f"📈 RSI parameters: {RSI_OVERSOLD}-{RSI_OVERBOUGHT} (period {RSI_PERIOD})")
    
    return True