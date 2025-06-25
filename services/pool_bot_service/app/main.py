# services/pool_bot_service/app/main.py

import sys
import os
from aiogram import executor

# Add parent directory to path to import telegram service modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from .bot import dp, bot, BOT_NAME
from . import logger
from common.utils.logging_config import log_operation

# Import existing telegram service handlers and functionality
# This allows us to reuse all the existing bot logic
from telegram_service.app import (
    error_handler,
    flow_integration,
    handlers,
    messaging_service,
    state_integration
)

# Register the bot with messaging service
from common.messaging.service import messaging_service as global_messaging_service
from common.messaging.telegram_messaging import TelegramMessaging

# Register this bot instance
global_messaging_service.register_messenger("telegram", TelegramMessaging(bot))
logger.info(f"Pool bot {BOT_NAME} registered with messaging service")


@log_operation(f"pool_bot_main_{BOT_NAME}")
def main():
    """Start the Pool bot instance"""
    logger.info(f"Starting Pool bot {BOT_NAME}...")
    
    try:
        # Start polling
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(
            f"Pool bot {BOT_NAME} startup failed",
            exc_info=True,
            extra={"error": str(e)}
        )
        raise
    finally:
        logger.info(f"Pool bot {BOT_NAME} stopped")


if __name__ == "__main__":
    main() 