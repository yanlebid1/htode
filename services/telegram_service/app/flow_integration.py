# services/telegram_service/app/flow_integration.py

from aiogram import types
from aiogram.dispatcher import FSMContext

from .bot import dp
from common.messaging.unified_flow import flow_library
from common.messaging.unified_flow import (
    check_and_process_flow,
    process_flow_action,
    show_available_flows
)

# Import service logger and logging utilities
from . import logger
from common.utils.logging_config import log_operation, log_context


@dp.message_handler(lambda message: True, state="*")
@log_operation("flow_message_handler")
async def flow_message_handler(message: types.Message, state: FSMContext = None):
    """
    Message handler that checks for active flows before letting other handlers process.
    This has a low priority (100) so specific command handlers will take precedence.
    """
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    with log_context(logger, user_id=user_id, message_text=text[:100]):  # Limit message length in logs
        # Get any state data for extra context
        state_data = {}
        if state:
            state_data = await state.get_data()

        # First check if an active flow wants to handle this message
        handled = await check_and_process_flow(
            user_id=user_id,
            platform="telegram",
            message_text=text,
            extra_context=state_data
        )

        if handled:
            logger.info("Message handled by flow", extra={
                "user_id": user_id,
                "flow_handled": True
            })
            return


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("flow:"), state="*")
@log_operation("flow_callback_handler")
async def flow_callback_handler(callback_query: types.CallbackQuery, state: FSMContext = None):
    """
    Handler for flow-specific callbacks.
    """
    user_id = callback_query.from_user.id
    action_text = callback_query.data

    with log_context(logger, user_id=user_id, callback_data=action_text):
        # Process the flow action
        if await process_flow_action(user_id, "telegram", action_text):
            await callback_query.answer("Action processed")
            logger.info("Flow action processed", extra={
                "user_id": user_id,
                "action": action_text
            })
        else:
            await callback_query.answer("Invalid flow action")
            logger.warning("Invalid flow action", extra={
                "user_id": user_id,
                "action": action_text
            })


# Command handler for starting property search
@dp.message_handler(commands=['search', 'find', 'property'])
async def start_property_search(message: types.Message):
    """
    Start the property search flow via command
    """
    user_id = message.from_user.id

    # Start the property search flow
    await flow_library.start_flow("property_search", user_id, "telegram")


# Command handler for starting subscription management
@dp.message_handler(commands=['subscribe', 'subscription'])
async def start_subscription_flow(message: types.Message):
    """
    Start the subscription management flow via command
    """
    user_id = message.from_user.id

    # Start the subscription flow
    await flow_library.start_flow("subscription", user_id, "telegram")


# Command handler for showing all available flows
@dp.message_handler(commands=['flows'])
async def show_flows_command(message: types.Message):
    """
    Show all available flows to the user
    """
    user_id = message.from_user.id

    await show_available_flows(user_id, "telegram")


# Function to create a Telegram inline keyboard for flows
def create_flow_keyboard(flow_name: str, actions: list):
    """
    Create an inline keyboard for flow operations.

    Args:
        flow_name: Name of the flow
        actions: List of action dictionaries with 'text' and 'action' keys
                (action can be 'start', 'end', or 'state_X')

    Returns:
        InlineKeyboardMarkup
    """
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    for action_info in actions:
        text = action_info['text']
        action = action_info['action']

        # Create button with appropriate callback data
        keyboard.insert(
            types.InlineKeyboardButton(
                text=text,
                callback_data=f"flow:{flow_name}:{action}"
            )
        )

    return keyboard