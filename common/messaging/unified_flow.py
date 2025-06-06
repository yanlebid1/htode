# common/messaging/unified_flow.py

import inspect
from typing import Dict, Any, Optional, Union, Callable, List

from .unified_platform_utils import safe_send_message, safe_send_menu
from common.unified_state_management import state_manager
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the messaging logger
from . import logger

# Flow name mappings to recognize flow commands in different formats
FLOW_NAME_ALIASES = {
    # Property search flow
    "property_search": ["search", "пошук", "підписка", "subscription"],

    # Subscription flow (existing)
    "subscription": ["підписатися", "subscribe", "start_subscription"],

    # Phone verification flow
    "phone_verification": ["phone", "телефон", "верифікація", "verification"],

    # Support flow
    "support": ["допомога", "help", "підтримка", "техпідтримка", "support"]
}


class FlowContext:
    """
    Context object passed to flow handlers providing access to flow data
    and convenience methods for common operations.
    """

    def __init__(self,
                 user_id: Union[str, int],
                 platform: str,
                 flow_data: Dict[str, Any],
                 message: Optional[str] = None):
        """
        Initialize the flow context.

        Args:
            user_id: User identifier
            platform: Platform identifier (telegram, )
            flow_data: Flow-specific data dictionary
            message: Current message text (if available)
        """
        self.user_id = user_id
        self.platform = platform
        self.data = flow_data or {}
        self.message = message
        self._updates = {}

    @log_operation("send_message")
    async def send_message(self, text: str, **kwargs) -> Any:
        """Send a message to the user using the unified messaging utility."""
        with log_context(logger, user_id=self.user_id, platform=self.platform):
            return await safe_send_message(
                user_id=self.user_id,
                text=text,
                platform=self.platform,
                **kwargs
            )

    @log_operation("send_menu")
    async def send_menu(self, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """Send a menu to the user using the unified messaging utility."""
        with log_context(logger, user_id=self.user_id, platform=self.platform, options_count=len(options)):
            return await safe_send_menu(
                user_id=self.user_id,
                text=text,
                options=options,
                platform=self.platform,
                **kwargs
            )

    def update(self, **kwargs) -> None:
        """
        Update flow data with new values.
        These will be saved when the handler completes.
        """
        self._updates.update(kwargs)
        self.data.update(kwargs)

    def get_updates(self) -> Dict[str, Any]:
        """Get all updates made during this handler execution."""
        return self._updates

    def clear_updates(self) -> None:
        """Clear all pending updates."""
        self._updates = {}


class MessageFlow:
    """
    A platform-agnostic message flow builder.
    Makes it easy to create consistent conversation flows across platforms.
    """

    def __init__(self, name: str, initial_state: str = "start", description: str = ""):
        """
        Initialize a message flow.

        Args:
            name: Name of the flow
            initial_state: Initial state name
            description: Optional description of the flow
        """
        self.name = name
        self.description = description
        self.initial_state = initial_state
        self.states = {}
        self.transitions = {}
        self.global_handlers = {}
        self.error_handler = None

    def get_description(self) -> str:
        """Get the description of this flow."""
        return self.description or f"Flow: {self.name}"

    def add_state(self,
                  state_name: str,
                  handler: Optional[Callable] = None,
                  **kwargs) -> 'MessageFlow':
        """
        Add a state to the flow.

        Args:
            state_name: Name of the state
            handler: Optional handler function for this state
            **kwargs: Additional state metadata

        Returns:
            Self for method chaining
        """
        self.states[state_name] = {
            "handler": handler,
            **kwargs
        }
        return self

    def add_transition(self,
                       from_state: str,
                       to_state: str,
                       condition: Optional[Callable] = None,
                       **kwargs) -> 'MessageFlow':
        """
        Add a transition between states.

        Args:
            from_state: Source state name
            to_state: Target state name
            condition: Optional function that returns True if transition should occur
            **kwargs: Additional transition metadata

        Returns:
            Self for method chaining
        """
        if from_state not in self.transitions:
            self.transitions[from_state] = []

        self.transitions[from_state].append({
            "to_state": to_state,
            "condition": condition,
            **kwargs
        })
        return self

    def add_global_handler(self,
                           handler_name: str,
                           handler: Callable) -> 'MessageFlow':
        """
        Add a global handler that is available in all states.

        Args:
            handler_name: Name of the handler
            handler: Handler function

        Returns:
            Self for method chaining
        """
        self.global_handlers[handler_name] = handler
        return self

    def set_error_handler(self, handler: Callable) -> 'MessageFlow':
        """
        Set a global error handler for this flow.

        Args:
            handler: Function that handles errors

        Returns:
            Self for method chaining
        """
        self.error_handler = handler
        return self

    @log_operation("start_flow")
    async def start(self, user_id: Union[str, int], platform: str, initial_data: Dict[str, Any] = None) -> bool:
        """
        Start the flow for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            initial_data: Optional initial flow data

        Returns:
            True if started successfully, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform, flow_name=self.name):
            try:
                # Prepare initial flow data
                flow_data = initial_data or {}

                # Update user state
                await state_manager.update_state(user_id, platform, {
                    "state": self.initial_state,
                    "active_flow": self.name,
                    "flow_data": flow_data
                })

                # Execute initial state handler if available
                initial_state_data = self.states.get(self.initial_state)
                if initial_state_data and initial_state_data.get("handler"):
                    # Create flow context
                    context = FlowContext(user_id, platform, flow_data)

                    # Call handler
                    handler = initial_state_data["handler"]
                    await self._call_handler(handler, context)

                    # Save any updates to flow data
                    updates = context.get_updates()
                    if updates:
                        await state_manager.update_state(user_id, platform, {
                            "flow_data": flow_data
                        })

                logger.info("Flow started successfully", extra={
                    'flow_name': self.name,
                    'user_id': user_id,
                    'platform': platform
                })
                return True
            except Exception as e:
                logger.error("Error starting flow", exc_info=True, extra={
                    'flow_name': self.name,
                    'user_id': user_id,
                    'platform': platform,
                    'error_type': type(e).__name__
                })
                if self.error_handler:
                    context = FlowContext(user_id, platform, flow_data)
                    await self._call_handler(self.error_handler, context, exception=e)
                return False

    @log_operation("process_message")
    async def process_message(self, user_id: Union[str, int], platform: str, message: str) -> bool:
        """
        Process a message within the flow.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if the message was handled, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform, flow_name=self.name):
            try:
                # Get current state
                state_data = await state_manager.get_state(user_id, platform) or {}
                current_state = state_data.get("state", self.initial_state)
                flow_data = state_data.get("flow_data", {})

                logger.debug("Processing message in flow", extra={
                    'current_state': current_state,
                    'message_length': len(message)
                })

                # Create flow context
                context = FlowContext(user_id, platform, flow_data, message)

                # Check for global handlers first
                for handler_name, handler in self.global_handlers.items():
                    try:
                        result = await self._call_handler(handler, context)
                        if result:
                            # Apply any updates to flow data
                            updates = context.get_updates()
                            if updates:
                                flow_data.update(updates)
                                await state_manager.update_state(user_id, platform, {
                                    "flow_data": flow_data
                                })
                            return True
                    except Exception as e:
                        logger.error(f"Error in global handler", exc_info=True, extra={
                            'handler_name': handler_name,
                            'error_type': type(e).__name__
                        })
                        if self.error_handler:
                            await self._call_handler(self.error_handler, context, exception=e)

                # Check state-specific handler
                state_info = self.states.get(current_state)
                if state_info and state_info.get("handler"):
                    handler = state_info["handler"]
                    try:
                        # Call the state handler
                        await self._call_handler(handler, context)

                        # Apply any updates to flow data
                        updates = context.get_updates()
                        if updates:
                            flow_data.update(updates)
                            await state_manager.update_state(user_id, platform, {
                                "flow_data": flow_data
                            })

                        # Check for transitions
                        await self._check_transitions(context, current_state, message, flow_data)

                        return True
                    except Exception as e:
                        logger.error(f"Error in state handler", exc_info=True, extra={
                            'state': current_state,
                            'error_type': type(e).__name__
                        })
                        if self.error_handler:
                            await self._call_handler(self.error_handler, context, exception=e)
                        return True

                # No handler for this state
                logger.warning(f"No handler for state", extra={
                    'state': current_state,
                    'flow_name': self.name
                })
                return False
            except Exception as e:
                logger.error(f"Error processing message in flow", exc_info=True, extra={
                    'flow_name': self.name,
                    'error_type': type(e).__name__
                })
                if self.error_handler:
                    context = FlowContext(
                        user_id,
                        platform,
                        state_data.get("flow_data", {}),
                        message
                    )
                    await self._call_handler(self.error_handler, context, exception=e)
                return False

    @log_operation("transition_to")
    async def transition_to(self, user_id: Union[str, int], platform: str, target_state: str) -> bool:
        """
        Manually transition to a specific state.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            target_state: Target state name

        Returns:
            True if transition succeeded, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform, target_state=target_state):
            try:
                # Get current state data
                state_data = await state_manager.get_state(user_id, platform) or {}
                flow_data = state_data.get("flow_data", {})

                # Update state
                await state_manager.update_state(user_id, platform, {
                    "state": target_state
                })

                # Execute new state handler
                state_info = self.states.get(target_state)
                if state_info and state_info.get("handler"):
                    # Create flow context
                    context = FlowContext(user_id, platform, flow_data)

                    # Call handler
                    handler = state_info["handler"]
                    await self._call_handler(handler, context)

                    # Save any updates to flow data
                    updates = context.get_updates()
                    if updates:
                        flow_data.update(updates)
                        await state_manager.update_state(user_id, platform, {
                            "flow_data": flow_data
                        })

                logger.info("Successfully transitioned to new state", extra={
                    'target_state': target_state,
                    'flow_name': self.name
                })
                return True
            except Exception as e:
                logger.error(f"Error transitioning to state", exc_info=True, extra={
                    'target_state': target_state,
                    'flow_name': self.name,
                    'error_type': type(e).__name__
                })
                if self.error_handler:
                    context = FlowContext(user_id, platform, flow_data)
                    await self._call_handler(self.error_handler, context, exception=e)
                return False

    @log_operation("end_flow")
    async def end(self, user_id: Union[str, int], platform: str) -> bool:
        """
        End the flow for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            True if ended successfully, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform, flow_name=self.name):
            try:
                # Clear flow state
                await state_manager.update_state(user_id, platform, {
                    "state": "start",
                    "active_flow": None,
                    "flow_data": {}
                })
                logger.info("Flow ended successfully", extra={'flow_name': self.name})
                return True
            except Exception as e:
                logger.error(f"Error ending flow", exc_info=True, extra={
                    'flow_name': self.name,
                    'error_type': type(e).__name__
                })
                return False

    async def _check_transitions(self,
                                 context: FlowContext,
                                 current_state: str,
                                 message: str,
                                 flow_data: Dict[str, Any]) -> bool:
        """
        Check if any transitions should be triggered.

        Args:
            context: Flow context
            current_state: Current state name
            message: User's message
            flow_data: Flow data dictionary

        Returns:
            True if a transition was triggered, False otherwise
        """
        transitions = self.transitions.get(current_state, [])

        for transition in transitions:
            condition = transition.get("condition")

            # Check if condition is met
            try:
                if condition is None or await self._call_condition(condition, context, message, flow_data):
                    target_state = transition["to_state"]

                    # Update state
                    await state_manager.update_state(context.user_id, context.platform, {
                        "state": target_state
                    })

                    # Execute new state handler
                    target_state_info = self.states.get(target_state)
                    if target_state_info and target_state_info.get("handler"):
                        handler = target_state_info["handler"]
                        await self._call_handler(handler, context)

                        # Save any updates to flow data
                        updates = context.get_updates()
                        if updates:
                            flow_data.update(updates)
                            await state_manager.update_state(context.user_id, context.platform, {
                                "flow_data": flow_data
                            })

                    # Only apply the first matching transition
                    return True
            except Exception as e:
                logger.error(f"Error checking transition condition", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                if self.error_handler:
                    await self._call_handler(self.error_handler, context, exception=e)

        return False

    async def _call_handler(self,
                            handler: Callable,
                            context: FlowContext,
                            **kwargs) -> Any:
        """
        Call a handler function with appropriate arguments based on its signature.

        Args:
            handler: Handler function to call
            context: Flow context
            **kwargs: Additional arguments to pass

        Returns:
            Result from the handler
        """
        # Get handler signature
        sig = inspect.signature(handler)
        params = sig.parameters

        # Prepare arguments based on signature
        if len(params) == 1 and "context" in params:
            # Handler accepts only context
            return await handler(context)
        elif len(params) >= 3 and "user_id" in params and "platform" in params and "message" in params:
            # Legacy handler with user_id, platform, message, flow_data
            if "flow_data" in params:
                return await handler(context.user_id, context.platform, context.message, context.data)
            else:
                return await handler(context.user_id, context.platform, context.message)
        else:
            # Default to passing all individual components
            return await handler(
                context.user_id,
                context.platform,
                context.message,
                context.data,
                **kwargs
            )

    async def _call_condition(self,
                              condition: Callable,
                              context: FlowContext,
                              message: str,
                              flow_data: Dict[str, Any]) -> bool:
        """
        Call a condition function with appropriate arguments based on its signature.

        Args:
            condition: Condition function to call
            context: Flow context
            message: User's message
            flow_data: Flow data dictionary

        Returns:
            Boolean result from the condition
        """
        # Get condition signature
        sig = inspect.signature(condition)
        params = sig.parameters

        # Prepare arguments based on signature
        if len(params) == 1 and "context" in params:
            # Condition accepts only context
            result = await condition(context) if inspect.iscoroutinefunction(condition) else condition(context)
        elif len(params) == 2 and "message" in params and "data" in params:
            # Legacy condition function (message, data)
            result = await condition(message, flow_data) if inspect.iscoroutinefunction(condition) else condition(
                message, flow_data)
        elif len(params) == 1 and "message" in params:
            # Simple condition function (message)
            result = await condition(message) if inspect.iscoroutinefunction(condition) else condition(message)
        else:
            # Default to passing both message and data
            result = (await condition(message, flow_data, context)
                      if inspect.iscoroutinefunction(condition)
                      else condition(message, flow_data, context))

        return bool(result)


class FlowLibrary:
    """
    A library of reusable message flows.
    """

    def __init__(self):
        """Initialize the flow library."""
        self.flows = {}

    @log_operation("register_flow")
    def register_flow(self, flow: MessageFlow) -> 'FlowLibrary':
        """
        Register a flow in the library.

        Args:
            flow: MessageFlow instance

        Returns:
            Self for method chaining
        """
        with log_context(logger, flow_name=flow.name):
            self.flows[flow.name] = flow
            logger.info(f"Registered flow", extra={'flow_name': flow.name})
            return self

    def get_flow(self, name: str) -> Optional[MessageFlow]:
        """
        Get a flow by name.

        Args:
            name: Flow name

        Returns:
            MessageFlow instance or None
        """
        return self.flows.get(name)

    def get_all_flows(self) -> Dict[str, MessageFlow]:
        """
        Get all registered flows.

        Returns:
            Dictionary of flow names to flow instances
        """
        return dict(self.flows)

    @log_operation("start_flow")
    async def start_flow(self,
                         name: str,
                         user_id: Union[str, int],
                         platform: str,
                         initial_data: Dict[str, Any] = None) -> bool:
        """
        Start a flow for a user.

        Args:
            name: Flow name
            user_id: User's platform-specific ID
            platform: Platform name
            initial_data: Optional initial flow data

        Returns:
            True if flow was started, False otherwise
        """
        with log_context(logger, flow_name=name, user_id=user_id, platform=platform):
            flow = self.get_flow(name)
            if not flow:
                logger.warning(f"Flow not found", extra={'flow_name': name})
                return False

            return await flow.start(user_id, platform, initial_data)

    @log_operation("process_message")
    async def process_message(self,
                              user_id: Union[str, int],
                              platform: str,
                              message: str) -> bool:
        """
        Process a message using the active flow.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if message was processed, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform):
            # Get the current active flow for this user
            state_data = await state_manager.get_state(user_id, platform) or {}
            active_flow_name = state_data.get("active_flow")

            if not active_flow_name:
                # No active flow
                logger.debug("No active flow for user", extra={'user_id': user_id})
                return False

            # Get the flow
            flow = self.get_flow(active_flow_name)
            if not flow:
                logger.warning(f"Active flow not found", extra={'flow_name': active_flow_name})
                return False

            # Process the message with the active flow
            return await flow.process_message(user_id, platform, message)

    @log_operation("end_active_flow")
    async def end_active_flow(self, user_id: Union[str, int], platform: str) -> bool:
        """
        End the active flow for a user.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name

        Returns:
            True if flow was ended, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform):
            # Get the current active flow for this user
            state_data = await state_manager.get_state(user_id, platform) or {}
            active_flow_name = state_data.get("active_flow")

            if not active_flow_name:
                # No active flow
                logger.debug("No active flow to end", extra={'user_id': user_id})
                return False

            # Get the flow
            flow = self.get_flow(active_flow_name)
            if not flow:
                logger.warning(f"Active flow not found", extra={'flow_name': active_flow_name})
                return False

            # End the flow
            return await flow.end(user_id, platform)

    @log_operation("transition_active_flow")
    async def transition_active_flow(self,
                                     user_id: Union[str, int],
                                     platform: str,
                                     target_state: str) -> bool:
        """
        Transition the active flow to a new state.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            target_state: Target state name

        Returns:
            True if transition succeeded, False otherwise
        """
        with log_context(logger, user_id=user_id, platform=platform, target_state=target_state):
            # Get the current active flow for this user
            state_data = await state_manager.get_state(user_id, platform) or {}
            active_flow_name = state_data.get("active_flow")

            if not active_flow_name:
                # No active flow
                logger.debug("No active flow for transition", extra={'user_id': user_id})
                return False

            # Get the flow
            flow = self.get_flow(active_flow_name)
            if not flow:
                logger.warning(f"Active flow not found", extra={'flow_name': active_flow_name})
                return False

            # Transition to the new state
            return await flow.transition_to(user_id, platform, target_state)


