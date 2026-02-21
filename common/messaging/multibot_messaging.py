"""
Multi-Bot Messaging Module

Routes messages to the correct pool bot based on user assignments.
"""
from typing import Optional, Dict, Any, List, Union
from collections import defaultdict
import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from common.db.database import get_db_session
from common.db.models.user import User
from common.config_multibot import multibot_config
from common.utils.logging_config import log_operation, log_context, setup_logging
from common.utils.retry_utils import retry_with_exponential_backoff
from .telegram_messaging import TelegramMessaging

logger = setup_logging(__name__)

# Cache for bot instances
_bot_instances: Dict[str, Bot] = {}


def get_bot_instance(bot_name: str) -> Optional[Bot]:
    """Get or create a bot instance for the given bot name"""
    if bot_name not in _bot_instances:
        bot_config = multibot_config.get_bot_by_name(bot_name)
        if not bot_config:
            logger.error("No configuration found for bot", extra={"bot_name": bot_name})
            return None
        
        try:
            _bot_instances[bot_name] = Bot(token=bot_config.token)
            logger.info("Created bot instance", extra={"bot_name": bot_name})
        except Exception as e:
            logger.error(
                "Failed to create bot instance",
                exc_info=True,
                extra={"bot_name": bot_name, "error": str(e)}
            )
            return None
    
    return _bot_instances.get(bot_name)


class MultiBotMessaging:
    """Handles messaging across multiple pool bots"""
    
    @staticmethod
    @log_operation("send_to_users_multibot")
    async def send_to_users(
        user_ids: List[int],
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send message to multiple users via their assigned bots"""
        
        # Group users by their assigned bot
        users_by_bot = defaultdict(list)
        
        with get_db_session() as session:
            users = session.query(User).filter(
                User.id.in_(user_ids),
                User.assigned_bot_name.isnot(None)
            ).all()
            
            for user in users:
                users_by_bot[user.assigned_bot_name].append({
                    'user_id': user.id,
                    'telegram_id': user.telegram_id
                })
        
        # Send messages via appropriate bots
        results = {
            'success': 0,
            'failed': 0,
            'no_bot_assigned': len(user_ids) - len(users),
            'by_bot': {}
        }
        
        # Process each bot's users
        tasks = []
        for bot_name, bot_users in users_by_bot.items():
            task = MultiBotMessaging._send_batch_to_bot(
                bot_name=bot_name,
                users=bot_users,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
            tasks.append(task)
        
        # Execute all bot sends concurrently
        if tasks:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for bot_name, result in zip(users_by_bot.keys(), batch_results):
                if isinstance(result, Exception):
                    logger.error(
                        "Error sending via bot",
                        exc_info=result,
                        extra={"bot_name": bot_name}
                    )
                    results['failed'] += len(users_by_bot[bot_name])
                    results['by_bot'][bot_name] = {'error': str(result)}
                else:
                    results['success'] += result['success']
                    results['failed'] += result['failed']
                    results['by_bot'][bot_name] = result
        
        logger.info(
            "Multi-bot send completed",
            extra={
                'total_users': len(user_ids),
                'success': results['success'],
                'failed': results['failed'],
                'no_bot': results['no_bot_assigned'],
                'bots_used': len(users_by_bot)
            }
        )
        
        return results
    
    @staticmethod
    async def _send_batch_to_bot(
        bot_name: str,
        users: List[Dict[str, Any]],
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send messages to users via a specific bot"""
        bot = get_bot_instance(bot_name)
        if not bot:
            return {'success': 0, 'failed': len(users), 'error': 'Bot not available'}
        
        messaging = TelegramMessaging(bot)
        success = 0
        failed = 0
        
        # Send to each user
        tasks = []
        for user in users:
            task = messaging.send_text(
                user_id=user['telegram_id'],
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
            tasks.append(task)
        
        # Execute sends concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for user, result in zip(users, results):
            if isinstance(result, Exception) or result is None:
                failed += 1
                logger.warning(
                    "Failed to send to user via bot",
                    extra={
                        'bot_name': bot_name,
                        'user_id': user['user_id'],
                        'telegram_id': user['telegram_id'],
                        'error': str(result) if isinstance(result, Exception) else 'No result'
                    }
                )
            else:
                success += 1
        
        return {'success': success, 'failed': failed}
    
    @staticmethod
    @log_operation("send_ad_multibot")
    async def send_ad_to_users(
        user_ids: List[int],
        ad_data: Dict[str, Any],
        image_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send ad to multiple users via their assigned bots"""
        
        # Group users by their assigned bot
        users_by_bot = defaultdict(list)
        
        with get_db_session() as session:
            users = session.query(User).filter(
                User.id.in_(user_ids),
                User.assigned_bot_name.isnot(None)
            ).all()
            
            for user in users:
                users_by_bot[user.assigned_bot_name].append({
                    'user_id': user.id,
                    'telegram_id': user.telegram_id
                })
        
        # Send ads via appropriate bots
        results = {
            'success': 0,
            'failed': 0,
            'no_bot_assigned': len(user_ids) - len(users),
            'by_bot': {}
        }
        
        # Process each bot's users concurrently
        tasks = []
        for bot_name, bot_users in users_by_bot.items():
            task = MultiBotMessaging._send_ad_batch_to_bot(
                bot_name=bot_name,
                users=bot_users,
                ad_data=ad_data,
                image_url=image_url,
                **kwargs
            )
            tasks.append(task)
        
        if tasks:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for bot_name, result in zip(users_by_bot.keys(), batch_results):
                if isinstance(result, Exception):
                    logger.error(
                        "Error sending ads via bot",
                        exc_info=result,
                        extra={"bot_name": bot_name}
                    )
                    results['failed'] += len(users_by_bot[bot_name])
                    results['by_bot'][bot_name] = {'error': str(result)}
                else:
                    results['success'] += result['success']
                    results['failed'] += result['failed']
                    results['by_bot'][bot_name] = result
        
        return results
    
    @staticmethod
    async def _send_ad_batch_to_bot(
        bot_name: str,
        users: List[Dict[str, Any]],
        ad_data: Dict[str, Any],
        image_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send ad to users via a specific bot"""
        bot = get_bot_instance(bot_name)
        if not bot:
            return {'success': 0, 'failed': len(users), 'error': 'Bot not available'}
        
        messaging = TelegramMessaging(bot)
        success = 0
        failed = 0
        
        # Send to each user
        tasks = []
        for user in users:
            task = messaging.send_ad(
                user_id=user['telegram_id'],
                ad_data=ad_data,
                image_url=image_url,
                **kwargs
            )
            tasks.append(task)
        
        # Execute sends concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for user, result in zip(users, results):
            if isinstance(result, Exception) or result is None:
                failed += 1
            else:
                success += 1
        
        return {'success': success, 'failed': failed}


# Global instance
multibot_messaging = MultiBotMessaging() 