# services/telegram_service/app/error_handler.py

import asyncio
from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramUnauthorizedError,
    TelegramAPIError,
    TelegramMigrateToChat,
)
from .bot import bot

# Import service logger
from . import logger
from common.utils.logging_config import log_context

router = Router()


@router.errors()
async def errors_handler(event: ErrorEvent):
    """
    Global error handler for all updates.
    Returns True if the error was handled, False otherwise.
    """
    update = event.update
    exception = event.exception

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
    context = (
        f"Chat ID: {chat_id}, User ID: {user_id}" if chat_id else "Unknown context"
    )

    # Handle specific exceptions
    with log_context(logger, chat_id=chat_id, user_id=user_id, update=update_str):
        # MessageNotModified -> TelegramBadRequest with "message is not modified"
        if isinstance(exception, TelegramBadRequest) and "message is not modified" in str(exception).lower():
            # This happens when the message content has not changed
            logger.warning("Message not modified", extra={"context": context})
            return True

        # MessageToEditNotFound -> TelegramBadRequest with "message to edit not found"
        if isinstance(exception, TelegramBadRequest) and "message to edit not found" in str(exception).lower():
            # Message to edit not found
            logger.warning("Message to edit not found", extra={"context": context})
            return True

        # CantParseEntities -> TelegramBadRequest with "can't parse entities"
        if isinstance(exception, TelegramBadRequest) and "can't parse entities" in str(exception).lower():
            # Markdown or HTML formatting issue
            logger.error("CantParseEntities", extra={"exception": str(exception), "context": context})
            try:
                # Try to send without formatting
                if chat_id:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="Sorry, there was a formatting error in the message. Please try again.",
                    )
            except Exception as e:
                logger.error("Failed to send error message", extra={"error": str(e)})
            return True

        if isinstance(exception, TelegramRetryAfter):
            # Flood control - wait the specified time before retrying
            retry_after = exception.retry_after
            logger.warning("RetryAfter", extra={"retry_after": retry_after, "context": context})
            await asyncio.sleep(retry_after)
            return True

        if isinstance(exception, TelegramForbiddenError):
            # User blocked the bot or user deactivated
            logger.info("Bot blocked or user deactivated", extra={"context": context})
            # You could remove the user from your active users database here
            return True

        if isinstance(exception, TelegramNotFound):
            # Chat not found
            logger.info("Chat not found", extra={"context": context})
            return True

        if isinstance(exception, TelegramMigrateToChat):
            # Group migrated to supergroup
            logger.info("Group migrated to supergroup", extra={"new_chat_id": exception.migrate_to_chat_id, "context": context})
            # You could update the chat ID in your database here
            return True

        if isinstance(exception, TelegramNetworkError):
            # Network issues - log and let it retry
            logger.error("NetworkError", extra={"exception": str(exception), "context": context})
            # Consider implementing an exponential backoff retry here
            await asyncio.sleep(1)  # Simple delay before retry
            return True

        # InvalidQueryID -> TelegramBadRequest with "query is too old"
        if isinstance(exception, TelegramBadRequest) and "query is too old" in str(exception).lower():
            # Expired button press
            logger.warning("InvalidQueryID", extra={"exception": str(exception), "context": context})
            return True

        # MessageToDeleteNotFound -> TelegramBadRequest with "message to delete not found"
        if isinstance(exception, TelegramBadRequest) and "message to delete not found" in str(exception).lower():
            # Message to delete not found
            logger.warning("MessageToDeleteNotFound", extra={"exception": str(exception), "context": context})
            return True

        if isinstance(exception, TelegramBadRequest):
            # Bad request to Telegram API (catch-all for remaining TelegramBadRequest)
            logger.error("BadRequest", extra={"exception": str(exception), "context": context})
            return True

        if isinstance(exception, TelegramUnauthorizedError):
            # User removed the bot or bot was never authorized
            logger.warning("Unauthorized", extra={"exception": str(exception), "context": context})
            return True

        # For other Telegram API errors
        if isinstance(exception, TelegramAPIError):
            logger.error("TelegramAPIError", extra={"exception": str(exception), "context": context})
            return True

        # For any other unexpected errors
        logger.error(
            "Unhandled exception",
            exc_info=True,
            extra={
                "error_type": type(exception).__name__,
                "error_message": str(exception),
            },
        )

        # Log the full update for debugging severe issues
        if update:
            logger.debug("Update details", extra={"update": str(update)})

    # Consider notifying administrators for critical errors here

    # We return False to indicate that we couldn't handle this exception
    # and want it to propagate further
    return False