# ===== Flow Integration Helper Functions =====

@log_operation("check_and_process_flow")
async def check_and_process_flow(user_id: Union[str, int],
                                 platform: str,
                                 message_text: str,
                                 extra_context: Optional[Dict[str, Any]] = None,
                                 on_success: Optional[Callable] = None,
                                 on_failure: Optional[Callable] = None) -> bool:
    """
    Check if there's an active flow for this user and process the message,
    or check if the message is a flow command.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram",)
        message_text: Message text from user
        extra_context: Optional extra context data to include
        on_success: Optional callback function to call if message was handled
        on_failure: Optional callback function to call if message wasn't handled

    Returns:
        True if the message was handled by a flow, False otherwise
    """
    with log_context(logger, user_id=user_id, platform=platform):
        # First check if there's an active flow to handle this message
        if await flow_library.process_message(user_id, platform, message_text):
            logger.info(f"Message handled by active flow", extra={'user_id': user_id, 'platform': platform})
            if on_success:
                await on_success()
            return True

        # Check if this is a command to start a flow
        flow_to_start = None

        # Convert message to lowercase for matching
        message_lower = message_text.lower().strip()

        # Check if message directly matches a flow name
        if message_lower in flow_library.get_all_flows():
            flow_to_start = message_lower
        else:
            # Check against aliases
            for flow_name, aliases in FLOW_NAME_ALIASES.items():
                if message_lower in aliases or any(alias in message_lower for alias in aliases):
                    flow_to_start = flow_name
                    break

        # If we found a flow to start, start it
        if flow_to_start:
            logger.info(f"Starting flow", extra={
                'flow_name': flow_to_start,
                'user_id': user_id,
                'platform': platform
            })

            # Initialize flow data with any extra context
            initial_data = extra_context or {}

            # Start the flow
            if await flow_library.start_flow(flow_to_start, user_id, platform, initial_data):
                if on_success:
                    await on_success()
                return True

        # If we get here, no flow handled the message
        if on_failure:
            await on_failure()
        return False


