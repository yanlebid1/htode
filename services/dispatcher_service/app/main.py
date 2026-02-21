# services/dispatcher_service/app/main.py

import asyncio
from .bot import dp, bot

# Import and register handler router
from .handlers import router as handlers_router
dp.include_router(handlers_router)

# Import service logger
from . import logger
from common.utils.logging_config import log_operation


@log_operation("dispatcher_main")
def main():
    """Start the Dispatcher bot"""
    logger.info("Starting Dispatcher bot...")

    try:
        # Start polling
        asyncio.run(_start_polling())
    except Exception as e:
        logger.error(
            "Dispatcher bot startup failed",
            exc_info=True,
            extra={"error": str(e)}
        )
        raise
    finally:
        logger.info("Dispatcher bot stopped")


async def _start_polling():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    main()
