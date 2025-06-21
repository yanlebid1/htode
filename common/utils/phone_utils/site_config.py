"""
Site configuration for phone extraction.
Specifies which service to use for each website.
"""

from enum import Enum
from typing import Dict, List, Optional


class ExtractionService(Enum):
    """Available extraction services"""

    WEBCRAWLER = "webcrawler"  # Lightweight HTTP requests
    CAMOUFOX = "camoufox"  # Browser automation


class RequestMethod(Enum):
    """Request methods for WebCrawler service"""

    AIOHTTP = "aiohttp"
    CURL_CFFI = "curl_cffi"
    HTTPX = "httpx"


# Site-specific configuration
SITE_CONFIG: Dict[str, Dict] = {
    # Sites that require browser automation
    "olx.ua": {
        "service": ExtractionService.CAMOUFOX,
        "description": "OLX requires browser to reveal phone numbers",
    },
    "dom.ria": {
        "service": ExtractionService.CAMOUFOX,
        "description": "DOM.RIA requires browser to click phone button",
    },
    "dom.ria.com": {
        "service": ExtractionService.CAMOUFOX,
        "description": "DOM.RIA (com domain) requires browser",
    },
    # Sites that work with lightweight requests
    "lun.ua": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI],
        "description": "LUN.ua works with simple HTTP requests",
    },
    "rieltor.ua": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.AIOHTTP],
        "description": "Rieltor.ua works with simple HTTP requests",
    },
    "real-estate.lviv.ua": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.CURL_CFFI, RequestMethod.HTTPX],
        "description": "Lviv real estate may need browser impersonation",
    },
    "faktor24.com": {
        "service": ExtractionService.WEBCRAWLER,
        "methods": [RequestMethod.AIOHTTP],
        "description": "Faktor24 works with simple HTTP requests",
    },
}

# Default configuration for unknown sites
DEFAULT_CONFIG = {
    "service": ExtractionService.WEBCRAWLER,
    "methods": [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI, RequestMethod.HTTPX],
    "description": "Unknown site - trying lightweight methods first",
}


def get_service_for_url(url: str) -> ExtractionService:
    """Get the appropriate service for a given URL."""
    for domain, config in SITE_CONFIG.items():
        if domain in url:
            return config["service"]
    return DEFAULT_CONFIG["service"]


def get_webcrawler_methods_for_url(url: str) -> Optional[List[RequestMethod]]:
    """Get preferred WebCrawler methods for a URL (if applicable)."""
    for domain, config in SITE_CONFIG.items():
        if domain in url and config["service"] == ExtractionService.WEBCRAWLER:
            return config.get("methods")

    if get_service_for_url(url) == ExtractionService.WEBCRAWLER:
        return DEFAULT_CONFIG.get("methods")

    return None


def should_use_camoufox(url: str) -> bool:
    """Check if URL requires Camoufox browser automation."""
    return get_service_for_url(url) == ExtractionService.CAMOUFOX
