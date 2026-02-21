# tests/test_http_client.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.phone_utils.http_client import (
    AsyncHTTPClient,
    _random_ua,
    USER_AGENTS,
)


# ── _random_ua() ────────────────────────────────────────────────────────


class TestRandomUa:
    def test_returns_string(self):
        ua = _random_ua()
        assert isinstance(ua, str)
        assert len(ua) > 0

    @patch("common.utils.phone_utils.http_client._UA_GEN", None)
    def test_falls_back_to_builtin_list(self):
        ua = _random_ua()
        assert ua in USER_AGENTS


# ── AsyncHTTPClient initialization ──────────────────────────────────────


class TestAsyncHTTPClientInit:
    def test_init_without_proxy(self):
        client = AsyncHTTPClient()
        assert client.proxy is None
        assert client.proxy_dict is None

    def test_init_with_proxy(self):
        client = AsyncHTTPClient(proxy="http://user:pass@1.2.3.4:8080")
        assert client.proxy == "http://user:pass@1.2.3.4:8080"
        assert client.proxy_dict is not None
        assert "http" in client.proxy_dict

    def test_parse_proxy_returns_dict(self):
        client = AsyncHTTPClient()
        result = client._parse_proxy("http://user:pass@1.2.3.4:8080")
        assert result == {
            "http": "http://user:pass@1.2.3.4:8080",
            "https": "http://user:pass@1.2.3.4:8080",
        }

    def test_get_random_headers_has_user_agent(self):
        client = AsyncHTTPClient()
        headers = client._get_random_headers()
        assert "User-Agent" in headers
        assert "Accept" in headers


# ── fetch_with_aiohttp() ────────────────────────────────────────────────


class TestFetchWithAiohttp:
    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        client = AsyncHTTPClient()

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value="<html>content</html>")

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch.object(client, "_get_aiohttp_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.fetch_with_aiohttp("https://example.com")
            assert result == "<html>content</html>"

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        client = AsyncHTTPClient()

        with patch.object(client, "_get_aiohttp_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("connection failed")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.fetch_with_aiohttp("https://example.com")
            assert result is None


# ── fetch_with_httpx() ──────────────────────────────────────────────────


class TestFetchWithHttpx:
    @pytest.mark.asyncio
    @patch("common.utils.phone_utils.http_client.httpx.AsyncClient")
    async def test_returns_text_on_success(self, mock_httpx_cls):
        client = AsyncHTTPClient()

        mock_response = MagicMock()
        mock_response.text = "<html>httpx content</html>"
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_response)
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.fetch_with_httpx("https://example.com")
        assert result == "<html>httpx content</html>"

    @pytest.mark.asyncio
    @patch("common.utils.phone_utils.http_client.httpx.AsyncClient")
    async def test_returns_none_on_error(self, mock_httpx_cls):
        client = AsyncHTTPClient()
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("httpx error")
        )
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.fetch_with_httpx("https://example.com")
        assert result is None


# ── fetch() — cascading fallback ────────────────────────────────────────


class TestFetch:
    @pytest.mark.asyncio
    async def test_returns_first_successful_method(self):
        client = AsyncHTTPClient()
        client.fetch_with_aiohttp = AsyncMock(return_value="<html>aiohttp</html>")
        client.fetch_with_curl_cffi = AsyncMock(return_value=None)

        result = await client.fetch("https://example.com")
        assert result == "<html>aiohttp</html>"
        # curl_cffi should not be called since aiohttp succeeded
        client.fetch_with_curl_cffi.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_when_first_fails(self):
        client = AsyncHTTPClient()
        client.fetch_with_aiohttp = AsyncMock(return_value=None)
        client.fetch_with_curl_cffi = AsyncMock(return_value="<html>curl</html>")

        result = await client.fetch("https://example.com")
        assert result == "<html>curl</html>"

    @pytest.mark.asyncio
    async def test_raises_when_all_methods_fail(self):
        client = AsyncHTTPClient()
        client.fetch_with_aiohttp = AsyncMock(return_value=None)
        client.fetch_with_curl_cffi = AsyncMock(return_value=None)
        client.fetch_with_httpx = AsyncMock(return_value=None)
        client._fetch_with_camoufox = AsyncMock(return_value=None)

        with pytest.raises(Exception, match="Failed to fetch"):
            await client.fetch("https://example.com")
