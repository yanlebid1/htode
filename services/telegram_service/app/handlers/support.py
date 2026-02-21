# services/telegram_service/app/handlers/support.py

from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from ..states.support_states import SupportStates
from common.messaging.handlers.support_handler import (
    handle_support_command,
    handle_support_category,
)
from ..utils.message_utils import safe_answer_callback_query, delete_message_safe, safe_send_message

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context

router = Router()

# store trigger info for support menu
SUPPORT_TRIGGER = {}


@router.message(F.text == "🧑‍💻 Техпідтримка")
@log_operation("handle_support_command_telegram")
async def handle_support_command_telegram(message: types.Message, state: FSMContext):
    """
    Start the support conversation by asking the user to choose a category.
    Uses the unified support handler for cross-platform consistency.
    """
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id, action="start_support"):
        # Set the state first since we have direct access to the state manager
        await state.set_state(SupportStates.waiting_for_category)

        bot_msg = await handle_support_command(
            message.from_user.id, platform="telegram"
        )

        # Save trigger and bot msg ids
        SUPPORT_TRIGGER[user_id] = {
            "trigger_id": message.message_id,
            "bot_id": getattr(bot_msg, "message_id", None),
        }
        logger.info("Support conversation started", extra={"user_id": user_id})


@router.message(
    F.text.in_(["Оплата", "Технічні проблеми", "Інше"]),
    SupportStates.waiting_for_category,
)
@log_operation("process_support_category_telegram")
async def process_support_category_telegram(message: types.Message, state: FSMContext):
    """
    Process the chosen support category.
    Uses the unified support handler for cross-platform consistency.
    """
    user_id = message.from_user.id
    category = message.text

    with log_context(logger, user_id=user_id, category=category):
        # End the FSM as no further input is needed
        await state.clear()

        # Use the unified handler for category processing
        await handle_support_category(
            message.from_user.id, category, platform="telegram"
        )
        logger.info(
            "Support category processed",
            extra={"user_id": user_id, "category": category},
        )


@router.callback_query(
    F.data.in_(["support_payment", "support_technical", "support_other", "back_to_menu"]),
    SupportStates.waiting_for_category,
)
@log_operation("process_support_category_telegram_cb")
async def process_support_category_telegram_cb(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handle support category selected via inline keyboard callback."""
    user_id = callback_query.from_user.id
    data = callback_query.data

    # If user tapped back, simply finish state and return to main menu
    if data == "back_to_menu":
        await state.clear()

        # delete trigger and menu messages
        info = SUPPORT_TRIGGER.pop(user_id, None)
        if info:
            if info.get("bot_id"):
                await delete_message_safe(user_id, info["bot_id"])
            if info.get("trigger_id"):
                await delete_message_safe(user_id, info["trigger_id"])

        try:
            await callback_query.message.delete()
        except Exception:
            pass

        from ..keyboards import main_menu_keyboard

        await safe_send_message(
            chat_id=user_id, text="Головне меню:", reply_markup=main_menu_keyboard()
        )
        await safe_answer_callback_query(callback_query.id)
        return

    # Map callback data to category string expected by handler
    category_mapping = {
        "support_payment": "payment",
        "support_technical": "technical",
        "support_other": "other",
    }
    category = category_mapping.get(data, "other")

    # Finish state before proceeding
    await state.clear()

    # Delegate to unified handler
    await handle_support_category(user_id, category, platform="telegram")

    # Clean up menu and trigger messages
    info = SUPPORT_TRIGGER.pop(user_id, None)
    if info:
        if info.get("bot_id"):
            await delete_message_safe(user_id, info["bot_id"])
        if info.get("trigger_id"):
            await delete_message_safe(user_id, info["trigger_id"])

    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await safe_answer_callback_query(callback_query.id)


# Optional helper function for Telegram-specific support redirect functionality
def create_support_telegram_link(category: str) -> str:
    """
    Create a Telegram deep link for support redirection.

    Args:
        category: Support category (payment, technical, other)

    Returns:
        Deep link URL for Telegram
    """
    return f"https://t.me/bookly_beekly?start={category.lower()}"
