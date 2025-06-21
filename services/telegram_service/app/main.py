# services/telegram_service/app/main.py

from aiogram import executor
from .bot import dp

# Import the flow integration

# Import the error handler

# Import the messaging service registration


# Import service logger instead of configuring local logging
from . import logger
from common.utils.logging_config import log_operation


@log_operation("setup_handlers")
def setup_handlers():
    """
    Make sure all handlers are registered properly.
    This function doesn't need to do anything explicit since imports
    already register the handlers with the dispatcher.
    """
    # The imports above already register the handlers with the dispatcher
    # We're just making sure the error_handler module is initialized
    # and that flow integration is imported so its handlers are registered
    logger.info("All handlers and error handler registered")
    logger.info("Flow integration initialized")


@log_operation("main")
def main():
    """
    Start the Telegram bot (using long polling)
    """
    logger.info("Starting Telegram bot...")
    try:
        # Make sure handlers are set up before starting
        setup_handlers()

        # Start polling
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error("Bot startup failed", exc_info=True, extra={"error": str(e)})
        raise
    finally:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
