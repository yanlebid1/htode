# services/telegram_service/app/main.py

import asyncio
from .bot import dp, bot

# Import the flow integration

# Import the error handler

# Import the messaging service registration


# Import service logger instead of configuring local logging
from . import logger
from common.utils.logging_config import log_operation
from common.utils.tracing import init_tracing


@log_operation("setup_handlers")
def setup_handlers():
    """
    Register all handler routers with the dispatcher.
    In aiogram v3, each handler module defines its own Router
    which must be explicitly included in the Dispatcher.
    """
    from .handlers.basic_handlers import router as basic_router
    from .handlers.menu_handlers import router as menu_router
    from .handlers.subscription import router as subscription_router
    from .handlers.advanced_handlers import router as advanced_router
    from .handlers.payment import router as payment_router
    from .handlers.phone_verification import router as phone_router
    from .handlers.support import router as support_router
    from .handlers.favorites import router as favorites_router
    from .flow_integration import router as flow_router
    from .tasks import router as tasks_router
    from .error_handler import router as error_router

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
    logger.info("All handler routers registered with dispatcher")


@log_operation("main")
def main():
    """
    Start the Telegram bot (using long polling)
    """
    init_tracing("telegram_service")
    logger.info("Starting Telegram bot...")
    try:
        # Make sure handlers are set up before starting
        setup_handlers()

        # Start polling
        asyncio.run(_start_polling())
    except Exception as e:
        logger.error("Bot startup failed", exc_info=True, extra={"error": str(e)})
        raise
    finally:
        logger.info("Bot stopped")


async def _start_polling():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    main()
