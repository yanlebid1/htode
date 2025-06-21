"""
Client for the Camoufox service API.
This is a backward compatibility wrapper that delegates to the extraction client.
"""

import asyncio
from typing import Optional, Dict, Any
import httpx
from common.utils import logger
from common.utils.logging_config import log_operation
from common.utils.extraction_client import extraction_client

# Default service URL - can be overridden via environment variable
import os

CAMOUFOX_SERVICE_URL = os.getenv("CAMOUFOX_SERVICE_URL", "http://camoufox_service:8100")


class CamoufoxClient:
    """Client for interacting with the Camoufox service - backward compatibility wrapper"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or CAMOUFOX_SERVICE_URL
        self.health_url = f"{self.base_url}/health"
        logger.warning("CamoufoxClient is deprecated. Use extraction_client instead.")

    @log_operation("camoufox_extract")
    async def extract_async(
        self,
        url: str,
        extraction_type: str = "content",
        proxy: Optional[str] = None,
        timeout: int = 30,
        wait_after_load: int = 3000,
    ) -> Dict[str, Any]:
        """
        Extract data from a URL using the extraction client.

        Args:
            url: URL to extract from
            extraction_type: Type of extraction ("content" or "phone_numbers") - ignored, always returns content
            proxy: Optional proxy URL
            timeout: Timeout in seconds
            wait_after_load: Time to wait after page load (milliseconds)

        Returns:
            Dict with extraction results
        """
        # Use extraction client which will route to the appropriate service
        result = await extraction_client.extract_content_async(
            url=url, proxy=proxy, timeout=timeout, wait_after_load=wait_after_load
        )

        # Transform to match old format
        if result["status"] == "success":
            return {
                "status": "success",
                "status_code": result.get("status_code"),
                "final_url": result.get("final_url"),
                "data": {"content": result.get("content")},
            }
        else:
            return {"status": "error", "error": result.get("error")}

    def extract(
        self,
        url: str,
        extraction_type: str = "content",
        proxy: Optional[str] = None,
        timeout: int = 30,
        wait_after_load: int = 3000,
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for extract_async.
        """
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.extract_async(
                    url, extraction_type, proxy, timeout, wait_after_load
                ),
                loop,
            )
            return future.result()
        except RuntimeError:
            return asyncio.run(
                self.extract_async(
                    url, extraction_type, proxy, timeout, wait_after_load
                )
            )

    async def health_check_async(self) -> bool:
        """Check if the Camoufox service is healthy"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.health_url)
                return response.status_code == 200
        except Exception:
            return False

    def health_check(self) -> bool:
        """Synchronous wrapper for health check"""
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.health_check_async(), loop)
            return future.result()
        except RuntimeError:
            return asyncio.run(self.health_check_async())


# Global client instance
camoufox_client = CamoufoxClient()
