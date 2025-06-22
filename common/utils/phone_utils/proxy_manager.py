"""
Proxy management module for fetching and rotating proxies from proxy-sale.com API.
Caches proxies locally since they don't update frequently (monthly).
"""

import os
import json
import random
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
import aiohttp
import asyncio
from common.utils import logger

# List to store proxies in fully authenticated URL form, e.g. "http://user:pass@IP:port"
PROXIES: List[str] = []
# Internal flag to indicate if proxies have been loaded
_proxies_loaded: bool = False
# Cache file path for storing fetched proxies
_CACHE_FILE = Path("proxy_cache.json")
# Cache validity period (30 days in seconds, since proxies update monthly)
_CACHE_VALIDITY_SECONDS = 30 * 24 * 60 * 60


class ProxyAPIError(Exception):
    """Custom exception for proxy API-related errors."""



async def _fetch_proxies_from_api() -> List[Dict[str, Any]]:
    """
    Fetch proxies from proxy-sale.com API using the API key from environment variables.

    Returns:
        List of proxy dictionaries from the API response.

    Raises:
        ProxyAPIError: If API key is missing or API request fails.
    """
    api_key = os.getenv("PROXY_SALE_API_KEY")
    if not api_key:
        raise ProxyAPIError("PROXY_SALE_API_KEY environment variable is not set")

    api_url = f"https://proxy-sale.com/personal/api/v1/{api_key}/proxy/list/ipv4"

    logger.info("Fetching proxies from proxy-sale.com API")

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    raise ProxyAPIError(
                        f"API request failed with status {response.status}"
                    )

                data = await response.json()

                if data.get("status") != "success":
                    errors = data.get("errors", [])
                    raise ProxyAPIError(f"API returned error: {errors}")

                items = data.get("data", {}).get("items", [])
                logger.info(f"Successfully fetched {len(items)} proxies from API")
                return items

    except aiohttp.ClientError as e:
        raise ProxyAPIError(f"Network error while fetching proxies: {e}")
    except json.JSONDecodeError as e:
        raise ProxyAPIError(f"Invalid JSON response from API: {e}")


def _save_proxies_to_cache(proxies: List[Dict[str, Any]]) -> None:
    """Save fetched proxies to local cache file with timestamp."""
    cache_data = {"timestamp": time.time(), "proxies": proxies}

    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
        logger.info(f"Saved {len(proxies)} proxies to cache file")
    except Exception as e:
        logger.warning(f"Failed to save proxies to cache: {e}")


def _load_proxies_from_cache() -> Optional[List[Dict[str, Any]]]:
    """
    Load proxies from cache file if it exists and is still valid.

    Returns:
        List of cached proxy dictionaries if valid, None otherwise.
    """
    if not _CACHE_FILE.exists():
        logger.info("No proxy cache file found")
        return None

    try:
        with open(_CACHE_FILE, "r") as f:
            cache_data = json.load(f)

        timestamp = cache_data.get("timestamp", 0)
        current_time = time.time()

        if current_time - timestamp > _CACHE_VALIDITY_SECONDS:
            logger.info("Proxy cache is expired (older than 30 days)")
            return None

        proxies = cache_data.get("proxies", [])
        logger.info(f"Loaded {len(proxies)} proxies from valid cache")
        return proxies

    except (json.JSONDecodeError, KeyError, Exception) as e:
        logger.warning(f"Failed to load proxy cache: {e}")
        return None


def _convert_api_proxies_to_urls(api_proxies: List[Dict[str, Any]]) -> List[str]:
    """
    Convert API proxy objects to authenticated proxy URLs.

    Args:
        api_proxies: List of proxy dictionaries from the API.

    Returns:
        List of proxy URLs in format "http://login:password@ip:port"
    """
    proxy_urls = []

    for proxy in api_proxies:
        # Only use active proxies - check status_type field which contains "ACTIVE"
        if proxy.get("status_type") != "ACTIVE":
            continue

        ip = proxy.get("ip")
        port_http = proxy.get("port_http")
        login = proxy.get("login")
        password = proxy.get("password")

        # Validate required fields
        if not all([ip, port_http, login, password]):
            logger.warning(f"Skipping proxy with missing data: {proxy}")
            continue

        proxy_url = f"http://{login}:{password}@{ip}:{port_http}"
        proxy_urls.append(proxy_url)

    logger.info(f"Converted {len(proxy_urls)} API proxies to URLs")
    return proxy_urls


