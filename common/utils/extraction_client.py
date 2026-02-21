"""
Unified extraction client that routes requests to the appropriate service.
"""

import asyncio
import os
from typing import Optional, Dict, Any
import httpx
from common.utils import logger
from common.utils.logging_config import log_operation
from .phone_utils.site_config import (
    get_service_for_url,
    get_webcrawler_methods_for_url,
    ExtractionService,
)

# Service URLs
CAMOUFOX_SERVICE_URL = os.getenv("CAMOUFOX_SERVICE_URL", "http://camoufox_service:8100")
WEBCRAWLER_SERVICE_URL = os.getenv(
    "WEBCRAWLER_SERVICE_URL", "http://webcrawler_service:8200"
)


class ExtractionClient:
    """Client for extracting content from web pages using the appropriate service."""

    def __init__(self):
        self.camoufox_url = f"{CAMOUFOX_SERVICE_URL}/browse"
        self.webcrawler_url = f"{WEBCRAWLER_SERVICE_URL}/crawl"

    @log_operation("extract_content")
    async def extract_content_async(
        self,
        url: str,
        proxy: Optional[str] = None,
        timeout: int = 30,
        wait_after_load: int = 3000,
        execute_script: Optional[str] = None,
        wait_for_selector: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Extract content from a URL using the appropriate service.

        Args:
            url: URL to extract from
            proxy: Optional proxy URL
            timeout: Timeout in seconds
            wait_after_load: Time to wait after page load (for Camoufox)
            execute_script: JavaScript to execute (for Camoufox)
            wait_for_selector: CSS selector to wait for (for Camoufox)
            headers: HTTP headers (for WebCrawler)

        Returns:
            Dict with extraction results
        """
        # Determine which service to use
        service = get_service_for_url(url)

        if service == ExtractionService.CAMOUFOX:
            return await self._extract_with_camoufox(
                url, proxy, timeout, wait_after_load, execute_script, wait_for_selector
            )
        else:
            return await self._extract_with_webcrawler(url, proxy, timeout, headers)

    async def _extract_with_camoufox(
        self,
        url: str,
        proxy: Optional[str],
        timeout: int,
        wait_after_load: int,
        execute_script: Optional[str],
        wait_for_selector: Optional[str],
    ) -> Dict[str, Any]:
        """Extract using Camoufox browser service."""
        request_data = {
            "url": url,
            "proxy": proxy,
            "timeout": timeout,
            "wait_after_load": wait_after_load,
            "execute_script": execute_script,
            "wait_for_selector": wait_for_selector,
        }

        # Remove None values
        request_data = {k: v for k, v in request_data.items() if v is not None}

        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                logger.info("Using Camoufox service", extra={"url": url})
                response = await client.post(self.camoufox_url, json=request_data)
                response.raise_for_status()

                result = response.json()

                if result["status"] == "success":
                    logger.info(
                        "Camoufox extraction successful",
                        extra={
                            "url": url,
                            "final_url": result.get("final_url"),
                            "status_code": result.get("status_code"),
                        },
                    )
                    return {
                        "status": "success",
                        "content": result.get("content"),
                        "final_url": result.get("final_url"),
                        "status_code": result.get("status_code"),
                        "service_used": "camoufox",
                    }
                else:
                    logger.error(
                        "Camoufox extraction failed",
                        extra={"url": url, "error": result.get("error")},
                    )
                    return {
                        "status": "error",
                        "error": result.get("error"),
                        "service_used": "camoufox",
                    }

        except Exception as e:
            logger.error(
                "Camoufox service error",
                exc_info=True,
                extra={"url": url, "error": str(e)},
            )
            return {"status": "error", "error": str(e), "service_used": "camoufox"}

    async def _extract_with_webcrawler(
        self,
        url: str,
        proxy: Optional[str],
        timeout: int,
        headers: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Extract using WebCrawler service."""
        # Get preferred methods for this URL
        methods = get_webcrawler_methods_for_url(url)

        request_data = {
            "url": url,
            "proxy": proxy,
            "timeout": timeout,
            "headers": headers,
        }

        # If we have specific methods, try them in order
        if methods:
            request_data["method"] = methods[0].value

        # Remove None values
        request_data = {k: v for k, v in request_data.items() if v is not None}

        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                logger.info("Using WebCrawler service", extra={"url": url})
                response = await client.post(self.webcrawler_url, json=request_data)
                response.raise_for_status()

                result = response.json()

                if result["status"] == "success":
                    logger.info(
                        "WebCrawler extraction successful",
                        extra={
                            "url": url,
                            "final_url": result.get("final_url"),
                            "status_code": result.get("status_code"),
                            "method_used": result.get("method_used"),
                        },
                    )
                    return {
                        "status": "success",
                        "content": result.get("content"),
                        "final_url": result.get("final_url"),
                        "status_code": result.get("status_code"),
                        "service_used": "webcrawler",
                        "method_used": result.get("method_used"),
                    }
                else:
                    logger.error(
                        "WebCrawler extraction failed",
                        extra={"url": url, "error": result.get("error")},
                    )
                    return {
                        "status": "error",
                        "error": result.get("error"),
                        "service_used": "webcrawler",
                    }

        except Exception as e:
            logger.error(
                "WebCrawler service error",
                exc_info=True,
                extra={"url": url, "error": str(e)},
            )
            return {"status": "error", "error": str(e), "service_used": "webcrawler"}

    def extract_content(
        self,
        url: str,
        proxy: Optional[str] = None,
        timeout: int = 30,
        wait_after_load: int = 3000,
        execute_script: Optional[str] = None,
        wait_for_selector: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for extract_content_async.
        """
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.extract_content_async(
                    url,
                    proxy,
                    timeout,
                    wait_after_load,
                    execute_script,
                    wait_for_selector,
                    headers,
                ),
                loop,
            )
            return future.result()
        except RuntimeError:
            return asyncio.run(
                self.extract_content_async(
                    url,
                    proxy,
                    timeout,
                    wait_after_load,
                    execute_script,
                    wait_for_selector,
                    headers,
                )
            )


# Global client instance
extraction_client = ExtractionClient()
