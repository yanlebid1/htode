# services/telegram_service/app/messaging_service.py
from common.messaging.service import messaging_service  # Import the global instance
from common.messaging.telegram_messaging import TelegramMessaging
from .bot import bot
from . import logger

# Register with the global messaging service instance
messaging_service.register_messenger("telegram", TelegramMessaging(bot))
logger.info("Telegram messaging service registered with global instance")
