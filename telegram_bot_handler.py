import telegram
import logging
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
logger = logging.getLogger(__name__)

class TelegramBotHandler:
    def __init__(self):
        try:
            self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            logger.info("Telegram бот инициализирован успешно.")
        except Exception as e:
            logger.error(f"Ошибка инициализации Telegram бота: {e}")
            self.bot = None

    async def send_message(self, text):
        if not self.bot:
            logger.error("Telegram бот не инициализирован. Сообщение не отправлено.")
            return
        try:
            await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=telegram.ParseMode.MARKDOWN)  # Исправлен ParseMode
            logger.info(f"Сообщение отправлено в Telegram: {text}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")