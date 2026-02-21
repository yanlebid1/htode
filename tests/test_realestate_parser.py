# tests/test_realestate_parser.py

import sys
from unittest.mock import MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.phone_utils.parsers.realestate_parser import (
    parse_real_estate_lviv,
    REAL_ESTATE_LVIV_API,
)
from common.utils.phone_utils.phone_models import ExtractionResult


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.proxy = None
    client.fetch = AsyncMock()
    return client


# ── parse_real_estate_lviv() ─────────────────────────────────────────────


class TestParseRealEstateLviv:
    @pytest.mark.asyncio
    async def test_extracts_phone_from_ajax_response(self, mock_client):
        # Simulate the AJAX response containing an encoded tel link
        ajax_response = 'some html <a href=\\u0022tel:+380501234567\\u0022>Call</a>'
        mock_client.fetch.return_value = ajax_response

        result = await parse_real_estate_lviv(
            "https://www.real-estate.lviv.ua/en/realty/12345-some-listing", mock_client
        )
        assert isinstance(result, ExtractionResult)
        assert len(result.phone_numbers) >= 1

    @pytest.mark.asyncio
    async def test_calls_ajax_api_with_correct_id(self, mock_client):
        mock_client.fetch.return_value = ""

        await parse_real_estate_lviv(
            "https://www.real-estate.lviv.ua/en/realty/99999-nice-apartment", mock_client
        )
        # Verify fetch was called with the API URL containing the ad ID
        call_args = mock_client.fetch.call_args
        url_called = call_args[0][0]
        assert "99999" in url_called

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_phone_in_response(self, mock_client):
        mock_client.fetch.return_value = "<div>No phone data here</div>"

        result = await parse_real_estate_lviv(
            "https://www.real-estate.lviv.ua/en/realty/12345-listing", mock_client
        )
        assert result.phone_numbers == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_fetch_returns_none(self, mock_client):
        mock_client.fetch.return_value = None

        result = await parse_real_estate_lviv(
            "https://www.real-estate.lviv.ua/en/realty/12345-listing", mock_client
        )
        assert result.phone_numbers == []

    @pytest.mark.asyncio
    async def test_handles_fetch_exception_gracefully(self, mock_client):
        mock_client.fetch.side_effect = Exception("network error")

        result = await parse_real_estate_lviv(
            "https://www.real-estate.lviv.ua/en/realty/12345-listing", mock_client
        )
        assert isinstance(result, ExtractionResult)
        assert result.phone_numbers == []
