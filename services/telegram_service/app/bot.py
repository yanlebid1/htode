# services/telegram_service/app/bot.py

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.utils.exceptions import (
    MessageNotModified, CantParseEntities, NetworkError, RetryAfter,
    BadRequest, Unauthorized, InvalidQueryID, TelegramAPIError,
    MessageToDeleteNotFound, BotBlocked
)
from common.config import TELEGRAM_TOKEN, REDIS_URL

# Import service logger instead of configuring local logging
from . import logger

# Parse Redis URL for host and port
# REDIS_URL format: redis://localhost:6379/0
import urllib.parse
parsed_redis_url = urllib.parse.urlparse(REDIS_URL)
REDIS_HOST = parsed_redis_url.hostname or "redis"
REDIS_PORT = parsed_redis_url.port or 6379

# Initialize bot and dispatcher
logger.info("Initializing Telegram bot", extra={
    "redis_host": REDIS_HOST,
    "redis_port": REDIS_PORT
})

try:
    bot = Bot(token=TELEGRAM_TOKEN)
    storage = RedisStorage2(host=REDIS_HOST, port=REDIS_PORT, db=1, prefix='fsm')
    dp = Dispatcher(bot, storage=storage)
    logger.info("Telegram bot initialized successfully")
except Exception as e:
    logger.error("Failed to initialize Telegram bot", exc_info=True, extra={
        "error": str(e)
    })
    raise