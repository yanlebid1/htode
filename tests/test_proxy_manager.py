# tests/test_proxy_manager.py

import sys
import json
import time
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
import aiohttp

import common.utils.phone_utils.proxy_manager as pm
from common.utils.phone_utils.proxy_manager import (
    get_random_proxy,
    proxies_available,
    get_proxy_count,
    _convert_api_proxies_to_urls,
    _save_proxies_to_cache,
    _load_proxies_from_cache,
    _fetch_proxies_from_api,
    ProxyAPIError,
)


@pytest.fixture(autouse=True)
def reset_proxy_state():
    """Reset global proxy state between tests."""
    original_proxies = pm.PROXIES[:]
    original_loaded = pm._proxies_loaded
    pm.PROXIES.clear()
    pm._proxies_loaded = False
    yield
    pm.PROXIES.clear()
    pm.PROXIES.extend(original_proxies)
    pm._proxies_loaded = original_loaded


# ── get_random_proxy() ──────────────────────────────────────────────────


class TestGetRandomProxy:
    @patch.object(pm, "load_proxies")
    def test_returns_none_when_no_proxies_loaded(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.clear()
        result = get_random_proxy()
        assert result is None

    @patch.object(pm, "load_proxies")
    def test_returns_proxy_from_loaded_list(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.extend(["http://user:pass@1.2.3.4:8080", "http://user:pass@5.6.7.8:8080"])
        result = get_random_proxy()
        assert result in pm.PROXIES


# ── proxies_available() ─────────────────────────────────────────────────


class TestProxiesAvailable:
    @patch.object(pm, "load_proxies")
    def test_returns_false_when_empty(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.clear()
        assert proxies_available() is False

    @patch.object(pm, "load_proxies")
    def test_returns_true_when_proxies_loaded(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.append("http://user:pass@1.2.3.4:8080")
        assert proxies_available() is True


# ── get_proxy_count() ───────────────────────────────────────────────────


class TestGetProxyCount:
    @patch.object(pm, "load_proxies")
    def test_returns_zero_when_empty(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.clear()
        assert get_proxy_count() == 0

    @patch.object(pm, "load_proxies")
    def test_returns_correct_count(self, mock_load):
        pm._proxies_loaded = True
        pm.PROXIES.extend(["http://a:b@1.2.3.4:80", "http://a:b@5.6.7.8:80", "http://a:b@9.10.11.12:80"])
        assert get_proxy_count() == 3


# ── _convert_api_proxies_to_urls() ──────────────────────────────────────


class TestConvertApiProxiesToUrls:
    def test_converts_active_proxies_to_urls(self):
        api_proxies = [
            {
                "ip": "1.2.3.4",
                "port_http": 8080,
                "login": "user",
                "password": "pass",
                "status_type": "ACTIVE",
            },
            {
                "ip": "5.6.7.8",
                "port_http": 3128,
                "login": "admin",
                "password": "secret",
                "status_type": "ACTIVE",
            },
        ]
        result = _convert_api_proxies_to_urls(api_proxies)
        assert len(result) == 2
        assert "http://user:pass@1.2.3.4:8080" in result
        assert "http://admin:secret@5.6.7.8:3128" in result

    def test_skips_inactive_proxies(self):
        api_proxies = [
            {"ip": "1.2.3.4", "port_http": 8080, "login": "u", "password": "p", "status_type": "EXPIRED"},
        ]
        result = _convert_api_proxies_to_urls(api_proxies)
        assert len(result) == 0

    def test_handles_missing_fields_gracefully(self):
        api_proxies = [
            {"ip": "1.2.3.4", "status_type": "ACTIVE"},  # missing port, login, password
        ]
        result = _convert_api_proxies_to_urls(api_proxies)
        assert len(result) == 0


# ── _save_proxies_to_cache() ────────────────────────────────────────────


class TestSaveProxiesToCache:
    @patch("builtins.open", new_callable=MagicMock)
    def test_writes_json_to_cache_file(self, mock_open):
        mock_file = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        proxies = [{"ip": "1.2.3.4", "port_http": 8080}]
        _save_proxies_to_cache(proxies)

        mock_open.assert_called_once()
        # json.dump was called with the file handle
        mock_file.write.assert_called()

    @patch("builtins.open", new_callable=MagicMock)
    @patch("common.utils.phone_utils.proxy_manager.time.time", return_value=1700000000.0)
    def test_includes_timestamp_in_cache(self, mock_time, mock_open):
        mock_file = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        _save_proxies_to_cache([])
        # Verify timestamp was used (json.dump writes to file)
        mock_time.assert_called()


# ── _load_proxies_from_cache() ──────────────────────────────────────────


class TestLoadProxiesFromCache:
    @patch("common.utils.phone_utils.proxy_manager._CACHE_FILE")
    def test_returns_none_for_missing_cache(self, mock_cache_file):
        mock_cache_file.exists.return_value = False
        result = _load_proxies_from_cache()
        assert result is None

    @patch("common.utils.phone_utils.proxy_manager.time.time", return_value=1700000000.0)
    @patch("common.utils.phone_utils.proxy_manager._CACHE_FILE")
    def test_returns_proxy_list_from_valid_cache(self, mock_cache_file, mock_time):
        mock_cache_file.exists.return_value = True
        cache_data = {
            "timestamp": 1700000000.0 - 100,  # 100 seconds ago
            "proxies": [{"ip": "1.2.3.4"}],
        }
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file), \
             patch("json.load", return_value=cache_data):
            result = _load_proxies_from_cache()
            assert result == [{"ip": "1.2.3.4"}]

    @patch("common.utils.phone_utils.proxy_manager.time.time", return_value=1700000000.0)
    @patch("common.utils.phone_utils.proxy_manager._CACHE_FILE")
    def test_returns_none_for_expired_cache(self, mock_cache_file, mock_time):
        mock_cache_file.exists.return_value = True
        expired_timestamp = 1700000000.0 - (31 * 24 * 60 * 60)  # 31 days ago
        cache_data = {
            "timestamp": expired_timestamp,
            "proxies": [{"ip": "1.2.3.4"}],
        }
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file), \
             patch("json.load", return_value=cache_data):
            result = _load_proxies_from_cache()
            assert result is None

    @patch("common.utils.phone_utils.proxy_manager._CACHE_FILE")
    def test_returns_none_for_corrupt_json(self, mock_cache_file):
        mock_cache_file.exists.return_value = True
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file), \
             patch("json.load", side_effect=json.JSONDecodeError("bad", "", 0)):
            result = _load_proxies_from_cache()
            assert result is None


# ── _fetch_proxies_from_api() ───────────────────────────────────────────


class TestFetchProxiesFromApi:
    @pytest.mark.asyncio
    async def test_raises_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            # Ensure PROXY_SALE_API_KEY is not set
            import os
            os.environ.pop("PROXY_SALE_API_KEY", None)
            with pytest.raises(ProxyAPIError, match="PROXY_SALE_API_KEY"):
                await _fetch_proxies_from_api()

    @pytest.mark.asyncio
    async def test_returns_proxy_list_on_success(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "success",
            "data": {"items": [{"ip": "1.2.3.4", "port_http": 8080}]},
        })

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch.dict("os.environ", {"PROXY_SALE_API_KEY": "test_key"}):
            with patch("aiohttp.ClientSession", return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )):
                result = await _fetch_proxies_from_api()
                assert len(result) == 1
                assert result[0]["ip"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch.dict("os.environ", {"PROXY_SALE_API_KEY": "test_key"}):
            with patch("aiohttp.ClientSession", return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )):
                with pytest.raises(ProxyAPIError, match="status 500"):
                    await _fetch_proxies_from_api()
