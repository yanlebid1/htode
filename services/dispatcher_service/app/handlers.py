# services/dispatcher_service/app/handlers.py

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .bot import dp, bot
from common.db.database import get_db_session
from common.db.models.user import User
from common.services.bot_assignment_service import bot_assignment_service
from common.utils.logging_config import log_operation, log_context
from . import logger


@dp.message_handler(commands=['start'])
@log_operation("dispatcher_start")
async def start_handler(message: types.Message):
    """Handle /start command - assign user to a pool bot"""
    telegram_id = str(message.from_user.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    with log_context(
        logger, 
        telegram_id=telegram_id,
        username=username
    ):
        with get_db_session() as session:
            # Check if user exists
            user = session.query(User).filter(
                User.telegram_id == telegram_id
            ).first()
            
            if user and user.assigned_bot_name:
                # User already assigned
                logger.info(
                    "User already assigned to bot",
                    extra={
                        "user_id": user.id,
                        "assigned_bot": user.assigned_bot_name
                    }
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"Перейти до бота {user.assigned_bot_username}",
                        url=f"https://t.me/{user.assigned_bot_username[1:]}"  # Remove @
                    )
                ]])
                
                await message.answer(
                    f"🏠 Вітаємо, {first_name}!\n\n"
                    f"Ви вже зареєстровані в нашій системі.\n"
                    f"Ваш персональний бот: {user.assigned_bot_username}\n\n"
                    f"Натисніть кнопку нижче, щоб перейти до вашого бота:",
                    reply_markup=keyboard
                )
                return
            
            # Create new user if doesn't exist
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    created_at=datetime.utcnow()
                )
                session.add(user)
                session.commit()
                logger.info(
                    "Created new user",
                    extra={"user_id": user.id}
                )
            
            # Assign to available bot
            assignment = bot_assignment_service.assign_user_to_bot(
                session=session,
                user_id=user.id,
                dispatcher_chat_id=telegram_id
            )
            
            if not assignment:
                # All bots at capacity
                await message.answer(
                    "⚠️ На жаль, всі боти зараз завантажені.\n"
                    "Будь ласка, спробуйте пізніше або зв'яжіться з підтримкою."
                )
                logger.warning(
                    "Failed to assign user - all bots at capacity",
                    extra={"user_id": user.id}
                )
                return
            
            # Successfully assigned
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"Перейти до бота {assignment['bot_username']}",
                    url=f"https://t.me/{assignment['bot_username'][1:]}"  # Remove @
                )
            ]])
            
            await message.answer(
                f"🏠 Вітаємо, {first_name}!\n\n"
                f"Для вас підібрано персонального бота: {assignment['bot_username']}\n\n"
                f"Натисніть кнопку нижче, щоб розпочати роботу:",
                reply_markup=keyboard
            )
            
            logger.info(
                "User successfully assigned to bot",
                extra={
                    "user_id": user.id,
                    "bot_name": assignment['bot_name'],
                    "bot_username": assignment['bot_username']
                }
            )


@dp.message_handler(commands=['status'])
@log_operation("dispatcher_status")
async def status_handler(message: types.Message):
    """Show system status (admin only)"""
    # Check if user is admin (you should implement proper admin check)
    if message.from_user.id not in [123456789]:  # Replace with actual admin IDs
        await message.answer("⛔ Ця команда доступна тільки адміністраторам")
        return
    
    with get_db_session() as session:
        stats = bot_assignment_service.get_bot_statistics(session)
    
    # Format status message
    status_text = (
        "📊 <b>Статус системи</b>\n\n"
        f"👥 Загальна місткість: {stats['total_capacity']:,} користувачів\n"
        f"👤 Поточні користувачі: {stats['total_users']:,}\n"
        f"📈 Загальне використання: {stats['overall_utilization']}\n\n"
        "<b>Статус ботів:</b>\n"
    )
    
    for bot in stats['bots']:
        emoji = "🟢" if float(bot['utilization'].rstrip('%')) < 90 else "🔴"
        status_text += (
            f"\n{emoji} {bot['username']}\n"
            f"   Користувачі: {bot['current_users']:,}/{bot['max_users']:,} "
            f"({bot['utilization']})\n"
        )
    
    await message.answer(status_text, parse_mode='HTML')


@dp.message_handler(commands=['reassign'])
@log_operation("dispatcher_reassign")
async def reassign_handler(message: types.Message):
    """Reassign user to different bot (admin only)"""
    # Admin check
    if message.from_user.id not in [123456789]:  # Replace with actual admin IDs
        await message.answer("⛔ Ця команда доступна тільки адміністраторам")
        return
    
    # Parse command: /reassign user_id new_bot_name
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "Використання: /reassign <user_id> <bot_name>\n"
            "Приклад: /reassign 12345 bot_5"
        )
        return
    
    try:
        user_id = int(parts[1])
        new_bot_name = parts[2]
        
        with get_db_session() as session:
            success = bot_assignment_service.reassign_user(
                session=session,
                user_id=user_id,
                new_bot_name=new_bot_name
            )
            
            if success:
                await message.answer(f"✅ Користувач {user_id} переміщений до {new_bot_name}")
            else:
                await message.answer(f"❌ Не вдалося перемістити користувача")
                
    except ValueError:
        await message.answer("❌ Невірний формат user_id")
    except Exception as e:
        await message.answer(f"❌ Помилка: {str(e)}")


@dp.message_handler()
@log_operation("dispatcher_default")
async def default_handler(message: types.Message):
    """Handle all other messages"""
    telegram_id = str(message.from_user.id)
    
    with get_db_session() as session:
        user = session.query(User).filter(
            User.telegram_id == telegram_id
        ).first()
        
        if user and user.assigned_bot_username:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"Перейти до бота {user.assigned_bot_username}",
                    url=f"https://t.me/{user.assigned_bot_username[1:]}"
                )
            ]])
            
            await message.answer(
                f"Будь ласка, використовуйте вашого персонального бота: {user.assigned_bot_username}",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                "Будь ласка, надішліть /start для початку роботи"
            )


# Import datetime for user creation
from datetime import datetime 