# tests/test_request_utils.py

import pytest
from unittest.mock import patch, MagicMock, mock_open
import requests


# ── get_retry_session() ──────────────────────────────────────────────────────


class TestGetRetrySession:
    @patch("common.utils.unified_request_utils.requests.Session")
    def test_returns_session_with_retry_adapter(self, mock_session_cls):
        from common.utils.unified_request_utils import get_retry_session

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        session = get_retry_session()
        assert session is mock_session
        assert mock_session.mount.call_count == 2
        # Should mount on both http:// and https://
        mount_calls = [call[0][0] for call in mock_session.mount.call_args_list]
        assert "http://" in mount_calls
        assert "https://" in mount_calls

    def test_custom_retry_params(self):
        from common.utils.unified_request_utils import get_retry_session

        session = get_retry_session(retries=5, backoff_factor=1.0)
        # Session should be usable
        assert isinstance(session, requests.Session)

    def test_uses_provided_session(self):
        from common.utils.unified_request_utils import get_retry_session

        existing_session = requests.Session()
        session = get_retry_session(session=existing_session)
        assert session is existing_session


# ── make_request() ───────────────────────────────────────────────────────────


class TestMakeRequest:
    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_get_success(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.1
        mock_session.get.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = make_request("https://example.com", method="get")
        assert result is mock_response
        mock_session.get.assert_called_once()

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_post_success(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.1
        mock_session.post.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = make_request("https://example.com", method="post", json={"key": "val"})
        assert result is mock_response
        mock_session.post.assert_called_once()

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_unsupported_method_raises_value_error(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_get_session.return_value = MagicMock()

        with pytest.raises(ValueError, match="Unsupported HTTP method"):
            make_request("https://example.com", method="patch")

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_timeout_returns_none_when_not_raising(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.Timeout("timed out")
        mock_get_session.return_value = mock_session

        result = make_request("https://example.com", raise_for_status=False)
        assert result is None

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_connection_error_returns_none_when_not_raising(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.ConnectionError("refused")
        mock_get_session.return_value = mock_session

        result = make_request("https://example.com", raise_for_status=False)
        assert result is None

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_http_error_reraises_when_raise_for_status(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_session.get.return_value = mock_response
        mock_get_session.return_value = mock_session

        with pytest.raises(requests.exceptions.HTTPError):
            make_request("https://example.com", raise_for_status=True)

    @patch("common.utils.unified_request_utils.get_retry_session")
    def test_http_error_returns_none_when_not_raising(self, mock_get_session):
        from common.utils.unified_request_utils import make_request

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get_session.return_value = mock_session

        result = make_request("https://example.com", raise_for_status=False)
        assert result is None


# ── fetch_ads_flatfy() ───────────────────────────────────────────────────────


class TestFetchAdsFlatfy:
    @patch("common.utils.unified_request_utils.make_request")
    def test_success_returns_data_list(self, mock_req):
        from common.utils.unified_request_utils import fetch_ads_flatfy

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": 1}, {"id": 2}]}
        mock_req.return_value = mock_response

        result = fetch_ads_flatfy(geo_id=10009580)
        assert result == [{"id": 1}, {"id": 2}]

    @patch("common.utils.unified_request_utils.make_request")
    def test_api_error_returns_empty_list(self, mock_req):
        from common.utils.unified_request_utils import fetch_ads_flatfy

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_req.return_value = mock_response

        result = fetch_ads_flatfy(geo_id=10009580)
        assert result == []

    @patch("common.utils.unified_request_utils.make_request")
    def test_passes_room_count_and_price_params(self, mock_req):
        from common.utils.unified_request_utils import fetch_ads_flatfy

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_req.return_value = mock_response

        fetch_ads_flatfy(geo_id=1, room_count="2", price_min=1000, price_max=5000)

        call_kwargs = mock_req.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["room_count"] == "2"
        assert params["price_min"] == "1000"
        assert params["price_max"] == "5000"

    @patch("common.utils.unified_request_utils.make_request")
    def test_exception_returns_empty_list(self, mock_req):
        from common.utils.unified_request_utils import fetch_ads_flatfy

        mock_req.side_effect = Exception("network error")

        result = fetch_ads_flatfy(geo_id=10009580)
        assert result == []


# ── get_json() ───────────────────────────────────────────────────────────────


class TestGetJson:
    @patch("common.utils.unified_request_utils.make_request")
    def test_success_returns_parsed_json(self, mock_req):
        from common.utils.unified_request_utils import get_json

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        mock_req.return_value = mock_response

        result = get_json("https://example.com/api")
        assert result == {"key": "value"}

    @patch("common.utils.unified_request_utils.make_request")
    def test_non_200_returns_none(self, mock_req):
        from common.utils.unified_request_utils import get_json

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_req.return_value = mock_response

        result = get_json("https://example.com/api")
        assert result is None

    @patch("common.utils.unified_request_utils.make_request")
    def test_invalid_json_returns_none(self, mock_req):
        from common.utils.unified_request_utils import get_json

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("not JSON")
        mock_req.return_value = mock_response

        result = get_json("https://example.com/api")
        assert result is None


# ── post_json() ──────────────────────────────────────────────────────────────


class TestPostJson:
    @patch("common.utils.unified_request_utils.make_request")
    def test_success_returns_json(self, mock_req):
        from common.utils.unified_request_utils import post_json

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_req.return_value = mock_response

        result = post_json("https://example.com/api", data={"key": "val"})
        assert result == {"result": "ok"}

    @patch("common.utils.unified_request_utils.make_request")
    def test_non_200_returns_none(self, mock_req):
        from common.utils.unified_request_utils import post_json

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_req.return_value = mock_response

        result = post_json("https://example.com/api", data={"key": "val"})
        assert result is None


# ── download_file() ──────────────────────────────────────────────────────────


class TestDownloadFile:
    @patch("builtins.open", new_callable=mock_open)
    @patch("common.utils.unified_request_utils.make_request")
    def test_success_writes_to_file(self, mock_req, mock_file):
        from common.utils.unified_request_utils import download_file

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_response.headers = {"content-length": "12"}
        mock_req.return_value = mock_response

        result = download_file("https://example.com/file.zip", "/tmp/file.zip")
        assert result is True
        mock_file.assert_called_once_with("/tmp/file.zip", "wb")

    @patch("common.utils.unified_request_utils.make_request")
    def test_failed_request_returns_false(self, mock_req):
        from common.utils.unified_request_utils import download_file

        mock_req.return_value = None

        result = download_file("https://example.com/file.zip", "/tmp/file.zip")
        assert result is False
