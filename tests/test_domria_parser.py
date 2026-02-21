# tests/test_domria_parser.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.phone_utils.parsers.domria_parser import parse_domria_page
from common.utils.phone_utils.phone_models import ExtractionResult


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.proxy = None
    client.fetch = AsyncMock()
    return client


# ── parse_domria_page() ─────────────────────────────────────────────────


class TestParseDomriaPage:
    @pytest.mark.asyncio
    async def test_extracts_phone_from_tel_link(self, mock_client):
        html = '<html><body><a href="tel:+380501234567">Call</a></body></html>'
        mock_client.fetch.return_value = html

        result = await parse_domria_page("https://dom.ria.com/uk/ad/123", mock_client)
        assert isinstance(result, ExtractionResult)
        assert len(result.phone_numbers) >= 1
        assert any("380501234567" in p for p in result.phone_numbers)

    @pytest.mark.asyncio
    async def test_extracts_phone_from_text_pattern(self, mock_client):
        html = "<html><body><p>Phone: +38 (067) 123-45-67</p></body></html>"
        mock_client.fetch.return_value = html

        result = await parse_domria_page("https://dom.ria.com/uk/ad/456", mock_client)
        assert len(result.phone_numbers) >= 1

    @pytest.mark.asyncio
    @patch("common.utils.phone_utils.parsers.domria_parser.extraction_client")
    async def test_falls_back_to_browser_when_no_phones_in_html(self, mock_ext, mock_client):
        # HTML has no phone info
        mock_client.fetch.return_value = "<html><body><p>No phone here</p></body></html>"

        # Browser extraction returns phone
        mock_ext.extract_content_async = AsyncMock(return_value={
            "status": "success",
            "content": '<html><body><a href="tel:+380991234567">Call</a></body></html>',
        })

        result = await parse_domria_page("https://dom.ria.com/uk/ad/789", mock_client)
        assert len(result.phone_numbers) >= 1

    @pytest.mark.asyncio
    @patch("common.utils.phone_utils.parsers.domria_parser.extraction_client")
    async def test_returns_empty_when_browser_extraction_fails(self, mock_ext, mock_client):
        mock_client.fetch.return_value = "<html><body>No phone</body></html>"
        mock_ext.extract_content_async = AsyncMock(return_value={
            "status": "error",
            "error": "timeout",
        })

        result = await parse_domria_page("https://dom.ria.com/uk/ad/000", mock_client)
        assert result.phone_numbers == []

    @pytest.mark.asyncio
    async def test_handles_fetch_failure_gracefully(self, mock_client):
        mock_client.fetch.side_effect = Exception("connection refused")

        # Should not crash — falls through to browser extraction
        with patch(
            "common.utils.phone_utils.parsers.domria_parser.extraction_client"
        ) as mock_ext:
            mock_ext.extract_content_async = AsyncMock(return_value={
                "status": "error", "error": "also failed"
            })
            result = await parse_domria_page("https://dom.ria.com/uk/ad/err", mock_client)
            assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_html(self, mock_client):
        mock_client.fetch.return_value = ""

        with patch(
            "common.utils.phone_utils.parsers.domria_parser.extraction_client"
        ) as mock_ext:
            mock_ext.extract_content_async = AsyncMock(return_value={
                "status": "error", "error": "no content"
            })
            result = await parse_domria_page("https://dom.ria.com/uk/ad/empty", mock_client)
            assert result.phone_numbers == []
