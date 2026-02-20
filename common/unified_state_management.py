# common/unified_state_management.py

import logging
import json
import asyncio
import redis
from typing import Dict, Any, Optional, Union, Callable, Awaitable

from common.config import REDIS_URL
from common.utils.retry_utils import retry_with_exponential_backoff, NETWORK_EXCEPTIONS

logger = logging.getLogger(__name__)


class StateManager:
    """
    Unified state management for all messaging platforms.
    Provides a consistent interface for state management regardless of platform.
    Supports both synchronous and asynchronous operations.
    """

    # Lua script for atomic read-modify-write state updates.
    # Avoids the race condition where two concurrent updates could lose writes.
    UPDATE_SCRIPT = """
    local current = redis.call('GET', KEYS[1])
    local state = current and cjson.decode(current) or {}
    local updates = cjson.decode(ARGV[1])
    for k, v in pairs(updates) do state[k] = v end
    local encoded = cjson.encode(state)
    if ARGV[2] ~= '0' then
        redis.call('SETEX', KEYS[1], ARGV[2], encoded)
    else
        redis.call('SET', KEYS[1], encoded)
    end
    return encoded
    """

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        prefix: str = "state",
        default_ttl: int = 86400,
    ):
        """
        Initialize the state manager.

        Args:
            redis_url: Redis connection URL (deprecated, uses cluster manager)
            prefix: Prefix for Redis keys
            default_ttl: Default time-to-live for state data in seconds (default: 24 hours)
        """
        # Use Redis cluster for state management
        try:
            from common.utils.redis_cluster_manager import get_state_redis
            self.redis = get_state_redis()
            logger.info(f"Initialized StateManager with Redis cluster, prefix '{prefix}'")
        except ImportError:
            # Fallback to legacy Redis connection
            self.redis = redis.from_url(redis_url)
            logger.warning(f"Redis cluster manager not available, using legacy connection with prefix '{prefix}'")
        
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.platform_handlers = {}

    def register_platform_handler(self, platform: str, handler: Any) -> None:
        """
        Register a platform-specific handler.

        Args:
            platform: Platform name (telegram,)
            handler: Platform-specific state handler
        """
        self.platform_handlers[platform] = handler
        logger.info(f"Registered platform handler for {platform}")

    def _get_key(self, user_id: Union[str, int], platform: str = None) -> str:
        """
        Generate a Redis key for a user's state.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            Formatted Redis key
        """
        if platform:
            return f"{self.prefix}:{platform}:{user_id}"
        else:
            return f"{self.prefix}:{user_id}"

    @retry_with_exponential_backoff(
        max_retries=3, initial_delay=0.5, retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def get_state(
        self, user_id: Union[str, int], platform: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the state for a user.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            User state dictionary or None if not found
        """
        # Try platform-specific handler first if platform is provided
        if platform and platform in self.platform_handlers:
            try:
                handler = self.platform_handlers[platform]
                return await handler.get_state(user_id)
            except Exception as e:
                logger.warning(
                    f"Error getting state with platform handler {platform}: {e}"
                )
                # Fall back to direct implementation

        # Direct implementation
        key = self._get_key(user_id, platform)

        try:
            # Use asyncio to run the Redis get in a thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.redis.get(key))

            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in Redis for key {key}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Error getting state for {key}: {e}")
            raise

    @retry_with_exponential_backoff(
        max_retries=3, initial_delay=0.5, retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def set_state(
        self,
        user_id: Union[str, int],
        data: Dict[str, Any],
        platform: str = None,
        ttl: int = None,
    ) -> bool:
        """
        Set the state for a user.

        Args:
            user_id: User's platform-specific ID or database ID
            data: State data to store
            platform: Optional platform identifier
            ttl: Optional time-to-live in seconds (defaults to self.default_ttl)

        Returns:
            True if successful, False otherwise
        """
        # Try platform-specific handler first if platform is provided
        if platform and platform in self.platform_handlers:
            try:
                handler = self.platform_handlers[platform]
                return await handler.set_state(user_id, data)
            except Exception as e:
                logger.warning(
                    f"Error setting state with platform handler {platform}: {e}"
                )
                # Fall back to direct implementation

        # Direct implementation
        key = self._get_key(user_id, platform)
        expire_time = ttl if ttl is not None else self.default_ttl

        try:
            serialized = json.dumps(data)

            # Use asyncio to run the Redis set in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self.redis.setex(key, expire_time, serialized)
            )
            return True
        except Exception as e:
            logger.error(f"Error setting state for {key}: {e}")
            raise

    async def update_state(
        self,
        user_id: Union[str, int],
        updates: Dict[str, Any],
        platform: str = None,
        ttl: int = None,
    ) -> bool:
        """
        Atomically update the state for a user (partial update).

        Uses a Lua script to perform read-modify-write in a single Redis
        operation, preventing lost writes from concurrent updates.

        Args:
            user_id: User's platform-specific ID or database ID
            updates: Dictionary of state updates
            platform: Optional platform identifier
            ttl: Optional time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        # Try platform-specific handler first if platform is provided
        if platform and platform in self.platform_handlers:
            try:
                handler = self.platform_handlers[platform]
                return await handler.update_state(user_id, updates)
            except Exception as e:
                logger.warning(
                    f"Error updating state with platform handler {platform}: {e}"
                )
                # Fall back to direct implementation

        # Atomic update via Lua script
        key = self._get_key(user_id, platform)
        expire_time = ttl if ttl is not None else self.default_ttl

        try:
            updates_json = json.dumps(updates)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.redis.eval(
                    self.UPDATE_SCRIPT, 1, key, updates_json, str(expire_time)
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Error updating state for {key}: {e}")
            raise

    @retry_with_exponential_backoff(
        max_retries=3, initial_delay=0.5, retryable_exceptions=NETWORK_EXCEPTIONS
    )
    async def clear_state(self, user_id: Union[str, int], platform: str = None) -> bool:
        """
        Clear the state for a user.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            True if successful, False otherwise
        """
        # Try platform-specific handler first if platform is provided
        if platform and platform in self.platform_handlers:
            try:
                handler = self.platform_handlers[platform]
                return await handler.clear_state(user_id)
            except Exception as e:
                logger.warning(
                    f"Error clearing state with platform handler {platform}: {e}"
                )
                # Fall back to direct implementation

        # Direct implementation
        key = self._get_key(user_id, platform)

        try:
            # Use asyncio to run the Redis delete in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.redis.delete(key))
            return True
        except Exception as e:
            logger.error(f"Error clearing state for {key}: {e}")
            raise

    async def get_current_state_name(
        self, user_id: Union[str, int], platform: str = None
    ) -> Optional[str]:
        """
        Get the current state name for a user.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            Current state name or None
        """
        state_data = await self.get_state(user_id, platform)
        return state_data.get("state") if state_data else None

    # --- Synchronous API equivalents ---

    def get_state_sync(
        self, user_id: Union[str, int], platform: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous version of get_state.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            User state dictionary or None if not found
        """
        key = self._get_key(user_id, platform)

        try:
            data = self.redis.get(key)
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in Redis for key {key}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Error getting state for {key}: {e}")
            return None

    def set_state_sync(
        self,
        user_id: Union[str, int],
        data: Dict[str, Any],
        platform: str = None,
        ttl: int = None,
    ) -> bool:
        """
        Synchronous version of set_state.

        Args:
            user_id: User's platform-specific ID or database ID
            data: State data to store
            platform: Optional platform identifier
            ttl: Optional time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id, platform)
        expire_time = ttl if ttl is not None else self.default_ttl

        try:
            serialized = json.dumps(data)
            self.redis.setex(key, expire_time, serialized)
            return True
        except Exception as e:
            logger.error(f"Error setting state for {key}: {e}")
            return False

    def update_state_sync(
        self,
        user_id: Union[str, int],
        updates: Dict[str, Any],
        platform: str = None,
        ttl: int = None,
    ) -> bool:
        """
        Synchronous version of update_state.

        Uses a Lua script to perform atomic read-modify-write in a single
        Redis operation, preventing lost writes from concurrent updates.

        Args:
            user_id: User's platform-specific ID or database ID
            updates: Dictionary of state updates
            platform: Optional platform identifier
            ttl: Optional time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id, platform)
        expire_time = ttl if ttl is not None else self.default_ttl

        try:
            updates_json = json.dumps(updates)
            self.redis.eval(
                self.UPDATE_SCRIPT, 1, key, updates_json, str(expire_time)
            )
            return True
        except Exception as e:
            logger.error(f"Error updating state for {key}: {e}")
            return False

    def clear_state_sync(self, user_id: Union[str, int], platform: str = None) -> bool:
        """
        Synchronous version of clear_state.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(user_id, platform)

        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error clearing state for {key}: {e}")
            return False

    def get_current_state_name_sync(
        self, user_id: Union[str, int], platform: str = None
    ) -> Optional[str]:
        """
        Synchronous version of get_current_state_name.

        Args:
            user_id: User's platform-specific ID or database ID
            platform: Optional platform identifier

        Returns:
            Current state name or None
        """
        state_data = self.get_state_sync(user_id, platform)
        return state_data.get("state") if state_data else None


class StateMachine:
    """
    Simple state machine for message handling flows across platforms.
    """

    def __init__(self, initial_state: str = "start"):
        """
        Initialize the state machine.

        Args:
            initial_state: Initial state name
        """
        self.handlers = {}
        self.initial_state = initial_state

    def add_state(
        self,
        state: str,
        handler: Callable[[Union[str, int], str, Dict[str, Any]], Awaitable[bool]],
    ):
        """
        Add a state handler.

        Args:
            state: State name
            handler: Async function that processes this state
        """
        self.handlers[state] = handler

    async def process(
        self, user_id: Union[str, int], platform: str, message: str
    ) -> bool:
        """
        Process a message based on the current state.

        Args:
            user_id: User's platform-specific ID
            platform: Platform name
            message: User's message

        Returns:
            True if processed successfully, False otherwise
        """
        # Get current state
        current_state_name = await state_manager.get_current_state_name(
            user_id, platform
        )
        current_state_name = current_state_name or self.initial_state

        # Get state data
        state_data = await state_manager.get_state(user_id, platform) or {}

        # Find handler for current state
        handler = self.handlers.get(current_state_name)
        if not handler:
            logger.warning(f"No handler found for state {current_state_name}")
            return False

        # Execute the handler
        try:
            return await handler(user_id, platform, message, state_data)
        except Exception as e:
            logger.error(f"Error processing state {current_state_name}: {e}")
            return False


# Create a global instance
state_manager = StateManager()
