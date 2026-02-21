# services/dispatcher_service/app/bot.py

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from common.config_multibot import multibot_config
from common.config import REDIS_URL
import os
import urllib.parse

# Import service logger
from . import logger

# Get dispatcher bot configuration
dispatcher_config = multibot_config.get_dispatcher_config()

if not dispatcher_config['token']:
    logger.error("TELEGRAM_DISPATCHER_TOKEN not set!")
    raise ValueError("Dispatcher bot token is required")

# Parse Redis URL for state storage
REDIS_STATE_URL = os.getenv("REDIS_STATE_URL", REDIS_URL)
parsed_redis_url = urllib.parse.urlparse(REDIS_STATE_URL)
REDIS_HOST = parsed_redis_url.hostname or "redis_state"
REDIS_PORT = parsed_redis_url.port or 6379

# Initialize dispatcher bot
logger.info(
    "Initializing Dispatcher bot",
    extra={
        "username": dispatcher_config['username'],
        "redis_host": REDIS_HOST,
        "redis_port": REDIS_PORT
    }
)

try:
    bot = Bot(token=dispatcher_config['token'])
    storage = RedisStorage.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/2")
    dp = Dispatcher(storage=storage)
    logger.info("Dispatcher bot initialized successfully")
except Exception as e:
    logger.error(
        "Failed to initialize Dispatcher bot",
        exc_info=True,
        extra={"error": str(e)}
    )
    raise
