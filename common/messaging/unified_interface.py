# common/messaging/unified_interface.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
from common.utils.logging_config import log_operation, log_context

# Import the messaging logger
from . import logger


class MessagingInterface(ABC):
    """
    Unified messaging interface for all platform-specific implementations.
    Provides a consistent API for sending messages across different platforms (Telegram, etc.).
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Get the platform identifier (telegram, ).

        Returns:
            String identifier for the platform
        """
        pass

    @abstractmethod
    async def format_user_id(self, user_id: str) -> str:
        """
        Format a user ID for the specific platform.
        Ensures the user ID is in the correct format for the platform.

        Args:
            user_id: Raw user identifier

        Returns:
            Properly formatted user ID for the platform
        """
        pass

    @abstractmethod
    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[Any] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a text message to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Message text to send
            keyboard: Optional keyboard/buttons
            **kwargs: Additional platform-specific options (parse_mode, etc.)

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            keyboard: Optional[Any] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a media message to a user.

        Args:
            user_id: Platform-specific user identifier
            media_url: URL of the media to send
            caption: Optional caption text
            keyboard: Optional keyboard/buttons
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[Any, None]:
        """
        Send an interactive menu to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Menu title or description text
            options: List of options with 'text' and 'value' keys
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a real estate ad with platform-specific formatting.

        Args:
            user_id: Platform-specific user identifier
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @classmethod
    @abstractmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Any:
        """
        Create a platform-specific keyboard from standardized options.

        Args:
            options: List of options with 'text' and 'value' keys
            **kwargs: Additional platform-specific parameters

        Returns:
            Platform-specific keyboard object
        """
        pass

    # Extended methods that may be implemented by specific platforms

    async def send_document(
            self,
            user_id: str,
            document_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a document to a user.
        Default implementation falls back to send_media, but platforms can override.

        Args:
            user_id: Platform-specific user identifier
            document_url: URL of the document to send
            caption: Optional caption text
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        with log_context(logger, user_id=user_id, platform=self.platform_name):
            return await self.send_media(user_id, document_url, caption, **kwargs)

    async def send_location(
            self,
            user_id: str,
            latitude: float,
            longitude: float,
            title: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a location to a user.
        Default implementation sends a text message with coordinates, but platforms can override.

        Args:
            user_id: Platform-specific user identifier
            latitude: Location latitude
            longitude: Location longitude
            title: Optional location title
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        with log_context(logger, user_id=user_id, platform=self.platform_name):
            location_text = f"📍 Location: {latitude}, {longitude}"
            if title:
                location_text = f"{title}\n{location_text}"
            return await self.send_text(user_id, location_text, **kwargs)

    async def get_user_info(
            self,
            user_id: str,
            **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a user.
        Default implementation returns None, but platforms can override.

        Args:
            user_id: Platform-specific user identifier
            **kwargs: Additional platform-specific options

        Returns:
            Dictionary with user information or None
        """
        with log_context(logger, user_id=user_id, platform=self.platform_name):
            return None


class MessengerFactory:
    """
    Factory class for creating messenger instances for different platforms.
    """

    _messengers = {}

    @classmethod
    @log_operation("register_messenger")
    def register_messenger(cls, platform: str, messenger_class) -> None:
        """
        Register a messenger implementation for a platform.

        Args:
            platform: Platform name (telegram,)
            messenger_class: MessagingInterface implementation class
        """
        with log_context(logger, platform=platform):
            cls._messengers[platform] = messenger_class
            logger.info("Registered messenger", extra={'platform': platform})

    @classmethod
    @log_operation("get_messenger")
    def get_messenger(cls, platform: str) -> Optional[MessagingInterface]:
        """
        Get a messenger instance for a platform.

        Args:
            platform: Platform name (telegram,)

        Returns:
            MessagingInterface instance or None if not found
        """
        with log_context(logger, platform=platform):
            messenger_class = cls._messengers.get(platform)
            if not messenger_class:
                logger.warning("Messenger class not found", extra={'platform': platform})
                return None

            try:
                if platform == "telegram":
                    from services.telegram_service.app.bot import bot
                    return messenger_class(bot)
                else:
                    logger.error("Unknown platform", extra={'platform': platform})
                    return None
            except ImportError as e:
                logger.error("Error importing dependencies", exc_info=True, extra={
                    'platform': platform,
                    'error_type': type(e).__name__
                })
                return None
            except Exception as e:
                logger.error("Error creating messenger", exc_info=True, extra={
                    'platform': platform,
                    'error_type': type(e).__name__
                })
                return None