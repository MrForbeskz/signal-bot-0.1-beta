import telegram
import logging
import asyncio
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramBotHandler:
    def __init__(self):
        """Initialize Telegram bot handler"""
        try:
            self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            self.chat_id = TELEGRAM_CHAT_ID
            self.message_queue = asyncio.Queue()
            self.is_processing = False
            logger.info("Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Telegram bot: {e}")
            self.bot = None

    async def send_message(self, text, parse_mode='MarkdownV2', max_retries=3):
        """
        Send message to Telegram with retry logic and rate limiting
        
        Args:
            text (str): Message text
            parse_mode (str): Parse mode for formatting
            max_retries (int): Maximum number of retry attempts
        """
        if not self.bot:
            logger.error("Telegram bot not initialized. Message not sent.")
            return False

        # Escape special characters for MarkdownV2
        if parse_mode == 'MarkdownV2':
            text = self._escape_markdown_v2(text)

        for attempt in range(max_retries):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
                logger.info(f"Message sent to Telegram successfully")
                return True
                
            except telegram.error.RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Rate limited. Waiting {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                
            except telegram.error.BadRequest as e:
                logger.error(f"Bad request error: {e}")
                # Try without markdown if formatting fails
                if parse_mode == 'MarkdownV2' and attempt == 0:
                    return await self.send_message(text, parse_mode=None, max_retries=max_retries-1)
                break
                
            except Exception as e:
                logger.error(f"Error sending message (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
        logger.error(f"Failed to send message after {max_retries} attempts")
        return False

    def _escape_markdown_v2(self, text):
        """
        Escape special characters for Telegram's MarkdownV2
        
        Args:
            text (str): Text to escape
            
        Returns:
            str: Escaped text
        """
        # Characters that need to be escaped in MarkdownV2
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        # Don't escape characters that are part of intended formatting
        lines = text.split('\n')
        escaped_lines = []
        
        for line in lines:
            # Check if line contains intended formatting (starts with * for bold)
            if line.startswith('*') and line.endswith('*') and len(line) > 2:
                # This is a bold line, don't escape the asterisks
                inner_text = line[1:-1]  # Remove outer asterisks
                escaped_inner = self._escape_text(inner_text, ['*'])  # Escape everything except *
                escaped_lines.append(f"*{escaped_inner}*")
            else:
                # Regular line, escape everything
                escaped_lines.append(self._escape_text(line, []))
        
        return '\n'.join(escaped_lines)

    def _escape_text(self, text, skip_chars=None):
        """
        Escape text with option to skip certain characters
        
        Args:
            text (str): Text to escape
            skip_chars (list): Characters to skip escaping
            
        Returns:
            str: Escaped text
        """
        if skip_chars is None:
            skip_chars = []
            
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in escape_chars:
            if char not in skip_chars:
                text = text.replace(char, f'\\{char}')
                
        return text

    async def send_status_update(self, active_symbols, reconnects, uptime):
        """
        Send formatted status update
        
        Args:
            active_symbols (int): Number of active symbols
            reconnects (int): Number of reconnections
            uptime (str): Bot uptime
        """
        status_msg = (
            f"💓 *Bot Status*\n\n"
            f"Active Symbols: {active_symbols}\n"
            f"Reconnects: {reconnects}\n"
            f"Uptime: {uptime}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(status_msg)

    async def send_signal(self, signal_type, symbol, entry_price, rsi, atr, oi_info, stop_loss, take_profit):
        """
        Send formatted trading signal
        
        Args:
            signal_type (str): 'LONG' or 'SHORT'
            symbol (str): Trading symbol
            entry_price (float): Entry price
            rsi (float): RSI value
            atr (float): ATR value
            oi_info (str): Open interest information
            stop_loss (float): Stop loss price
            take_profit (float): Take profit price
        """
        emoji = "🟢" if signal_type == "LONG" else "🔴"
        
        signal_msg = (
            f"{emoji} *{signal_type} SIGNAL*\n\n"
            f"Symbol: {symbol}\n"
            f"Entry Price: {entry_price:.4f}\n"
            f"RSI: {rsi:.2f}\n"
            f"ATR: {atr:.4f}\n"
            f"Open Interest: {oi_info}\n\n"
            f"🛑 Stop Loss: {stop_loss:.4f}\n"
            f"🎯 Take Profit: {take_profit:.4f}\n\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(signal_msg)

    async def send_error_alert(self, error_msg, error_type="ERROR"):
        """
        Send error alert with formatting
        
        Args:
            error_msg (str): Error message
            error_type (str): Type of error
        """
        alert_msg = (
            f"🚨 *{error_type}*\n\n"
            f"{error_msg}\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await self.send_message(alert_msg)

    async def test_connection(self):
        """
        Test Telegram bot connection
        
        Returns:
            bool: True if connection successful
        """
        try:
            await self.bot.get_me()
            logger.info("Telegram bot connection test successful")
            return True
        except Exception as e:
            logger.error(f"Telegram bot connection test failed: {e}")
            return False