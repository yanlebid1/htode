# services/pool_bot_service/app/main.py

import sys
import os
import asyncio

# Add parent directory to path to import telegram service modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from .bot import dp, bot, BOT_NAME
from . import logger
from common.utils.logging_config import log_operation

# Import and register telegram_service handler routers with this pool bot's dispatcher
from telegram_service.app.handlers.basic_handlers import router as basic_router
from telegram_service.app.handlers.menu_handlers import router as menu_router
from telegram_service.app.handlers.subscription import router as subscription_router
from telegram_service.app.handlers.advanced_handlers import router as advanced_router
from telegram_service.app.handlers.payment import router as payment_router
from telegram_service.app.handlers.phone_verification import router as phone_router
from telegram_service.app.handlers.support import router as support_router
from telegram_service.app.handlers.favorites import router as favorites_router
from telegram_service.app.flow_integration import router as flow_router
from telegram_service.app.tasks import router as tasks_router
from telegram_service.app.error_handler import router as error_router

dp.include_routers(
    basic_router,
    menu_router,
    subscription_router,
    advanced_router,
    payment_router,
    phone_router,
    support_router,
    favorites_router,
    flow_router,
    tasks_router,
    error_router,
)

# Import remaining telegram_service functionality
from telegram_service.app import messaging_service, state_integration

# Register the bot with messaging service
from common.messaging.service import messaging_service as global_messaging_service
from common.messaging.telegram_messaging import TelegramMessaging

# Register this bot instance
global_messaging_service.register_messenger("telegram", TelegramMessaging(bot))
logger.info("Pool bot registered with messaging service", extra={"bot_name": BOT_NAME})


@log_operation("pool_bot_main")
def main():
    """Start the Pool bot instance"""
    logger.info("Starting Pool bot", extra={"bot_name": BOT_NAME})

    try:
        # Start polling
        asyncio.run(_start_polling())
    except Exception as e:
        logger.error(
            "Pool bot startup failed",
            exc_info=True,
            extra={"bot_name": BOT_NAME, "error": str(e)}
        )
        raise
    finally:
        logger.info("Pool bot stopped", extra={"bot_name": BOT_NAME})


async def _start_polling():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    main()
