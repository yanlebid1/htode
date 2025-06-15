# services/telegram_service/app/state_integration.py

from aiogram.dispatcher import FSMContext

from common.unified_state_management import state_manager

# Import service logger and logging utilities
from . import logger
from common.utils.logging_config import log_operation, log_context


class UnifiedFSMContextAdapter:
    """
    Adapter class to make the unified state manager compatible with aiogram's FSMContext.
    This allows for a smooth transition to the unified state management system.
    """

    def __init__(self, user_id: str, platform: str = "telegram"):
        """
        Initialize the adapter.

        Args:
            user_id: User's platform-specific ID
            platform: Platform identifier (defaults to "telegram")
        """
        self.user_id = str(user_id)
        self.platform = platform
        self.logger = logger

    @log_operation("get_state_data")
    async def get_data(self) -> dict:
        """
        Get state data for the user, mimicking FSMContext.get_data().

        Returns:
            State data dictionary or empty dict if not found
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.debug("Getting state data", extra={
                "user_id": self.user_id,
                "platform": self.platform
            })
            data = await state_manager.get_state(self.platform, self.user_id) or {}
            self.logger.debug("State data retrieved", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "data_keys": list(data.keys()) if data else []
            })
            return data

    @log_operation("get_state_name")
    async def get_state(self) -> str:
        """
        Get current state name for the user, mimicking FSMContext.get_state().

        Returns:
            Current state name or None
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.debug("Getting state name", extra={
                "user_id": self.user_id,
                "platform": self.platform
            })
            state_name = await state_manager.get_current_state_name(self.platform, self.user_id)
            self.logger.debug("State name retrieved", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "state_name": state_name
            })
            return state_name

    @log_operation("set_state")
    async def set_state(self, state: str = None) -> None:
        """
        Set state for the user, mimicking FSMContext.set_state().

        Args:
            state: State name to set
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.info("Setting state", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "new_state": state
            })
            current_data = await self.get_data()
            current_data['state'] = state
            await state_manager.set_state(self.platform, self.user_id, current_data)
            self.logger.debug("State set successfully", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "new_state": state
            })

    @log_operation("update_state_data")
    async def update_data(self, **kwargs) -> None:
        """
        Update state data for the user, mimicking FSMContext.update_data().

        Args:
            **kwargs: Data to update
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.debug("Updating state data", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "update_keys": list(kwargs.keys())
            })
            await state_manager.update_state(self.platform, self.user_id, kwargs)
            self.logger.debug("State data updated", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "updated_keys": list(kwargs.keys())
            })

    @log_operation("set_state_data")
    async def set_data(self, data: dict) -> None:
        """
        Set state data for the user, mimicking FSMContext.set_data().

        Args:
            data: Data to set
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.debug("Setting state data", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "data_keys": list(data.keys())
            })
            await state_manager.set_state(self.platform, self.user_id, data)
            self.logger.debug("State data set", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "data_keys": list(data.keys())
            })

    @log_operation("reset_state")
    async def reset_state(self, with_data: bool = True) -> None:
        """
        Reset state for the user, mimicking FSMContext.reset_state().

        Args:
            with_data: Whether to clear data as well
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.info("Resetting state", extra={
                "user_id": self.user_id,
                "platform": self.platform,
                "with_data": with_data
            })
            if with_data:
                await state_manager.clear_state(self.platform, self.user_id)
                self.logger.debug("State fully cleared", extra={
                    "user_id": self.user_id,
                    "platform": self.platform
                })
            else:
                current_data = await self.get_data()
                current_data.pop('state', None)
                await state_manager.set_state(self.platform, self.user_id, current_data)
                self.logger.debug("State name cleared, data preserved", extra={
                    "user_id": self.user_id,
                    "platform": self.platform
                })

    @log_operation("finish_state")
    async def finish(self) -> None:
        """
        Finish the current state for the user, mimicking FSMContext.finish().
        """
        with log_context(self.logger, user_id=self.user_id, platform=self.platform):
            self.logger.info("Finishing state", extra={
                "user_id": self.user_id,
                "platform": self.platform
            })
            current_data = await self.get_data()
            current_data.pop('state', None)
            await state_manager.set_state(self.platform, self.user_id, current_data)
            self.logger.debug("State finished", extra={
                "user_id": self.user_id,
                "platform": self.platform
            })


# Factory function to create an adapter from a user_id
@log_operation("get_state_for_user")
def get_state_for_user(user_id: str) -> UnifiedFSMContextAdapter:
    """
    Get a state adapter for a Telegram user.

    Args:
        user_id: User's Telegram ID

    Returns:
        FSMContext-compatible adapter for the user
    """
    with log_context(logger, user_id=user_id):
        logger.debug("Creating state adapter", extra={
            "user_id": user_id,
            "platform": "telegram"
        })
        return UnifiedFSMContextAdapter(user_id)


# Function to migrate existing state from aiogram to unified system
@log_operation("migrate_existing_state")
async def migrate_existing_state(old_context: FSMContext, user_id: str) -> None:
    """
    Migrate existing state from aiogram's FSMContext to unified system.

    Args:
        old_context: Existing FSMContext
        user_id: User's Telegram ID
    """
    with log_context(logger, user_id=user_id):
        try:
            # Get existing state data
            state = await old_context.get_state()
            data = await old_context.get_data()

            logger.info("Migrating state", extra={
                "user_id": user_id,
                "has_state": bool(state),
                "data_keys": list(data.keys()) if data else []
            })

            # If there's existing data, migrate it
            if data:
                # Add state name to data if it exists
                if state:
                    data['state'] = state

                # Save to unified state manager
                await state_manager.set_state("telegram", str(user_id), data)
                logger.info("State migrated successfully", extra={
                    "user_id": user_id,
                    "state": state,
                    "data_keys": list(data.keys())
                })
            else:
                logger.info("No state data to migrate", extra={
                    "user_id": user_id
                })
        except Exception as e:
            logger.error("Error migrating state", exc_info=True, extra={
                "user_id": user_id,
                "error": str(e)
            })