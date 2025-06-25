"""
Bot Assignment Service

Manages the assignment of users to pool bots and tracks bot capacity.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from common.db.database import get_db_session
from common.db.models.user import User
from common.config_multibot import multibot_config
from common.utils.logging_config import log_operation, log_context, setup_logging

logger = setup_logging(__name__)

class BotAssignmentService:
    """Manages user assignment to pool bots"""
    
    @staticmethod
    @log_operation("get_bot_user_counts")
    def get_bot_user_counts(session: Session) -> Dict[str, int]:
        """Get current user count for each bot"""
        counts = session.query(
            User.assigned_bot_name,
            func.count(User.id)
        ).filter(
            User.assigned_bot_name.isnot(None),
            User.is_active == True
        ).group_by(User.assigned_bot_name).all()
        
        return {bot_name: count for bot_name, count in counts}
    
    @staticmethod
    @log_operation("find_available_bot")
    def find_available_bot(session: Session) -> Optional[str]:
        """Find a bot with available capacity"""
        user_counts = BotAssignmentService.get_bot_user_counts(session)
        active_bots = multibot_config.get_active_bots()
        
        # Find bot with most available capacity
        best_bot = None
        max_available = 0
        
        for bot in active_bots:
            current_users = user_counts.get(bot.name, 0)
            available_capacity = bot.max_users - current_users
            
            if available_capacity > max_available:
                max_available = available_capacity
                best_bot = bot.name
                
            logger.info(
                "Bot capacity check",
                extra={
                    "bot_name": bot.name,
                    "current_users": current_users,
                    "max_users": bot.max_users,
                    "available": available_capacity
                }
            )
        
        if max_available <= 0:
            logger.warning("All bots at capacity!")
            return None
            
        return best_bot
    
    @staticmethod
    @log_operation("assign_user_to_bot")
    def assign_user_to_bot(
        session: Session,
        user_id: int,
        dispatcher_chat_id: str
    ) -> Optional[Dict[str, Any]]:
        """Assign a user to an available bot"""
        # Find available bot
        bot_name = BotAssignmentService.find_available_bot(session)
        if not bot_name:
            return None
        
        bot_config = multibot_config.get_bot_by_name(bot_name)
        if not bot_config:
            return None
        
        # Update user assignment
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        user.assigned_bot_name = bot_name
        user.assigned_bot_username = bot_config.username
        user.assignment_date = datetime.utcnow()
        user.dispatcher_chat_id = dispatcher_chat_id
        
        session.commit()
        
        logger.info(
            "User assigned to bot",
            extra={
                "user_id": user_id,
                "bot_name": bot_name,
                "bot_username": bot_config.username
            }
        )
        
        return {
            "bot_name": bot_name,
            "bot_username": bot_config.username,
            "bot_token": bot_config.token
        }
    
    @staticmethod
    @log_operation("get_user_bot_assignment")
    def get_user_bot_assignment(
        session: Session,
        telegram_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get user's current bot assignment"""
        user = session.query(User).filter(
            User.telegram_id == telegram_id
        ).first()
        
        if not user or not user.assigned_bot_name:
            return None
        
        bot_config = multibot_config.get_bot_by_name(user.assigned_bot_name)
        if not bot_config:
            return None
        
        return {
            "bot_name": user.assigned_bot_name,
            "bot_username": user.assigned_bot_username,
            "bot_token": bot_config.token,
            "assignment_date": user.assignment_date
        }
    
    @staticmethod
    @log_operation("reassign_user")
    def reassign_user(
        session: Session,
        user_id: int,
        new_bot_name: str
    ) -> bool:
        """Manually reassign a user to a different bot"""
        bot_config = multibot_config.get_bot_by_name(new_bot_name)
        if not bot_config:
            return False
        
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        old_bot = user.assigned_bot_name
        user.assigned_bot_name = new_bot_name
        user.assigned_bot_username = bot_config.username
        user.assignment_date = datetime.utcnow()
        
        session.commit()
        
        logger.info(
            "User reassigned",
            extra={
                "user_id": user_id,
                "old_bot": old_bot,
                "new_bot": new_bot_name
            }
        )
        
        return True
    
    @staticmethod
    @log_operation("get_bot_statistics")
    def get_bot_statistics(session: Session) -> Dict[str, Any]:
        """Get statistics for all bots"""
        user_counts = BotAssignmentService.get_bot_user_counts(session)
        active_bots = multibot_config.get_active_bots()
        
        stats = {
            "total_capacity": multibot_config.get_total_capacity(),
            "total_users": sum(user_counts.values()),
            "bots": []
        }
        
        for bot in active_bots:
            current_users = user_counts.get(bot.name, 0)
            stats["bots"].append({
                "name": bot.name,
                "username": bot.username,
                "current_users": current_users,
                "max_users": bot.max_users,
                "utilization": f"{(current_users / bot.max_users * 100):.1f}%",
                "available_slots": bot.max_users - current_users
            })
        
        stats["overall_utilization"] = f"{(stats['total_users'] / stats['total_capacity'] * 100):.1f}%"
        
        return stats

# Global instance
bot_assignment_service = BotAssignmentService() 