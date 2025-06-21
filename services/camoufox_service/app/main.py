"""
Camoufox Service - A browser automation service for JavaScript-heavy websites.
"""

import asyncio
import logging
from typing import Optional, Any, List
from contextlib import asynccontextmanager
import urllib.parse

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
        3000, description="Time to wait after page load (milliseconds)"
    )
    proxy: Optional[str] = Field(None, description="Optional proxy URL")
    timeout: int = Field(30, description="Timeout in seconds")
    execute_script: Optional[str] = Field(
        None, description="Optional JavaScript to execute on the page"
    )
    wait_for_selector: Optional[str] = Field(
        None, description="Optional CSS selector to wait for"
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
    def __init__(self, size: int = 3):
        self.size = size
        self.browsers: List[AsyncCamoufox] = []
        self.available = asyncio.Queue(maxsize=size)
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the browser pool"""
        async with self._lock:
            if self._initialized:
                return

            logger.info(f"Initializing browser pool with {self.size} instances")
            for i in range(self.size):
                try:
                    browser = await self._create_browser()
                    self.browsers.append(browser)
                    await self.available.put(browser)
                    logger.info(f"Browser {i+1}/{self.size} initialized")
                except Exception as e:
                    logger.error(f"Failed to create browser {i+1}: {e}")

            self._initialized = True
            logger.info("Browser pool initialization complete")

    async def _create_browser(self) -> AsyncCamoufox:
        """Create a new browser instance"""
        return await AsyncCamoufox(
            headless=True,
            os="windows",
            locale="uk-UA",
            geoip=True,
            block_webrtc=True,
            humanize=True,
        ).__aenter__()

    async def acquire(self) -> AsyncCamoufox:
        """Acquire a browser from the pool"""
        if not self._initialized:
            await self.initialize()
        return await self.available.get()

    async def release(self, browser: AsyncCamoufox):
        """Release a browser back to the pool"""
        await self.available.put(browser)

    async def shutdown(self):
        """Shutdown all browsers in the pool"""
        logger.info("Shutting down browser pool")
        for browser in self.browsers:
            try:
                await browser.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
        self.browsers.clear()
        self._initialized = False


# Create global browser pool
browser_pool = BrowserPool(size=3)


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
        logger.info(f"Navigating to {request.url}")
        response = await page.goto(
            request.url, wait_until="domcontentloaded", timeout=request.timeout * 1000
        )

        # Wait for selector if specified
        if request.wait_for_selector:
            try:
                await page.wait_for_selector(request.wait_for_selector, timeout=10000)
                logger.info(f"Found selector: {request.wait_for_selector}")
            except Exception as e:
                logger.warning(f"Selector not found: {request.wait_for_selector}, error: {e}")

        # Wait for any dynamic content
        await page.wait_for_timeout(request.wait_after_load)

        # Execute script if provided
        script_result = None
        if request.execute_script:
            try:
                script_result = await page.evaluate(request.execute_script)
                logger.info("Script executed successfully")
            except Exception as e:
                logger.error(f"Script execution failed: {e}")

        # Get final content and info
        content = await page.content()
        final_url = page.url
        status_code = response.status if response else None

        logger.info(f"Successfully loaded {request.url}")

        return BrowserResponse(
            status="success",
            content=content,
            final_url=final_url,
            status_code=status_code,
            script_result=script_result,
        )

    except Exception as e:
        logger.error(f"Browser automation failed for {request.url}: {e}")
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
