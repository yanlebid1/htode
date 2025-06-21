"""
Asynchronous HTTP client manager with multiple fallback methods (aiohttp, curl_cffi, Camoufox).
Manages browser impersonation and handles proxies for requests.
"""

import urllib.parse
import random
from contextlib import asynccontextmanager
from typing import Optional, Dict
import aiohttp
from curl_cffi.requests import AsyncSession
import httpx
from common.utils import logger

# Attempt to use fake_useragent for realistic random User-Agent strings
try:
    from fake_useragent import UserAgent  # type: ignore

    _UA_GEN = UserAgent()
except Exception:
    _UA_GEN = None

# Browser impersonation options for curl_cffi (to bypass anti-bot measures)
IMPERSONATE_OPTIONS = [
    "chrome110",
    "chrome107",
    "chrome104",
    "chrome99",
    "firefox109",
    "firefox102",
    "safari15_5",
    "safari15_3",
    "edge99",
]

# Fallback pool of common User-Agent strings for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Default request timeout (seconds) for network operations
REQUEST_TIMEOUT = 30


def _random_ua() -> str:
    """Return a random User-Agent string."""
    if _UA_GEN is not None:
        try:
            return _UA_GEN.random  # type: ignore[attr-defined]
        except Exception:
            pass
    return random.choice(USER_AGENTS)


class AsyncHTTPClient:
    """
    Manages async HTTP requests with fallback mechanisms for anti-bot protection.
    Order of fallback:
      1. aiohttp (primary - lightweight)
      2. curl_cffi (with browser impersonation options)
      3. httpx (supports HTTP/2 and advanced usage)
      4. camoufox (headless browser automation as last resort)
    """

    def __init__(self, proxy: Optional[str] = None):
        """
        Initialize the HTTP client.
        Args:
            proxy: Optional proxy URL (e.g., 'http://user:pass@IP:Port').
        """
        self.proxy = proxy
        self.proxy_dict = self._parse_proxy(proxy) if proxy else None

    def _parse_proxy(self, proxy_url: str) -> Dict[str, str]:
        """Parse a proxy URL into a dictionary format for libraries that require separate http/https proxies."""
        urllib.parse.urlparse(proxy_url)
        return {"http": proxy_url, "https": proxy_url}

    def _get_random_headers(self) -> Dict[str, str]:
        """Generate a set of headers with a random User-Agent to mimic a real browser."""
        headers = {
            "User-Agent": _random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,uk;q=0.8,ru;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",  # Do Not Track request header
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        return headers

    @asynccontextmanager
    async def _get_aiohttp_session(self):
        """
        Context manager to provide an aiohttp ClientSession, optionally with a proxy.
        """
        connector = None
        if self.proxy:
            try:
                # Use aiohttp_proxy if available to simplify proxy usage
                from aiohttp_proxy import ProxyConnector  # type: ignore

                connector = ProxyConnector.from_url(self.proxy)
            except ImportError:
                connector = None  # Fallback: aiohttp can use proxy via session directly
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            yield session

    @asynccontextmanager
    async def _get_curl_cffi_session(self, impersonate: str):
        """
        Context manager to provide a curl_cffi AsyncSession with a given browser impersonation profile.
        """
        session = AsyncSession(
            impersonate=impersonate,
            timeout=REQUEST_TIMEOUT,
            proxies=self.proxy_dict if self.proxy else None,
        )
        try:
            yield session
        finally:
            await session.aclose()

    async def _fetch_with_camoufox(self, url: str) -> Optional[str]:
        """
        Use Camoufox service to retrieve page content. This delegates to a separate service for better scalability.
        """
        try:
            from common.utils.camoufox_client import camoufox_client

            result = await camoufox_client.extract_async(
                url=url,
                extraction_type="content",
                proxy=self.proxy,
                timeout=REQUEST_TIMEOUT,
                wait_after_load=2000,
            )

            if result["status"] == "success":
                data = result.get("data", {})
                return data.get("content")
            else:
                logger.warning(
                    f"Camoufox service failed for {url}: {result.get('error')}"
                )
                return None

        except Exception as e:
            logger.warning(f"Camoufox service error for {url}: {e}")
            return None

    async def fetch_with_aiohttp(
        self, url: str, headers: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Fetch a URL using aiohttp (primary method). Returns the response text or None on failure.
        """
        try:
            async with self._get_aiohttp_session() as session:
                # Combine randomized headers with any provided headers
                combined_headers = {**self._get_random_headers(), **(headers or {})}
                # Add common anti-scraping headers
                if "api" in url:
                    combined_headers["X-Requested-With"] = "XMLHttpRequest"
                combined_headers["Referer"] = "https://www.google.com/"
                # Remove any None values
                combined_headers = {
                    k: v for k, v in combined_headers.items() if v is not None
                }
                async with session.get(
                    url, headers=combined_headers, ssl=False
                ) as response:
                    response.raise_for_status()
                    logger.info(f"Successfully fetched {url} with aiohttp")
                    return await response.text()
        except Exception as e:
            logger.warning(f"aiohttp failed for {url}: {e}")
            return None

    async def fetch_with_curl_cffi(
        self, url: str, headers: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Fetch a URL using curl_cffi with multiple browser impersonations to bypass anti-bot checks.
        """
        combined_headers = {**self._get_random_headers(), **(headers or {})}
        combined_headers = {k: v for k, v in combined_headers.items() if v is not None}
        for imp in IMPERSONATE_OPTIONS:
            try:
                logger.debug(f"Trying curl_cffi with impersonation: {imp}")
                async with self._get_curl_cffi_session(imp) as session:
                    response = await session.get(url, headers=combined_headers)
                    if response.status_code == 200:
                        logger.info(
                            f"Successfully fetched {url} with curl_cffi (profile={imp})"
                        )
                        return response.text
                    else:
                        logger.warning(
                            f"curl_cffi got status {response.status_code} for {url} (profile={imp})"
                        )
            except Exception as e:
                logger.debug(f"curl_cffi exception with {imp}: {e}")
                continue
        return None

    async def fetch_with_httpx(
        self, url: str, headers: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Fetch a URL using httpx (supports HTTP/2). Returns response text or None on failure.
        """
        try:
            combined_headers = {**self._get_random_headers(), **(headers or {})}
            combined_headers = {
                k: v for k, v in combined_headers.items() if v is not None
            }
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                proxy=self.proxy,
                headers=combined_headers,
                follow_redirects=True,
                http2=True,
                verify=False,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                logger.info(f"Successfully fetched {url} with httpx")
                return response.text
        except Exception as e:
            logger.warning(f"httpx failed for {url}: {e}")
            return None

    async def fetch(self, url: str, headers: Optional[Dict] = None) -> str:
        """
        Try to fetch the URL using each method in sequence until one succeeds.
        Raises:
            Exception: if all methods fail to retrieve the content.
        """
        methods = [
            ("aiohttp", self.fetch_with_aiohttp),
            ("curl_cffi", self.fetch_with_curl_cffi),
            ("httpx", self.fetch_with_httpx),
            ("camoufox", lambda u, h=None: self._fetch_with_camoufox(u)),
        ]
        for name, method in methods:
            logger.info(f"Trying {name} for {url}")
            try:
                content = await method(url, headers)
                if content:
                    return content
            except Exception as e:
                logger.warning(f"{name} fetch raised exception for {url}: {e}")
                continue
        # If loop completes with no return, all methods failed
        raise Exception(f"Failed to fetch {url} with all methods")
