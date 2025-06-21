# common/messaging/handlers/support_handler.py

from typing import Union

from common.messaging.unified_platform_utils import safe_send_message, safe_send_menu
from common.utils.logging_config import log_operation, log_context

# Import the handlers logger
from . import logger

# Create a dictionary of support categories for reference
SUPPORT_CATEGORIES = {
    "payment": {
        "uk": "Оплата",
        "en": "Payment",
        "template": "Привіт! У мене є питання щодо оплати. Будь ласка, допоможіть розібратись.",
    },
    "technical": {
        "uk": "Технічні проблеми",
        "en": "Technical Issues",
        "template": "Привіт! Я зіткнувся з технічною проблемою. Опис проблеми: ",
    },
    "other": {
        "uk": "Інше",
        "en": "Other",
        "template": "Привіт! У мене інше питання. Прошу допомоги: ",
    },
}


@log_operation("handle_support_command")
async def handle_support_command(user_id: Union[str, int], platform: str = None):
    """
    Start the support conversation by asking the user to choose a category.
    Works across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier ("telegram",)
    """
    with log_context(logger, user_id=user_id, platform=platform):
        try:
            # Prepare menu options for category selection
            options = [
                {"text": "Оплата", "value": "support_payment"},
                {"text": "Технічні проблеми", "value": "support_technical"},
                {"text": "Інше", "value": "support_other"},
                {"text": "↪️ Назад", "value": "back_to_menu"},
            ]

            # Send the menu across any platform
            await safe_send_menu(
                user_id=user_id,
                text="Будь ласка, оберіть категорію звернення:",
                options=options,
                platform=platform,
            )

            # State management is handled by the calling platform-specific handlers
            return True
        except Exception as e:
            logger.error(
                "Error in handle_support_command",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("handle_support_category")
async def handle_support_category(
    user_id: Union[str, int], category: str, platform: str = None
):
    """
    Process the chosen support category across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        category: Selected support category
        platform: Optional platform identifier ("telegram",)
    """
    with log_context(logger, user_id=user_id, category=category, platform=platform):
        try:
            # Standardize category values
            if category in ["support_payment", "payment", "оплата", "Оплата"]:
                category = "payment"
                template = SUPPORT_CATEGORIES["payment"]["template"]
            elif category in [
                "support_technical",
                "technical",
                "технічні проблеми",
                "Технічні проблеми",
            ]:
                category = "technical"
                template = SUPPORT_CATEGORIES["technical"]["template"]
            elif category in ["support_other", "other", "інше", "Інше"]:
                category = "other"
                template = SUPPORT_CATEGORIES["other"]["template"]
            else:
                category = "general"
                template = "Привіт! У мене є питання."

            # Create platform-specific redirect options
            if platform == "telegram":
                # Telegram uses inline buttons with URLs
                options = [
                    {
                        "text": "Перейти до техпідтримки",
                        "url": f"https://t.me/bookly_beekly?start={category.lower()}",
                    }
                ]
            else:
                # Generic fallback
                options = [
                    {
                        "text": "Звернутися до техпідтримки",
                        "value": f"support:{category.lower()}",
                    }
                ]

            # Add back to menu option
            options.append({"text": "Повернутися в головне меню", "value": "main_menu"})

            # Send instructions with the template
            await safe_send_message(
                user_id=user_id,
                text="Будь ласка, надішліть наступне повідомлення до техпідтримки.",
                platform=platform,
            )

            # Send the template with menu options
            await safe_send_menu(
                user_id=user_id, text=template, options=options, platform=platform
            )

            # State management is handled by the calling platform-specific handlers
            return True
        except Exception as e:
            logger.error(
                "Error in handle_support_category",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "category": category,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            return False
