# services/telegram_service/app/error_handler.py

import asyncio
from aiogram.utils.exceptions import (
    MessageNotModified, CantParseEntities, NetworkError, RetryAfter,
    BadRequest, Unauthorized, InvalidQueryID, TelegramAPIError,
    MessageToDeleteNotFound, BotBlocked, MessageToEditNotFound,
    ChatNotFound, UserDeactivated, MigrateToChat
)
from .bot import dp, bot

# Import service logger
from . import logger
from common.utils.logging_config import log_context


@dp.errors_handler()
async def errors_handler(update, exception):
    """
    Global error handler for all updates.
    Returns True if the error was handled, False otherwise.
    """

    # Log the update that caused the error
    update_str = str(update) if update else "No update"
    if len(update_str) > 100:
        update_str = f"{update_str[:97]}..."

    chat_id = None
    user_id = None

    # Extract chat ID and user ID where possible for better logging
    if update and update.message:
        chat_id = update.message.chat.id
        user_id = update.message.from_user.id
    elif update and update.callback_query:
        chat_id = update.callback_query.message.chat.id
        user_id = update.callback_query.from_user.id

    # Log the context of the error
    context = f"Chat ID: {chat_id}, User ID: {user_id}" if chat_id else "Unknown context"

    # Handle specific exceptions
    with log_context(logger, chat_id=chat_id, user_id=user_id, update=update_str):
        if isinstance(exception, MessageNotModified):
            # This happens when the message content has not changed
            logger.warning(f'Message not modified: {context}')
            return True

        if isinstance(exception, MessageToEditNotFound):
            # Message to edit not found
            logger.warning(f'Message to edit not found: {context}')
            return True

        if isinstance(exception, CantParseEntities):
            # Markdown or HTML formatting issue
            logger.error(f'CantParseEntities: {exception} | {context}')
            try:
                # Try to send without formatting
                if chat_id:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="Sorry, there was a formatting error in the message. Please try again."
                    )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
            return True

        if isinstance(exception, RetryAfter):
            # Flood control - wait the specified time before retrying
            retry_after = exception.timeout
            logger.warning(f'RetryAfter: {retry_after} seconds | {context}')
            await asyncio.sleep(retry_after)
            return True

        if isinstance(exception, BotBlocked):
            # User blocked the bot
            logger.info(f'Bot blocked by user: {context}')
            # You could remove the user from your active users database here
            return True

        if isinstance(exception, ChatNotFound):
            # Chat not found
            logger.info(f'Chat not found: {context}')
            return True

        if isinstance(exception, UserDeactivated):
            # User account deleted
            logger.info(f'User deactivated: {context}')
            # You could remove the user from your active users database here
            return True

        if isinstance(exception, MigrateToChat):
            # Group migrated to supergroup
            logger.info(f'Group migrated to supergroup. New chat id: {exception.migrate_to_chat_id} | {context}')
            # You could update the chat ID in your database here
            return True

        if isinstance(exception, NetworkError):
            # Network issues - log and let it retry
            logger.error(f'NetworkError: {exception} | {context}')
            # Consider implementing an exponential backoff retry here
            await asyncio.sleep(1)  # Simple delay before retry
            return True

        if isinstance(exception, BadRequest):
            # Bad request to Telegram API
            logger.error(f'BadRequest: {exception} | {context}')
            return True

        if isinstance(exception, Unauthorized):
            # User removed the bot or bot was never authorized
            logger.warning(f'Unauthorized: {exception} | {context}')
            return True

        if isinstance(exception, InvalidQueryID):
            # Expired button press
            logger.warning(f'InvalidQueryID: {exception} | {context}')
            return True

        if isinstance(exception, MessageToDeleteNotFound):
            # Message to delete not found
            logger.warning(f'MessageToDeleteNotFound: {exception} | {context}')
            return True

        # For other Telegram API errors
        if isinstance(exception, TelegramAPIError):
            logger.error(f'TelegramAPIError: {exception} | {context}')
            return True

        # For any other unexpected errors
        logger.error('Unhandled exception', exc_info=True, extra={
            'error_type': type(exception).__name__,
            'error_message': str(exception)
        })

        # Log the full update for debugging severe issues
        if update:
            logger.debug(f'Update: {update}')

    # Consider notifying administrators for critical errors here

    # We return False to indicate that we couldn't handle this exception
    # and want it to propagate further
    return False