@log_operation("show_available_flows")
async def show_available_flows(user_id: Union[str, int], platform: str):
    """
    Show a menu of available flows the user can start.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram",)
    """
    with log_context(logger, user_id=user_id, platform=platform):
        # Get all registered flows
        all_flows = flow_library.get_all_flows()

        # Create menu options
        options = []

        # Add option for each flow with a human-readable name
        flow_display_names = {
            "property_search": "Пошук нерухомості",
            "subscription": "Керування підписками",
            "phone_verification": "Верифікація телефону",
            "support": "Технічна підтримка"
        }

        for flow_name in all_flows:
            display_name = flow_display_names.get(flow_name, flow_name.capitalize())
            options.append({
                "text": display_name,
                "value": f"flow:{flow_name}:start"
            })

        logger.debug("Showing available flows menu", extra={
            'user_id': user_id,
            'platform': platform,
            'flows_count': len(options)
        })

        # Send the menu
        await safe_send_menu(
            user_id=user_id,
            text="Оберіть дію:",
            options=options,
            platform=platform
        )


@log_operation("process_flow_action")
async def process_flow_action(user_id: Union[str, int],
                              platform: str,
                              action_text: str) -> bool:
    """
    Process a flow action from a menu selection or explicit command.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram",)
        action_text: Action text (format: "flow:flow_name:action")

    Returns:
        True if action was processed, False otherwise
    """
    with log_context(logger, user_id=user_id, platform=platform, action=action_text):
        # Check if this is a flow action
        if not action_text.startswith("flow:"):
            return False

        # Parse the action
        parts = action_text.split(":", 2)
        if len(parts) != 3:
            logger.warning("Invalid flow action format", extra={'action': action_text})
            return False

        _, flow_name, action = parts

        logger.debug("Processing flow action", extra={
            'flow_name': flow_name,
            'action': action
        })

        # Process the action
        if action == "start":
            # Start a flow
            return await flow_library.start_flow(flow_name, user_id, platform)
        elif action.startswith("state_"):
            # Transition to a state in the active flow
            state_name = action[6:]  # Remove "state_" prefix
            return await flow_library.transition_active_flow(user_id, platform, state_name)
        elif action == "end":
            # End the active flow
            return await flow_library.end_active_flow(user_id, platform)

        # Unknown action
        logger.warning("Unknown flow action", extra={'action': action})
        return False


