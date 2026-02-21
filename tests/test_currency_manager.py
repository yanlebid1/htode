# tests/test_currency_manager.py

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

from common.utils.currency_manager import (
    CurrencyRateManager,
    _rate_from_privat,
    _rate_from_monobank,
    get_usd_uah_rate,
    CURRENCY_RATE_CACHE_KEY,
)


# ── CurrencyRateManager.convert_usd_to_uah() ────────────────────────────────


class TestConvertUsdToUah:
    @patch.object(CurrencyRateManager, "get_usd_uah_rate", return_value=Decimal("41.50"))
    def test_correct_conversion(self, mock_rate):
        result = CurrencyRateManager.convert_usd_to_uah(Decimal("100"))
        assert result == Decimal("4150.00")


# ── CurrencyRateManager.convert_to_uah() ────────────────────────────────────


class TestConvertToUah:
    @patch.object(CurrencyRateManager, "get_usd_uah_rate", return_value=Decimal("41.00"))
    def test_usd_conversion(self, mock_rate):
        result = CurrencyRateManager.convert_to_uah(Decimal("50"), "USD")
        assert result == Decimal("2050.00")

    def test_uah_passthrough(self):
        result = CurrencyRateManager.convert_to_uah(Decimal("1000"), "UAH")
        assert result == Decimal("1000")


# ── CurrencyRateManager.get_usd_uah_rate() ──────────────────────────────────


class TestGetUsdUahRate:
    @patch("common.utils.currency_manager.BaseCacheManager")
    def test_returns_cached_rate(self, mock_cache):
        mock_cache.get.return_value = "41.50"
        result = CurrencyRateManager.get_usd_uah_rate()
        assert result == Decimal("41.50")

    @patch.object(CurrencyRateManager, "update_rate", return_value=Decimal("42.00"))
    @patch("common.utils.currency_manager.BaseCacheManager")
    def test_fetches_if_not_cached(self, mock_cache, mock_update):
        mock_cache.get.return_value = None
        result = CurrencyRateManager.get_usd_uah_rate()
        assert result == Decimal("42.00")
        mock_update.assert_called_once()


# ── _rate_from_privat() ──────────────────────────────────────────────────────


class TestRateFromPrivat:
    @pytest.mark.asyncio
    async def test_parses_privat_response(self):
        # Create an async context manager for session.get()
        mock_response = MagicMock()
        mock_response.json = AsyncMock(
            return_value=[
                {"ccy": "EUR", "base_ccy": "UAH", "sale": "44.00"},
                {"ccy": "USD", "base_ccy": "UAH", "sale": "41.50"},
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_ctx

        result = await _rate_from_privat(mock_session)
        assert result == Decimal("41.50")


# ── _rate_from_monobank() ────────────────────────────────────────────────────


class TestRateFromMonobank:
    @pytest.mark.asyncio
    async def test_parses_monobank_response(self):
        mock_response = MagicMock()
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "currencyCodeA": 840,
                    "currencyCodeB": 980,
                    "rateSell": 41.80,
                    "rateCross": 41.50,
                },
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_ctx

        result = await _rate_from_monobank(mock_session)
        assert result == Decimal("41.8")


# ── get_usd_uah_rate() async ─────────────────────────────────────────────────


class TestGetUsdUahRateAsync:
    @pytest.mark.asyncio
    async def test_monobank_success(self):
        """When Monobank succeeds, use its rate."""
        mock_response = MagicMock()
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "currencyCodeA": 840,
                    "currencyCodeB": 980,
                    "rateSell": 41.50,
                    "rateCross": 41.00,
                },
            ]
        )
        mock_response.raise_for_status = MagicMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_ctx

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("common.utils.currency_manager.aiohttp.ClientSession", return_value=mock_session_ctx):
            result = await get_usd_uah_rate()
        assert result == Decimal("41.5")
