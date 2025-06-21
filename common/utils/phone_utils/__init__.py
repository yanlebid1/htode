"""
Phone number extraction utilities.
"""

from .parsers.phone_parser import extract_phone_numbers_from_resource
from .phone_models import ExtractionResult
from .proxy_manager import get_random_proxy, refresh_proxies, get_proxy_count

__all__ = [
    "extract_phone_numbers_from_resource",
    "ExtractionResult",
    "get_random_proxy",
    "refresh_proxies",
    "get_proxy_count",
]
