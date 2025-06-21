# services/telegram_service/app/handlers/__init__.py
"""
This file ensures all handler modules are properly imported and registered with the dispatcher.
"""

# Import from . import syntax to ensure all handlers are properly registered
from . import menu_handlers
from . import basic_handlers
from . import advanced_handlers
from . import subscription
from . import support
from . import favorites

# Make all these modules available when importing from handlers
__all__ = [
    "menu_handlers",
    "basic_handlers",
    "advanced_handlers",
    "subscription",
    "support",
    "favorites",
]
