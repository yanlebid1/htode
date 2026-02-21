# tests/test_extraction_client.py

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

from common.utils.extraction_client import ExtractionClient


# ── ExtractionClient.__init__() ──────────────────────────────────────────────


class TestExtractionClientInit:
    def test_sets_correct_urls_from_env(self):
        client = ExtractionClient()
        assert "/browse" in client.camoufox_url
        assert "/crawl" in client.webcrawler_url

    @patch.dict("os.environ", {
        "CAMOUFOX_SERVICE_URL": "http://custom-camoufox:9000",
        "WEBCRAWLER_SERVICE_URL": "http://custom-webcrawler:9001",
    })
    def test_custom_env_urls(self):
        # Re-import to pick up new env
        import importlib
        import common.utils.extraction_client as mod
        importlib.reload(mod)
        client = mod.ExtractionClient()
        assert client.camoufox_url == "http://custom-camoufox:9000/browse"
        assert client.webcrawler_url == "http://custom-webcrawler:9001/crawl"
        # Reload back to defaults
        importlib.reload(mod)


# ── extract_content_async() ──────────────────────────────────────────────────


class TestExtractContentAsync:
    @pytest.mark.asyncio
    @patch.object(ExtractionClient, "_extract_with_camoufox", new_callable=AsyncMock)
    async def test_routes_olx_to_camoufox(self, mock_camoufox):
        mock_camoufox.return_value = {"status": "success", "service_used": "camoufox"}
        client = ExtractionClient()

        result = await client.extract_content_async("https://www.olx.ua/d/uk/ad/123")
        mock_camoufox.assert_called_once()
        assert result["service_used"] == "camoufox"

    @pytest.mark.asyncio
    @patch.object(ExtractionClient, "_extract_with_webcrawler", new_callable=AsyncMock)
    async def test_routes_lun_to_webcrawler(self, mock_webcrawler):
        mock_webcrawler.return_value = {"status": "success", "service_used": "webcrawler"}
        client = ExtractionClient()

        result = await client.extract_content_async("https://lun.ua/uk/search")
        mock_webcrawler.assert_called_once()
        assert result["service_used"] == "webcrawler"


# ── _extract_with_camoufox() ────────────────────────────────────────────────


class TestExtractWithCamoufox:
    @pytest.mark.asyncio
    @patch("common.utils.extraction_client.httpx.AsyncClient")
    async def test_success_returns_content(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "content": "<html>test</html>",
            "final_url": "https://olx.ua/final",
            "status_code": 200,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = ExtractionClient()
        result = await client._extract_with_camoufox(
            "https://olx.ua/ad/123", None, 30, 3000, None, None
        )

        assert result["status"] == "success"
        assert result["content"] == "<html>test</html>"
        assert result["service_used"] == "camoufox"

    @pytest.mark.asyncio
    @patch("common.utils.extraction_client.httpx.AsyncClient")
    async def test_service_error_returns_error_dict(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "Browser timeout",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = ExtractionClient()
        result = await client._extract_with_camoufox(
            "https://olx.ua/ad/123", None, 30, 3000, None, None
        )

        assert result["status"] == "error"
        assert result["service_used"] == "camoufox"

    @pytest.mark.asyncio
    @patch("common.utils.extraction_client.httpx.AsyncClient")
    async def test_http_exception_returns_error_dict(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = ExtractionClient()
        result = await client._extract_with_camoufox(
            "https://olx.ua/ad/123", None, 30, 3000, None, None
        )

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["service_used"] == "camoufox"


# ── _extract_with_webcrawler() ──────────────────────────────────────────────


class TestExtractWithWebcrawler:
    @pytest.mark.asyncio
    @patch("common.utils.extraction_client.httpx.AsyncClient")
    async def test_success_returns_content_with_method_used(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "content": "<html>crawler</html>",
            "final_url": "https://lun.ua/final",
            "status_code": 200,
            "method_used": "aiohttp",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = ExtractionClient()
        result = await client._extract_with_webcrawler(
            "https://lun.ua/uk/search", None, 30, None
        )

        assert result["status"] == "success"
        assert result["service_used"] == "webcrawler"
        assert result["method_used"] == "aiohttp"

    @pytest.mark.asyncio
    @patch("common.utils.extraction_client.httpx.AsyncClient")
    async def test_error_returns_error_dict(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Service down")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        client = ExtractionClient()
        result = await client._extract_with_webcrawler(
            "https://lun.ua/uk/search", None, 30, None
        )

        assert result["status"] == "error"
        assert result["service_used"] == "webcrawler"


# ── extract_content() (sync wrapper) ────────────────────────────────────────


class TestExtractContentSync:
    @patch.object(ExtractionClient, "extract_content_async", new_callable=AsyncMock)
    def test_delegates_to_async_method(self, mock_async):
        mock_async.return_value = {"status": "success", "service_used": "webcrawler"}

        client = ExtractionClient()
        result = client.extract_content("https://lun.ua/uk/search")

        assert result["status"] == "success"
        mock_async.assert_called_once()
