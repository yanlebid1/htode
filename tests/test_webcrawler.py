# tests/test_webcrawler.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from services.webcrawler_service.app.main import (
    app,
    _is_private_ip,
    validate_url,
)

client = TestClient(app)


class TestIsPrivateIp:
    """Tests for the _is_private_ip() SSRF helper."""

    def test_loopback(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_private_10_range(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_192_range(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_private_172_range(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_hostname_not_ip(self):
        """DNS hostnames are not treated as private IPs."""
        assert _is_private_ip("example.com") is False

    def test_link_local(self):
        assert _is_private_ip("169.254.169.254") is True


class TestValidateUrl:
    """Tests for the validate_url() SSRF protection."""

    def test_valid_https(self):
        result = validate_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_valid_http(self):
        result = validate_url("http://example.com/page")
        assert result == "http://example.com/page"

    def test_blocked_scheme_ftp(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_url("ftp://example.com/file")

    def test_blocked_scheme_file(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_url("file:///etc/passwd")

    def test_blocked_host_localhost(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_url("http://localhost/admin")

    def test_blocked_host_127(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_url("http://127.0.0.1/admin")

    def test_blocked_metadata_endpoint(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_private_ip_10_range(self):
        with pytest.raises(ValueError, match="private"):
            validate_url("http://10.0.0.1/internal")

    def test_private_ip_192_range(self):
        with pytest.raises(ValueError, match="private"):
            validate_url("http://192.168.1.1/internal")

    def test_empty_hostname(self):
        with pytest.raises(ValueError):
            validate_url("http:///path")


class TestWebcrawlerEndpoints:
    """Tests for the webcrawler FastAPI endpoints."""

    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "webcrawler"

    def test_crawl_with_invalid_url(self):
        """Test that SSRF-blocked URLs are rejected with 422."""
        response = client.post("/crawl", json={"url": "http://localhost/secret"})
        assert response.status_code == 422  # Pydantic validation error

    def test_crawl_with_blocked_scheme(self):
        """Test that blocked schemes are rejected."""
        response = client.post("/crawl", json={"url": "ftp://example.com/file"})
        assert response.status_code == 422

    @patch(
        "services.webcrawler_service.app.main.fetch_with_aiohttp",
        new_callable=AsyncMock,
    )
    def test_crawl_success(self, mock_fetch):
        """Test a successful crawl request."""
        mock_fetch.return_value = ("<html>OK</html>", 200, "https://example.com")

        response = client.post(
            "/crawl",
            json={"url": "https://example.com", "method": "aiohttp"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["content"] == "<html>OK</html>"
        assert data["status_code"] == 200
