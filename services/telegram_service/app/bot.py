# services/telegram_service/app/bot.py

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from common.config import TELEGRAM_TOKEN, REDIS_URL
import os

# Import service logger instead of configuring local logging
from . import logger

# Use Redis cluster for Telegram bot state storage
# Parse Redis State URL for Telegram FSM storage
import urllib.parse

REDIS_STATE_URL = os.getenv("REDIS_STATE_URL", REDIS_URL)
parsed_redis_url = urllib.parse.urlparse(REDIS_STATE_URL)
REDIS_HOST = parsed_redis_url.hostname or "redis_state"
REDIS_PORT = parsed_redis_url.port or 6379

# Initialize bot and dispatcher
logger.info(
    "Initializing Telegram bot with Redis cluster",
    extra={"redis_host": REDIS_HOST, "redis_port": REDIS_PORT, "redis_url": REDIS_STATE_URL},
)

try:
    bot = Bot(token=TELEGRAM_TOKEN)
    storage = RedisStorage2(host=REDIS_HOST, port=REDIS_PORT, db=1, prefix="fsm")
    dp = Dispatcher(bot, storage=storage)
    logger.info("Telegram bot initialized successfully with Redis cluster")
except Exception as e:
    logger.error(
        "Failed to initialize Telegram bot", exc_info=True, extra={"error": str(e)}
    )
    raise
