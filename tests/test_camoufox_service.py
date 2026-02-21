# tests/test_camoufox_service.py

import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# Mock camoufox before importing the service module
sys.modules.setdefault("camoufox", MagicMock())
sys.modules.setdefault("camoufox.async_api", MagicMock())

from pydantic import ValidationError
from services.camoufox_service.app.main import BrowserPool, BrowserRequest


class TestBrowserPool:
    """Tests for the BrowserPool stats and state."""

    def test_initial_pool_stats(self):
        """Test initial pool state before initialization."""
        pool = BrowserPool(size=5)
        assert pool.size == 5
        assert pool._initialized is False
        assert pool._total_requests == 0
        assert pool._failed_requests == 0
        assert pool._active_sessions == 0

    async def test_pool_stats_after_requests(self):
        """Test that stats track requests and failures."""
        pool = BrowserPool(size=2)
        pool._total_requests = 10
        pool._failed_requests = 2
        pool._active_sessions = 1

        stats = await pool.get_stats()
        assert stats["total_requests"] == 10
        assert stats["failed_requests"] == 2
        assert stats["active_sessions"] == 1

    async def test_success_rate_calculation(self):
        """Test that success rate is calculated correctly."""
        pool = BrowserPool(size=2)
        pool._total_requests = 100
        pool._failed_requests = 10

        stats = await pool.get_stats()
        assert stats["success_rate"] == 90.0

    async def test_success_rate_zero_requests(self):
        """Test that success rate is 0 when no requests have been made."""
        pool = BrowserPool(size=2)
        stats = await pool.get_stats()
        assert stats["success_rate"] == 0


class TestCamoufoxHealthEndpoint:
    """Tests for the /health endpoint."""

    async def test_health_unhealthy_when_not_initialized(self):
        """Test that health returns 503 when pool is not initialized."""
        from services.camoufox_service.app.main import health_check, browser_pool

        orig_initialized = browser_pool._initialized
        orig_available = browser_pool.available

        try:
            browser_pool._initialized = False
            browser_pool.available = MagicMock()
            browser_pool.available.qsize.return_value = 0

            response = await health_check()
            # Should be a JSONResponse with 503
            assert response.status_code == 503
        finally:
            browser_pool._initialized = orig_initialized
            browser_pool.available = orig_available

    async def test_health_healthy_when_initialized(self):
        """Test that health returns 200 when pool is initialized with browsers."""
        from services.camoufox_service.app.main import health_check, browser_pool

        orig_initialized = browser_pool._initialized
        orig_available = browser_pool.available

        try:
            browser_pool._initialized = True
            browser_pool.available = MagicMock()
            browser_pool.available.qsize.return_value = 5

            response = await health_check()
            # When healthy, it returns a dict (not JSONResponse)
            assert isinstance(response, dict)
            assert response["status"] == "healthy"
        finally:
            browser_pool._initialized = orig_initialized
            browser_pool.available = orig_available


class TestBrowserRequestValidation:
    """Tests for BrowserRequest Pydantic model validation."""

    def test_valid_request(self):
        req = BrowserRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.wait_after_load == 3000
        assert req.timeout == 30

    def test_timeout_over_max(self):
        with pytest.raises(ValidationError):
            BrowserRequest(url="https://example.com", timeout=200)

    def test_timeout_under_min(self):
        with pytest.raises(ValidationError):
            BrowserRequest(url="https://example.com", timeout=0)

    def test_wait_after_load_negative(self):
        with pytest.raises(ValidationError):
            BrowserRequest(url="https://example.com", wait_after_load=-1)

    def test_wait_after_load_over_max(self):
        with pytest.raises(ValidationError):
            BrowserRequest(url="https://example.com", wait_after_load=50000)

    def test_script_max_length(self):
        with pytest.raises(ValidationError):
            BrowserRequest(
                url="https://example.com",
                execute_script="x" * 10001,
            )

    def test_valid_with_all_options(self):
        req = BrowserRequest(
            url="https://example.com",
            wait_after_load=5000,
            timeout=60,
            execute_script="return document.title;",
            wait_for_selector=".content",
        )
        assert req.timeout == 60
        assert req.execute_script == "return document.title;"