@log_operation("create_flow_context")
async def create_flow_context(user_id: Union[str, int],
                              platform: str,
                              message: Optional[str] = None,
                              initial_data: Optional[Dict[str, Any]] = None) -> FlowContext:
    """
    Create a FlowContext object for custom flow handling.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Platform identifier ("telegram",)
        message: Optional message text
        initial_data: Optional initial flow data

    Returns:
        FlowContext object
    """
    with log_context(logger, user_id=user_id, platform=platform):
        # Get current state data if available
        state_data = await state_manager.get_state(user_id, platform) or {}
        flow_data = state_data.get("flow_data", {})

        # Merge with initial data if provided
        if initial_data:
            flow_data.update(initial_data)

        # Create and return context
        return FlowContext(user_id, platform, flow_data, message)


# Create a global instance
flow_library = FlowLibrary()


# ===== Utility Functions for Flow Creation =====

def create_simple_flow(name: str,
                       states: Dict[str, Callable],
                       transitions: List[Dict[str, Any]] = None,
                       initial_state: str = "start") -> MessageFlow:
    """
    Create a simple flow with states and transitions.

    Args:
        name: Flow name
        states: Dictionary of state names to handler functions
        transitions: List of transition dictionaries
                    (from_state, to_state, condition)
        initial_state: Initial state name

    Returns:
        New MessageFlow instance
    """
    flow = MessageFlow(name, initial_state)

    # Add states
    for state_name, handler in states.items():
        flow.add_state(state_name, handler)

    # Add transitions
    if transitions:
        for transition in transitions:
            flow.add_transition(
                transition["from_state"],
                transition["to_state"],
                transition.get("condition")
            )

    return flow


