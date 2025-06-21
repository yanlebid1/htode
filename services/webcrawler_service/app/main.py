"""
WebCrawler Service - Lightweight HTTP client service for web scraping.
"""

import logging
from typing import Optional, Dict
from enum import Enum

from fastapi import FastAPI
from pydantic import BaseModel, Field
import aiohttp
import httpx
from curl_cffi.requests import AsyncSession

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RequestMethod(str, Enum):
    """Available request methods"""

    AIOHTTP = "aiohttp"
    CURL_CFFI = "curl_cffi"
    HTTPX = "httpx"


# Request/Response models
class CrawlRequest(BaseModel):
    url: str = Field(..., description="URL to fetch")
    method: Optional[RequestMethod] = Field(None, description="Request method to use")
    proxy: Optional[str] = Field(None, description="Optional proxy URL")
    timeout: int = Field(30, description="Timeout in seconds")
    headers: Optional[Dict[str, str]] = Field(None, description="Optional HTTP headers")
    follow_redirects: bool = Field(True, description="Whether to follow redirects")
    impersonate: Optional[str] = Field(
        None, description="Browser to impersonate (for curl_cffi)"
    )


class CrawlResponse(BaseModel):
    status: str = Field(..., description="Status: 'success' or 'error'")
    content: Optional[str] = Field(None, description="Page content")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    final_url: Optional[str] = Field(None, description="Final URL after redirects")
    method_used: Optional[str] = Field(
        None, description="Request method that succeeded"
    )
    error: Optional[str] = Field(None, description="Error message if failed")


# Create FastAPI app
app = FastAPI(
    title="WebCrawler Service",
    description="Lightweight HTTP client service for web scraping",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "webcrawler"}


async def fetch_with_aiohttp(
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
) -> tuple[Optional[str], int, str]:
    """Fetch using aiohttp"""
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)

        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            kwargs = {
                "ssl": False,
                "allow_redirects": follow_redirects,
                "headers": headers or {},
            }
            if proxy:
                kwargs["proxy"] = proxy

            async with session.get(url, **kwargs) as response:
                content = await response.text()
                final_url = str(response.url)
                return content, response.status, final_url

    except Exception as e:
        logger.warning(f"aiohttp failed for {url}: {e}")
        raise


async def fetch_with_curl_cffi(
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    impersonate: Optional[str] = None,
) -> tuple[Optional[str], int, str]:
    """Fetch using curl_cffi with browser impersonation"""
    impersonate = impersonate or "chrome110"

    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None

        async with AsyncSession(
            impersonate=impersonate, timeout=timeout, proxies=proxies
        ) as session:
            response = await session.get(
                url, headers=headers or {}, allow_redirects=follow_redirects
            )
            return response.text, response.status_code, str(response.url)

    except Exception as e:
        logger.warning(f"curl_cffi failed for {url}: {e}")
        raise


async def fetch_with_httpx(
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
) -> tuple[Optional[str], int, str]:
    """Fetch using httpx with HTTP/2 support"""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            proxy=proxy,
            follow_redirects=follow_redirects,
            http2=True,
            verify=False,
            headers=headers or {},
        ) as client:
            response = await client.get(url)
            return response.text, response.status_code, str(response.url)

    except Exception as e:
        logger.warning(f"httpx failed for {url}: {e}")
        raise


@app.post("/crawl", response_model=CrawlResponse)
async def crawl_page(request: CrawlRequest):
    """Fetch a web page using the specified method"""

    # Determine which methods to try
    if request.method:
        methods = [request.method]
    else:
        # Default order: aiohttp -> curl_cffi -> httpx
        methods = [RequestMethod.AIOHTTP, RequestMethod.CURL_CFFI, RequestMethod.HTTPX]

    last_error = None

    # Try each method
    for method in methods:
        try:
            logger.info(f"Trying {method} for {request.url}")

            if method == RequestMethod.AIOHTTP:
                content, status_code, final_url = await fetch_with_aiohttp(
                    request.url,
                    request.proxy,
                    request.timeout,
                    request.headers,
                    request.follow_redirects,
                )
            elif method == RequestMethod.CURL_CFFI:
                content, status_code, final_url = await fetch_with_curl_cffi(
                    request.url,
                    request.proxy,
                    request.timeout,
                    request.headers,
                    request.follow_redirects,
                    request.impersonate,
                )
            elif method == RequestMethod.HTTPX:
                content, status_code, final_url = await fetch_with_httpx(
                    request.url,
                    request.proxy,
                    request.timeout,
                    request.headers,
                    request.follow_redirects,
                )
            else:
                raise ValueError(f"Unknown method: {method}")

            # Success!
            logger.info(f"Successfully fetched {request.url} with {method}")
            return CrawlResponse(
                status="success",
                content=content,
                status_code=status_code,
                final_url=final_url,
                method_used=method.value,
            )

        except Exception as e:
            logger.warning(f"{method} failed: {e}")
            last_error = str(e)
            continue

    # All methods failed
    logger.error(f"All methods failed for {request.url}")
    return CrawlResponse(
        status="error", error=f"All methods failed. Last error: {last_error}"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8200)
