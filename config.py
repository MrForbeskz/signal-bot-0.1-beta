# Telegram Bot Token (полученный от BotFather)
TELEGRAM_BOT_TOKEN = "7997273231:AAHMgGylVIGNbSgnmUt3QPlwlaMPu5Gvc-g"
# ID твоего чата в Telegram, куда бот будет слать сообщения.
TELEGRAM_CHAT_ID = "1720590434"
# Binance API Keys (ИСПОЛЬЗУЙ КЛЮЧИ ОТ TESTNET ДЛЯ РАЗРАБОТКИ!)
BINANCE_API_KEY = "3ef76c401039b22bb8c1825fc404881830e1fca69af04ab920f3ee45fce6c7cf"
BINANCE_API_SECRET = "3d4e6e9faadcaa29dde9701e96a943d7f231fe905770a4bc0376e7878102bb83"
# URL для Binance Futures API
# Для реальной торговли:
# BINANCE_FUTURES_BASE_URL_REST = "https://fapi.binance.com "
# BINANCE_FUTURES_BASE_URL_WS = "wss://fstream.binance.com"
# Для Testnet:
BINANCE_FUTURES_BASE_URL_REST = "https://testnet.binancefuture.com "
BINANCE_FUTURES_BASE_URL_WS = "wss://stream.binancefuture.com"
# Параметры стратегии
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
ATR_PERIOD = 14
VOLUME_THRESHOLD_USD = 200_000_000  # 200 миллионов USD
TIMEFRAME = "1m"  # Таймфрейм для анализа (1m, 5m, 15m, 1h и т.д.)
KLINE_LIMIT = 100  # Количество исторических свечей для загрузки для расчета индикаторов
SYMBOLS_TO_MONITOR = []  # Оставь пустым для мониторинга всех подходящих, или укажи конкретные, например ["BTCUSDT", "ETHUSDT"]