def create_linear_flow(name: str,
                       steps: List[Dict[str, Any]],
                       initial_state: str = "start") -> MessageFlow:
    """
    Create a linear flow with a sequence of steps.

    Args:
        name: Flow name
        steps: List of step dictionaries with handlers and optional conditions
        initial_state: Initial state name

    Returns:
        New MessageFlow instance
    """
    flow = MessageFlow(name, initial_state)

    # Add steps as states
    prev_state = initial_state
    for i, step in enumerate(steps):
        state_name = step.get("name", f"step_{i + 1}")
        handler = step["handler"]

        # Add state
        flow.add_state(state_name, handler)

        # Add transition from previous state
        if i > 0 or prev_state != state_name:
            flow.add_transition(
                prev_state,
                state_name,
                step.get("condition")
            )

        prev_state = state_name

    return flow


def create_menu_flow(name: str,
                     menu_text: str,
                     options: Dict[str, Dict[str, Any]],
                     initial_state: str = "menu") -> MessageFlow:
    """
    Create a menu-based flow with options.

    Args:
        name: Flow name
        menu_text: Text to display for the menu
        options: Dictionary of option text to handler and state info
        initial_state: Initial state name

    Returns:
        New MessageFlow instance
    """
    flow = MessageFlow(name, initial_state)

    # Create menu handler
    async def show_menu(context: FlowContext):
        menu_options = [
            {"text": option_text, "value": f"option_{i}"}
            for i, option_text in enumerate(options.keys())
        ]
        await context.send_menu(menu_text, menu_options)

    # Add menu state
    flow.add_state(initial_state, show_menu)

    # Add option states and transitions
    for i, (option_text, option_data) in enumerate(options.items()):
        state_name = option_data.get("state_name", f"option_{i}")
        handler = option_data["handler"]

        # Add state
        flow.add_state(state_name, handler)

        # Create condition function
        option_value = f"option_{i}"
        condition = lambda msg, option=option_value, text=option_text: msg == option or msg == text

        # Add transition
        flow.add_transition(initial_state, state_name, condition)

        # Add return transition if specified
        if option_data.get("return_to_menu", True):
            flow.add_transition(state_name, initial_state, None)

    return flow