# common/messaging/service.py

from typing import Dict, Any, Optional, List

from .unified_interface import MessagingInterface
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger


class MessagingService:
    """Telegram-only messaging service (multi-platform support removed)."""

    def __init__(self):
        # Single slot for telegram messenger
        self._telegram: Optional[MessagingInterface] = None

    @log_operation("register_messenger")
    def register_messenger(self, _platform: str, messenger: MessagingInterface) -> None:
        """Register the single Telegram messenger (platform arg ignored)."""
        self._telegram = messenger
        logger.info("Telegram messenger registered")

    def get_messenger(self, *_unused) -> Optional[MessagingInterface]:
        """Always return the Telegram messenger instance (or None if not yet registered)."""
        return self._telegram

    async def get_user_platform(self, user_id: int) -> tuple[str, str]:
        """Return Telegram as the only platform plus the telegram_id."""
        from common.messaging.unified_platform_utils import resolve_user_id

        _, _, telegram_id = resolve_user_id(user_id)
        return "telegram", telegram_id

    async def get_messenger_for_user(
        self, user_id: int
    ) -> tuple[str, str, Optional[MessagingInterface]]:
        """Return telegram messenger and id for user (None if messenger unregistered)."""
        _, _, telegram_id = await self.get_user_platform(user_id)
        return "telegram", telegram_id, self._telegram

    @log_operation("send_notification")
    async def send_notification(
        self,
        user_id: int,
        text: str,
        image_url: Optional[str] = None,
        options: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> bool:
        """
        Send a notification to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            text: Message text
            image_url: Optional image URL
            options: Optional list of menu options
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        from common.messaging.unified_platform_utils import resolve_user_id

        with log_context(
            logger,
            user_id=user_id,
            has_image=bool(image_url),
            has_options=bool(options),
        ):
            # Get platform info using resolve_user_id
            _, platform_name, platform_id = resolve_user_id(user_id)

            if not platform_name or not platform_id:
                logger.warning(
                    "No messaging platform found for user", extra={"user_id": user_id}
                )
                return False

            messenger = self.get_messenger(platform_name)
            if not messenger:
                logger.error(
                    "No messenger implementation registered for platform",
                    extra={"platform": platform_name},
                )
                return False

            try:
                logger.debug(
                    "Sending notification",
                    extra={
                        "platform": platform_name,
                        "platform_id": platform_id[:10],
                        "text_length": len(text),
                        "has_image": bool(image_url),
                        "has_options": bool(options),
                    },
                )

                if options:
                    # Send as a menu
                    await messenger.send_menu(platform_id, text, options, **kwargs)
                elif image_url:
                    # Send as media with caption
                    await messenger.send_media(
                        platform_id, image_url, caption=text, **kwargs
                    )
                else:
                    # Send as plain text
                    await messenger.send_text(platform_id, text, **kwargs)

                logger.info(
                    "Notification sent successfully",
                    extra={"user_id": user_id, "platform": platform_name},
                )
                return True
            except Exception as e:
                logger.error(
                    "Error sending notification",
                    exc_info=True,
                    extra={
                        "user_id": user_id,
                        "platform": platform_name,
                        "error_type": type(e).__name__,
                    },
                )
                return False

    @log_operation("send_ad")
    async def send_ad(
        self,
        user_id: int,
        ad_data: Dict[str, Any],
        image_url: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """
        Send an ad to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        from common.messaging.unified_platform_utils import resolve_user_id

        with log_context(logger, user_id=user_id, ad_id=ad_data.get("id")):
            logger.info(f'Sending ad {ad_data.get("id")} to user {user_id}...')
            # Get platform info using resolve_user_id
            _, platform_name, platform_id = resolve_user_id(user_id)

            if not platform_name or not platform_id:
                logger.warning(
                    "No messaging platform found for user", extra={"user_id": user_id}
                )
                return False

            messenger = self.get_messenger(platform_name)
            if not messenger:
                logger.error(
                    "No messenger implementation registered for platform",
                    extra={"platform": platform_name},
                )
                return False

            try:
                logger.debug(
                    "Sending ad",
                    extra={
                        "platform": platform_name,
                        "formatted_id": platform_id[:10],
                        "ad_id": ad_data.get("id"),
                        "has_image": bool(image_url),
                    },
                )

                # Send the ad using platform-specific formatting
                await messenger.send_ad(platform_id, ad_data, image_url, **kwargs)

                logger.info(
                    "Ad sent successfully",
                    extra={
                        "user_id": user_id,
                        "platform": platform_name,
                        "ad_id": ad_data.get("id"),
                    },
                )
                return True
            except Exception as e:
                logger.error(
                    "Error sending ad",
                    exc_info=True,
                    extra={
                        "user_id": user_id,
                        "platform": platform_name,
                        "ad_id": ad_data.get("id"),
                        "error_type": type(e).__name__,
                    },
                )
                return False

    @classmethod
    @log_operation("create_for_service")
    def create_for_service(cls, service_name: str) -> "MessagingService":
        """
        Create a messaging service for a specific service only.

        Args:
            service_name: Name of the service ('telegram', )

        Returns:
            Configured MessagingService instance with only the specified messenger
        """
        with log_context(logger, service_name=service_name):
            service = cls()
            try:
                pass

                # Don't import the bot here, let the telegram service do it
                logger.info("Telegram messenger type imported successfully")

            except ImportError as e:
                logger.error(
                    "Failed to import telegram messaging type",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize telegram messaging",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )

            return service


messaging_service = MessagingService()

# Add it to the exports
__all__ = ["MessagingService", "messaging_service"]
