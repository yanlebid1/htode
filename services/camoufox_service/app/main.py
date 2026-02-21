"""
Camoufox Service - A browser automation service for JavaScript-heavy websites.
"""

import asyncio
import logging
from typing import Optional, Any, List
from contextlib import asynccontextmanager
import urllib.parse
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field
from camoufox.async_api import AsyncCamoufox

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Request/Response models
class BrowserRequest(BaseModel):
    url: str = Field(..., description="URL to load in browser")
    wait_after_load: int = Field(
        3000, ge=0, le=30000, description="Time to wait after page load (milliseconds)"
    )
    proxy: Optional[str] = Field(None, description="Optional proxy URL")
    timeout: int = Field(30, ge=1, le=120, description="Timeout in seconds")
    execute_script: Optional[str] = Field(
        None, max_length=10000, description="Optional JavaScript to execute on the page"
    )
    wait_for_selector: Optional[str] = Field(
        None, max_length=500, description="Optional CSS selector to wait for"
    )


class BrowserResponse(BaseModel):
    status: str = Field(..., description="Status: 'success' or 'error'")
    content: Optional[str] = Field(None, description="Page HTML content")
    final_url: Optional[str] = Field(None, description="Final URL after redirects")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    script_result: Optional[Any] = Field(None, description="Result of executed script")
    error: Optional[str] = Field(None, description="Error message if failed")


# Browser pool management
class BrowserPool:
    def __init__(self, size: int = None):
        # Scale browser pool size significantly - use env var with high default
        self.size = size or int(os.getenv('BROWSER_POOL_SIZE', '15'))  # Increased from 3 to 15
        self.browsers: List[AsyncCamoufox] = []
        self.available = asyncio.Queue(maxsize=self.size)
        self._lock = asyncio.Lock()
        self._initialized = False
        self._active_sessions = 0
        self._total_requests = 0
        self._failed_requests = 0

    async def initialize(self):
        """Initialize the browser pool"""
        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing browser pool", extra={"size": self.size})
            successful_browsers = 0
            
            for i in range(self.size):
                try:
                    browser = await self._create_browser()
                    self.browsers.append(browser)
                    await self.available.put(browser)
                    successful_browsers += 1
                    logger.info("Browser initialized", extra={"completed": successful_browsers, "total": self.size})
                except Exception as e:
                    logger.error("Failed to create browser", extra={"browser_number": i+1, "error": str(e)})

            self._initialized = True
            logger.info("Browser pool initialization complete", extra={"ready": successful_browsers, "total": self.size})
            
            if successful_browsers == 0:
                raise RuntimeError("Failed to initialize any browsers in pool")

    async def _create_browser(self) -> AsyncCamoufox:
        """Create a new browser instance with optimized settings"""
        return await AsyncCamoufox(
            headless=True,
            os="windows",
            locale="uk-UA", 
            geoip=True,
            block_webrtc=True,
            humanize=True,
            # Performance optimizations
            disable_blink_features="AutomationControlled",
            disable_web_security=True,
            no_sandbox=True,
            disable_dev_shm_usage=True,
        ).__aenter__()

    async def acquire(self) -> AsyncCamoufox:
        """Acquire a browser from the pool"""
        if not self._initialized:
            await self.initialize()
        
        self._active_sessions += 1
        self._total_requests += 1
        logger.debug("Acquiring browser", extra={"active_sessions": self._active_sessions, "available": self.available.qsize()})
        
        browser = await self.available.get()
        return browser

    async def release(self, browser: AsyncCamoufox):
        """Release a browser back to the pool"""
        self._active_sessions -= 1
        await self.available.put(browser)
        logger.debug("Released browser", extra={"active_sessions": self._active_sessions, "available": self.available.qsize()})

    async def get_stats(self) -> dict:
        """Get browser pool statistics"""
        return {
            'pool_size': self.size,
            'available_browsers': self.available.qsize(),
            'active_sessions': self._active_sessions,
            'total_requests': self._total_requests,
            'failed_requests': self._failed_requests,
            'success_rate': ((self._total_requests - self._failed_requests) / self._total_requests * 100) if self._total_requests > 0 else 0
        }

    async def shutdown(self):
        """Shutdown all browsers in the pool"""
        logger.info("Shutting down browser pool")
        for browser in self.browsers:
            try:
                await browser.__aexit__(None, None, None)
            except Exception as e:
                logger.error("Error closing browser", extra={"error": str(e)})
        self.browsers.clear()
        self._initialized = False


# Create global browser pool with environment-based sizing
browser_pool = BrowserPool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    await browser_pool.initialize()
    yield
    # Shutdown
    await browser_pool.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Camoufox Service",
    description="Browser automation service for JavaScript-heavy websites",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "camoufox"}


@app.get("/stats")
async def get_browser_stats():
    """Get browser pool statistics for monitoring"""
    stats = await browser_pool.get_stats()
    return {
        "status": "success",
        "browser_pool": stats,
        "service": "camoufox",
        "timestamp": f"{asyncio.get_running_loop().time()}"
    }


@app.post("/browse", response_model=BrowserResponse)
async def browse_page(request: BrowserRequest):
    """Load a page in browser and return content"""
    browser = None
    page = None

    try:
        # Prepare proxy configuration if provided
        proxy_config = None
        if request.proxy:
            parsed = urllib.parse.urlparse(request.proxy)
            proxy_config = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            }
            if parsed.username and parsed.password:
                proxy_config["username"] = parsed.username
                proxy_config["password"] = parsed.password

        # Acquire browser from pool
        browser = await browser_pool.acquire()

        # Create new page with proxy if needed
        if proxy_config:
            context = await browser.new_context(proxy=proxy_config)
            page = await context.new_page()
        else:
            page = await browser.new_page()

        # Navigate to URL
        logger.info("Navigating to URL", extra={"url": request.url})
        response = await page.goto(
            request.url, wait_until="domcontentloaded", timeout=request.timeout * 1000
        )

        # Wait for selector if specified
        if request.wait_for_selector:
            try:
                await page.wait_for_selector(request.wait_for_selector, timeout=10000)
                logger.info("Found selector", extra={"selector": request.wait_for_selector})
            except Exception as e:
                logger.warning("Selector not found", extra={"selector": request.wait_for_selector, "error": str(e)})

        # Wait for any dynamic content
        await page.wait_for_timeout(request.wait_after_load)

        # Execute script if provided
        script_result = None
        if request.execute_script:
            try:
                script_result = await page.evaluate(request.execute_script)
                logger.info("Script executed successfully")
            except Exception as e:
                logger.error("Script execution failed", extra={"error": str(e)})

        # Get final content and info
        content = await page.content()
        final_url = page.url
        status_code = response.status if response else None

        logger.info("Successfully loaded page", extra={"url": request.url})

        return BrowserResponse(
            status="success",
            content=content,
            final_url=final_url,
            status_code=status_code,
            script_result=script_result,
        )

    except Exception as e:
        logger.error("Browser automation failed", extra={"url": request.url, "error": str(e)})
        # Track failed requests
        browser_pool._failed_requests += 1
        return BrowserResponse(status="error", error=str(e))

    finally:
        # Clean up
        if page:
            await page.close()
        if browser:
            await browser_pool.release(browser)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