async def _load_proxies_async() -> None:
    """
    Asynchronously load proxies from cache or API.
    First tries to load from cache, then falls back to API if cache is invalid/missing.
    """
    global PROXIES, _proxies_loaded

    if _proxies_loaded:
        return

    try:
        # Try to load from cache first
        cached_proxies = _load_proxies_from_cache()

        if cached_proxies:
            PROXIES = _convert_api_proxies_to_urls(cached_proxies)
            _proxies_loaded = True
            return

        # Cache is invalid/missing, fetch from API
        logger.info("Cache invalid or missing, fetching fresh proxies from API")
        api_proxies = await _fetch_proxies_from_api()

        # Save to cache for future use
        _save_proxies_to_cache(api_proxies)

        # Convert to URLs and store
        PROXIES = _convert_api_proxies_to_urls(api_proxies)
        _proxies_loaded = True

    except ProxyAPIError as e:
        logger.error(f"Failed to load proxies: {e}")
        PROXIES = []
        _proxies_loaded = True
    except Exception as e:
        logger.exception(f"Unexpected error loading proxies: {e}")
        PROXIES = []
        _proxies_loaded = True


def load_proxies() -> None:
    """
    Synchronous wrapper for loading proxies.
    Uses asyncio to run the async proxy loading logic.
    """
    try:
        # Try to get existing event loop
        loop = asyncio.get_running_loop()
        # If we're in an event loop, schedule the task
        future = asyncio.run_coroutine_threadsafe(_load_proxies_async(), loop)
        future.result(timeout=60)  # Wait up to 60 seconds
    except RuntimeError:
        # No event loop running, create a new one
        asyncio.run(_load_proxies_async())


def get_random_proxy() -> Optional[str]:
    """
    Retrieve a random proxy URL (fully authenticated) from the loaded list.
    Loads proxies from API/cache if not already loaded.

    Returns:
        A proxy URL string (e.g., "http://user:pass@IP:Port") or None if no proxies available.
    """
    global _proxies_loaded

    if not _proxies_loaded:
        load_proxies()

    if not PROXIES:
        return None

    return random.choice(PROXIES)


def proxies_available() -> bool:
    """
    Check if any proxies are available (loads proxy list if not loaded yet).
    """
    if not _proxies_loaded:
        load_proxies()

    return len(PROXIES) > 0


def refresh_proxies() -> None:
    """
    Force refresh proxies from API, bypassing cache.
    Useful for manual cache invalidation.
    """
    global _proxies_loaded

    logger.info("Force refreshing proxies from API")

    # Remove cache file to force API fetch
    if _CACHE_FILE.exists():
        try:
            _CACHE_FILE.unlink()
            logger.info("Removed proxy cache file")
        except Exception as e:
            logger.warning(f"Failed to remove cache file: {e}")

    # Reset state and reload
    _proxies_loaded = False
    load_proxies()


def get_proxy_count() -> int:
    """
    Get the number of available proxies.

    Returns:
        Number of loaded proxies.
    """
    if not _proxies_loaded:
        load_proxies()

    return len(PROXIES)


# Backward compatibility: keep old function signature
def load_proxies_from_file(file_path: Optional[str] = None) -> None:
    """
    DEPRECATED: Load proxies from API instead of file.
    The file_path parameter is ignored for backward compatibility.
    """
    if file_path is not None:
        logger.warning(
            "file_path parameter is deprecated and ignored. Proxies are now loaded from API."
        )

    load_proxies()


if __name__ == "__main__":
    """
    Test script for proxy API functionality.
    Set PROXY_SALE_API_KEY environment variable before running.
    """
    import sys

    print("Testing Proxy API Integration")
    print("=" * 40)

    # Check if API key is set
    api_key = os.getenv("PROXY_SALE_API_KEY")
    if not api_key:
        print("❌ PROXY_SALE_API_KEY environment variable is not set")
        print("Please set it with: export PROXY_SALE_API_KEY=your_api_key_here")
        sys.exit(1)

    print(f"✅ API key found: {api_key[:8]}...")

    try:
        print("\n🔄 Loading proxies...")
        load_proxies()

        proxy_count = get_proxy_count()
        print(f"✅ Successfully loaded {proxy_count} proxies")

        if proxy_count > 0:
            print("\n🎲 Testing random proxy selection:")
            for i in range(min(3, proxy_count)):
                proxy = get_random_proxy()
                if proxy:
                    # Mask credentials for display
                    display_proxy = proxy.replace(
                        proxy.split("@")[0].split("//")[1], "***:***"
                    )
                    print(f"  Proxy {i+1}: {display_proxy}")

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
