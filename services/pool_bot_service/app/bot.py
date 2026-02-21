# services/pool_bot_service/app/bot.py

import hashlib
import os
import urllib.parse
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from common.config_multibot import multibot_config
from common.config import REDIS_URL
from . import logger, BOT_NAME

# Get bot configuration based on BOT_NAME environment variable
bot_config = multibot_config.get_bot_by_name(BOT_NAME)

if not bot_config:
    # Fallback to environment variable if not in multibot config
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("No configuration found for bot", extra={"bot_name": BOT_NAME})
        raise ValueError(f"Bot token not found for {BOT_NAME}")

    # Create minimal config from env
    class MinimalConfig:
        def __init__(self):
            self.name = BOT_NAME
            self.token = BOT_TOKEN
            self.username = os.getenv("BOT_USERNAME", f"@{BOT_NAME}")

    bot_config = MinimalConfig()

# Parse Redis URL for state storage
REDIS_STATE_URL = os.getenv("REDIS_STATE_URL", REDIS_URL)
parsed_redis_url = urllib.parse.urlparse(REDIS_STATE_URL)
REDIS_HOST = parsed_redis_url.hostname or "redis_state"
REDIS_PORT = parsed_redis_url.port or 6379

# Different Redis DB for each bot (deterministic across restarts)
redis_db = hashlib.md5(BOT_NAME.encode()).digest()[0] % 16

# Initialize bot
logger.info(
    "Initializing Pool bot",
    extra={
        "bot_name": bot_config.name,
        "username": bot_config.username if hasattr(bot_config, 'username') else 'unknown',
        "redis_host": REDIS_HOST,
        "redis_port": REDIS_PORT,
        "redis_db": redis_db
    }
)

try:
    bot = Bot(token=bot_config.token)
    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{redis_db}")
    dp = Dispatcher(storage=storage)
    logger.info("Pool bot initialized successfully", extra={"bot_name": BOT_NAME})
except Exception as e:
    logger.error(
        "Failed to initialize Pool bot",
        exc_info=True,
        extra={"bot_name": BOT_NAME, "error": str(e)}
    )
    raise
