"""
Multi-Bot Configuration for Dispatcher Pattern

This configuration manages the pool of subscription-mailing bots
that handle the actual user interactions and notifications.
"""
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

from common.utils.secrets import get_secret

load_dotenv()

@dataclass
class BotConfig:
    """Configuration for a single bot in the pool"""
    name: str  # Internal identifier (e.g., "bot_1")
    token: str  # Bot token from BotFather
    username: str  # Bot username (e.g., "@YourBot_1")
    max_users: int = 5000  # Maximum users per bot
    is_active: bool = True  # Whether bot is currently active

class MultiBotConfig:
    """Manages the pool of bots"""
    
    def __init__(self):
        self.dispatcher_token = get_secret("telegram_dispatcher_token", fallback_env="TELEGRAM_DISPATCHER_TOKEN")
        self.dispatcher_username = os.getenv("TELEGRAM_DISPATCHER_USERNAME", "@YourDispatcherBot")
        self.pool_bots: List[BotConfig] = []
        self._load_bot_pool()
    
    def _load_bot_pool(self):
        """Load bot pool from environment variables"""
        # Expected format: BOT_POOL_1_TOKEN, BOT_POOL_1_USERNAME, etc.
        bot_index = 1
        while True:
            token = get_secret(f"bot_pool_{bot_index}_token", fallback_env=f"BOT_POOL_{bot_index}_TOKEN")
            if not token:
                break
                
            username = os.getenv(f"BOT_POOL_{bot_index}_USERNAME", f"@YourBot_{bot_index}")
            max_users = int(os.getenv(f"BOT_POOL_{bot_index}_MAX_USERS", "5000"))
            is_active = os.getenv(f"BOT_POOL_{bot_index}_ACTIVE", "true").lower() == "true"
            
            # Extract flower name from username for internal naming
            flower_name = username.replace("@hto_de_", "").replace("_bot", "") if username.startswith("@hto_de_") else f"bot_{bot_index}"
            
            bot_config = BotConfig(
                name=flower_name,
                token=token,
                username=username,
                max_users=max_users,
                is_active=is_active
            )
            self.pool_bots.append(bot_config)
            bot_index += 1
    
    def get_dispatcher_config(self) -> Dict[str, str]:
        """Get dispatcher bot configuration"""
        return {
            "token": self.dispatcher_token,
            "username": self.dispatcher_username
        }
    
    def get_active_bots(self) -> List[BotConfig]:
        """Get list of active bots in the pool"""
        return [bot for bot in self.pool_bots if bot.is_active]
    
    def get_bot_by_name(self, name: str) -> Optional[BotConfig]:
        """Get specific bot configuration by name"""
        for bot in self.pool_bots:
            if bot.name == name:
                return bot
        return None
    
    def get_total_capacity(self) -> int:
        """Calculate total user capacity across all active bots"""
        return sum(bot.max_users for bot in self.get_active_bots())

# Global instance
multibot_config = MultiBotConfig()

# Example .env configuration:
"""
# Dispatcher Bot
TELEGRAM_DISPATCHER_TOKEN=your_dispatcher_bot_token_here
TELEGRAM_DISPATCHER_USERNAME=@YourMainBot

# Bot Pool
BOT_POOL_1_TOKEN=first_pool_bot_token
BOT_POOL_1_USERNAME=@YourBot_1
BOT_POOL_1_MAX_USERS=5000
BOT_POOL_1_ACTIVE=true

BOT_POOL_2_TOKEN=second_pool_bot_token
BOT_POOL_2_USERNAME=@YourBot_2
BOT_POOL_2_MAX_USERS=5000
BOT_POOL_2_ACTIVE=true

# Add more bots as needed...
BOT_POOL_20_TOKEN=twentieth_pool_bot_token
BOT_POOL_20_USERNAME=@YourBot_20
BOT_POOL_20_MAX_USERS=5000
BOT_POOL_20_ACTIVE=true
""" 