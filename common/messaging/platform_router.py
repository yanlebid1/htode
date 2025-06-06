# common/messaging/platform_router.py

import importlib
import inspect
from typing import Dict, Any, Optional, Union, Callable, Type

from common.messaging.unified_interface import MessagingInterface
from common.messaging.unified_platform_utils import resolve_user_id
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger


class PlatformRouter:
    """
    A router that dynamically loads platform-specific handlers and routes messages to them.
    """

    def __init__(self):
        """Initialize the platform router."""
        self.messengers = {}
        self.handlers = {}
        self.flows = {}

    @log_operation("register_messenger")
    def register_messenger(self, platform: str, messenger_class: Type[MessagingInterface]) -> None:
        """
        Register a messenger implementation for a platform.

        Args:
            platform: Platform name (telegram,)
            messenger_class: MessagingInterface implementation class
        """
        with log_context(logger, platform=platform):
            try:
                # Platform-specific configuration
                platform_configs = {
                    "telegram": {"module": "services.telegram_service.app.bot", "attr": "bot"},
                }

                # Check if platform is supported
                if platform not in platform_configs:
                    logger.error("Unsupported platform", extra={'platform': platform})
                    return

                config = platform_configs[platform]
                messenger = None

                # Import the bot/client instance
                try:
                    module = importlib.import_module(config["module"])
                    client_instance = getattr(module, config["attr"], None)

                    if client_instance:
                        messenger = messenger_class(client_instance)
                    else:
                        logger.error(f"Instance is None for platform", extra={
                            'platform': platform,
                            'attr': config["attr"]
                        })
                except ImportError as e:
                    logger.error(f"Failed to import for platform", exc_info=True, extra={
                        'platform': platform,
                        'module': config["module"],
                        'error_type': type(e).__name__
                    })

                # Register the messenger if available
                if messenger:
                    self.messengers[platform] = messenger
                    logger.info(f"Registered messenger for platform", extra={'platform': platform})
                else:
                    logger.error(f"Failed to create messenger instance for platform", extra={'platform': platform})

            except Exception as e:
                logger.error(f"Failed to register messenger for platform", exc_info=True, extra={
                    'platform': platform,
                    'error_type': type(e).__name__
                })

    @log_operation("register_handler")
    def register_handler(self, platform: str, handler_name: str, handler_func: Callable) -> None:
        """
        Register a handler function for a specific platform.

        Args:
            platform: Platform name
            handler_name: Name of the handler
            handler_func: Handler function
        """
        with log_context(logger, platform=platform, handler_name=handler_name):
            if platform not in self.handlers:
                self.handlers[platform] = {}

            self.handlers[platform][handler_name] = handler_func
            logger.info(f"Registered handler", extra={
                'handler_name': handler_name,
                'platform': platform
            })

    @log_operation("register_flow")
    def register_flow(self, flow_name: str, flow_handlers: Dict[str, Dict[str, Callable]]) -> None:
        """
        Register a message flow that can work across platforms.

        Args:
            flow_name: Name of the flow
            flow_handlers: Dictionary mapping states to handlers for each platform
                           Format: {state_name: {platform_name: handler_func}}
        """
        with log_context(logger, flow_name=flow_name):
            self.flows[flow_name] = flow_handlers
            logger.info(f"Registered flow", extra={'flow_name': flow_name})

    @log_operation("get_messenger")
    def get_messenger(self, platform: str) -> Optional[MessagingInterface]:
        """
        Get the messenger for a specific platform.

        Args:
            platform: Platform name

        Returns:
            MessagingInterface implementation or None
        """
        messenger = self.messengers.get(platform)
        logger.debug("Retrieved messenger", extra={
            'platform': platform,
            'found': bool(messenger)
        })
        return messenger

    @log_operation("get_handler")
    def get_handler(self, platform: str, handler_name: str) -> Optional[Callable]:
        """
        Get a handler function for a specific platform.

        Args:
            platform: Platform name
            handler_name: Name of the handler

        Returns:
            Handler function or None
        """
        handler = self.handlers.get(platform, {}).get(handler_name)
        logger.debug("Retrieved handler", extra={
            'platform': platform,
            'handler_name': handler_name,
            'found': bool(handler)
        })
        return handler

    @log_operation("get_flow_handler")
    def get_flow_handler(self, flow_name: str, state_name: str, platform: str) -> Optional[Callable]:
        """
        Get a handler function for a specific state in a flow.

        Args:
            flow_name: Name of the flow
            state_name: Name of the state
            platform: Platform name

        Returns:
            Handler function or None
        """
        with log_context(logger, flow_name=flow_name, state_name=state_name, platform=platform):
            flow = self.flows.get(flow_name)
            if not flow:
                logger.debug("Flow not found")
                return None

            state_handlers = flow.get(state_name)
            if not state_handlers:
                logger.debug("State handlers not found")
                return None

            handler = state_handlers.get(platform)
            logger.debug("Retrieved flow handler", extra={'found': bool(handler)})
            return handler

    @log_operation("route_message")
    async def route_message(self, user_id: Union[str, int], message: str,
                            platform: str = None, context: Dict[str, Any] = None) -> Any:
        """
        Route a message to the appropriate handler.

        Args:
            user_id: User's platform-specific ID or database ID
            message: Message text
            platform: Optional platform override
            context: Optional context data

        Returns:
            Result from the handler
        """
        with log_context(logger, user_id=str(user_id)[:10], platform=platform, has_context=bool(context)):
            try:
                # Resolve user ID and platform
                db_user_id, platform_name, platform_id = resolve_user_id(user_id, platform)
                platform = platform_name or platform or "telegram"  # Default to telegram

                logger.debug("Resolved user ID", extra={
                    'db_user_id': db_user_id,
                    'platform_name': platform_name,
                    'platform_id': str(platform_id)[:10] if platform_id else None
                })

                # Get the user's current state
                from common.unified_state_management import state_manager
                state_data = await state_manager.get_state(user_id, platform) or {}
                current_state = state_data.get("state", "start")

                logger.debug("User state retrieved", extra={
                    'current_state': current_state,
                    'has_active_flow': 'active_flow' in state_data
                })

                # Check for global commands (like /start, /help, etc.)
                command_handler = self._get_command_handler(message, platform)
                if command_handler:
                    logger.info("Routing to command handler", extra={
                        'command': message.split()[0] if message else None
                    })
                    return await command_handler(platform_id or user_id, message, context or {})

                # Check for active flow
                active_flow = state_data.get("active_flow")
                if active_flow:
                    flow_handler = self.get_flow_handler(active_flow, current_state, platform)
                    if flow_handler:
                        logger.info("Routing to flow handler", extra={
                            'active_flow': active_flow,
                            'current_state': current_state
                        })
                        return await flow_handler(platform_id or user_id, message, state_data)

                # Check for state-specific handler
                state_handler_name = f"handle_state_{current_state}"
                state_handler = self.get_handler(platform, state_handler_name)
                if state_handler:
                    logger.info("Routing to state handler", extra={
                        'state_handler_name': state_handler_name
                    })
                    return await state_handler(platform_id or user_id, message, state_data)

                # Fall back to default handler
                default_handler = self.get_handler(platform, "handle_default")
                if default_handler:
                    logger.info("Routing to default handler")
                    return await default_handler(platform_id or user_id, message, state_data)

                logger.warning(f"No handler found for message", extra={
                    'platform': platform,
                    'state': current_state
                })
                return None
            except Exception as e:
                logger.error(f"Error routing message", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                return None

    @log_operation("get_command_handler")
    def _get_command_handler(self, message: str, platform: str) -> Optional[Callable]:
        """
        Check if a message is a command and get the appropriate handler.

        Args:
            message: Message text
            platform: Platform name

        Returns:
            Command handler function or None
        """
        if not message:
            return None

        with log_context(logger, platform=platform, message_preview=message[:20]):
            # Check for commands
            if message.startswith('/'):
                command = message[1:].split()[0].lower()
                handler_name = f"handle_command_{command}"

                handler = self.get_handler(platform, handler_name)
                logger.debug("Command handler check", extra={
                    'command': command,
                    'handler_name': handler_name,
                    'found': bool(handler)
                })
                return handler

            return None

    @classmethod
    @log_operation("create_and_configure")
    def create_and_configure(cls) -> 'PlatformRouter':
        """
        Create and configure a PlatformRouter with all available platforms and handlers.

        Returns:
            Configured PlatformRouter instance
        """
        logger.info("Creating and configuring platform router")
        router = cls()

        # Register messengers
        try:
            from common.messaging.telegram_messaging import TelegramMessaging
            router.register_messenger("telegram", TelegramMessaging)
        except ImportError:
            logger.warning("TelegramMessaging not found or could not be imported")

        # Auto-load handlers from platform-specific modules
        platforms = ["telegram"]
        handler_modules = [
            "services.{}_service.app.handlers.basic_handlers",
            "services.{}_service.app.handlers.advanced_handlers",
            "services.{}_service.app.handlers.subscription",
            "services.{}_service.app.handlers.support",
            "services.{}_service.app.handlers.favorites",
            "services.{}_service.app.handlers.payment",
            "services.{}_service.app.handlers.phone_verification"
        ]

        from common.utils.logging_config import LogAggregator
        aggregator = LogAggregator(logger, "create_and_configure")

        for platform in platforms:
            for module_template in handler_modules:
                module_name = module_template.format(platform)
                try:
                    module = importlib.import_module(module_name)

                    # Find handler functions (async functions that start with "handle_")
                    for name, obj in inspect.getmembers(module):
                        if (name.startswith("handle_") and inspect.iscoroutinefunction(obj)):
                            router.register_handler(platform, name, obj)
                            aggregator.add_item({'platform': platform, 'module': module_name, 'handler': name},
                                                success=True)
                except ImportError:
                    # Module doesn't exist for this platform, skip
                    aggregator.add_item({'platform': platform, 'module': module_name}, success=False)
                    pass
                except Exception as e:
                    logger.error(f"Error loading handlers", exc_info=True, extra={
                        'module_name': module_name,
                        'error_type': type(e).__name__
                    })
                    aggregator.add_error(str(e), {'platform': platform, 'module': module_name})

        aggregator.log_summary()
        return router


# Create a global instance
platform_router = PlatformRouter.create_and_configure()