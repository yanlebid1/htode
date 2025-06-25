# services/dispatcher_service/app/main.py

from aiogram import executor
from .bot import dp

# Import handlers to register them
from . import handlers

# Import service logger
from . import logger
from common.utils.logging_config import log_operation


@log_operation("dispatcher_main")
def main():
    """Start the Dispatcher bot"""
    logger.info("Starting Dispatcher bot...")
    
    try:
        # Start polling
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(
            "Dispatcher bot startup failed", 
            exc_info=True, 
            extra={"error": str(e)}
        )
        raise
    finally:
        logger.info("Dispatcher bot stopped")


if __name__ == "__main__":
    main() 