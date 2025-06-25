"""
Pool Bot Service

This service runs the actual property bot functionality.
Multiple instances can be created with different bot tokens.
"""
from common.utils.logging_config import setup_logging
import os

# Get bot instance name from environment
BOT_NAME = os.getenv("BOT_NAME", "pool_bot")

# Setup service-specific logger
logger = setup_logging(f"pool_bot_service_{BOT_NAME}") 