# tests/test_s3_utils.py

import sys
from unittest.mock import patch, MagicMock
from io import BytesIO

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from botocore.exceptions import ClientError


# ── detect_content_type() ────────────────────────────────────────────────

# Import after mocks are in place
from common.utils.s3_utils import (
    detect_content_type,
    delete_s3_image,
    delete_s3_image_batch,
    _upload_image_to_s3,
)


class TestDetectContentType:
    def test_returns_jpeg_for_jpg(self):
        result = detect_content_type("https://example.com/photo.jpg", "jpg")
        assert result == "image/jpeg"

    def test_returns_png_for_png(self):
        result = detect_content_type("https://example.com/photo.png", "png")
        assert result == "image/png"

    def test_returns_webp_for_webp(self):
        result = detect_content_type("https://example.com/photo.webp", "webp")
        assert result == "image/webp"

    def test_returns_gif_for_gif(self):
        result = detect_content_type("https://example.com/photo.gif", "gif")
        assert result == "image/gif"

    def test_falls_back_to_jpeg_for_unknown(self):
        # Use an extension that mimetypes doesn't recognise
        result = detect_content_type("https://example.com/photo.qzx", "qzx")
        assert result == "image/jpeg"

    def test_handles_url_with_query_params(self):
        result = detect_content_type(
            "https://example.com/photo.png?w=800&h=600", "png"
        )
        assert result == "image/png"


# ── delete_s3_image() ───────────────────────────────────────────────────


class TestDeleteS3Image:
    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "cloudfront_domain": "https://d123.cloudfront.net",
        "s3_bucket": "test-bucket",
    })
    def test_extracts_key_from_cloudfront_url_and_deletes(self, mock_s3):
        url = "https://d123.cloudfront.net/images/ad_123_photo.jpg"
        result = delete_s3_image(url)
        assert result is True
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="images/ad_123_photo.jpg"
        )

    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "cloudfront_domain": "https://d123.cloudfront.net",
        "s3_bucket": "test-bucket",
    })
    def test_returns_true_on_success(self, mock_s3):
        url = "https://d123.cloudfront.net/images/photo.jpg"
        assert delete_s3_image(url) is True

    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "cloudfront_domain": "https://d123.cloudfront.net",
        "s3_bucket": "test-bucket",
    })
    def test_returns_false_on_client_error(self, mock_s3):
        mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "DeleteObject",
        )
        url = "https://d123.cloudfront.net/images/photo.jpg"
        assert delete_s3_image(url) is False

    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "cloudfront_domain": "https://d123.cloudfront.net",
        "s3_bucket": "test-bucket",
    })
    def test_returns_false_for_non_matching_url(self, mock_s3):
        url = "https://other-cdn.com/images/photo.jpg"
        assert delete_s3_image(url) is False
        mock_s3.delete_object.assert_not_called()

    def test_returns_false_for_empty_url(self):
        assert delete_s3_image("") is False


# ── delete_s3_image_batch() ─────────────────────────────────────────────


class TestDeleteS3ImageBatch:
    def test_returns_empty_dict_for_empty_input(self):
        result = delete_s3_image_batch([])
        assert result == {}

    @patch("common.utils.s3_utils.delete_s3_image")
    def test_deletes_multiple_images_returns_results(self, mock_delete):
        mock_delete.side_effect = [True, True, True]
        urls = [
            "https://cdn.example.com/a.jpg",
            "https://cdn.example.com/b.jpg",
            "https://cdn.example.com/c.jpg",
        ]
        result = delete_s3_image_batch(urls)
        assert len(result) == 3
        assert all(v is True for v in result.values())

    @patch("common.utils.s3_utils.delete_s3_image")
    def test_handles_mixed_success_failure(self, mock_delete):
        mock_delete.side_effect = [True, False, True]
        urls = ["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg", "https://cdn.example.com/c.jpg"]
        result = delete_s3_image_batch(urls)
        assert result[urls[0]] is True
        assert result[urls[1]] is False
        assert result[urls[2]] is True


# ── _upload_image_to_s3() ──────────────────────────────────────────────


class TestUploadImageToS3:
    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.make_request")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "s3_bucket": "test-bucket",
        "s3_prefix": "images/",
        "cloudfront_domain": "https://d123.cloudfront.net",
        "access_key": "test",
        "secret_key": "test",
        "region": "us-east-1",
    })
    def test_downloads_and_uploads_returns_cloudfront_url(self, mock_request, mock_s3):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\xff\xd8\xff\xe0fake-jpeg-data"
        mock_request.return_value = mock_response

        result = _upload_image_to_s3(
            "https://example.com/photo.jpg", "ad_123"
        )
        assert result is not None
        assert "d123.cloudfront.net" in result
        mock_s3.put_object.assert_called_once()

    @patch("common.utils.s3_utils.make_request")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "s3_bucket": "test-bucket",
        "s3_prefix": "images/",
        "cloudfront_domain": "https://d123.cloudfront.net",
        "access_key": "test",
        "secret_key": "test",
        "region": "us-east-1",
    })
    def test_returns_none_on_download_failure(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response

        result = _upload_image_to_s3(
            "https://example.com/missing.jpg", "ad_123"
        )
        assert result is None

    @patch("common.utils.s3_utils.make_request")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "s3_bucket": "test-bucket",
        "s3_prefix": "images/",
        "cloudfront_domain": "https://d123.cloudfront.net",
        "access_key": "test",
        "secret_key": "test",
        "region": "us-east-1",
    })
    def test_returns_none_when_no_response(self, mock_request):
        mock_request.return_value = None
        result = _upload_image_to_s3(
            "https://example.com/photo.jpg", "ad_123"
        )
        assert result is None

    def test_returns_none_for_empty_image_url(self):
        result = _upload_image_to_s3("", "ad_123")
        assert result is None

    def test_returns_none_for_empty_ad_unique_id(self):
        result = _upload_image_to_s3("https://example.com/photo.jpg", "")
        assert result is None

    @patch("common.utils.s3_utils.time.sleep")
    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.make_request")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "s3_bucket": "test-bucket",
        "s3_prefix": "images/",
        "cloudfront_domain": "https://d123.cloudfront.net",
        "access_key": "test",
        "secret_key": "test",
        "region": "us-east-1",
    })
    def test_retries_on_s3_upload_failure(self, mock_request, mock_s3, mock_sleep):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\xff\xd8\xff\xe0fake-jpeg-data"
        mock_request.return_value = mock_response

        # First attempt fails, second succeeds
        mock_s3.put_object.side_effect = [
            ClientError(
                {"Error": {"Code": "InternalError", "Message": "retry"}},
                "PutObject",
            ),
            None,  # success
        ]

        result = _upload_image_to_s3(
            "https://example.com/photo.jpg", "ad_123", max_retries=2
        )
        assert result is not None
        assert mock_s3.put_object.call_count == 2

    @patch("common.utils.s3_utils.Image")
    @patch("common.utils.s3_utils.s3_client")
    @patch("common.utils.s3_utils.make_request")
    @patch("common.utils.s3_utils.AWS_CONFIG", {
        "s3_bucket": "test-bucket",
        "s3_prefix": "images/",
        "cloudfront_domain": "https://d123.cloudfront.net",
        "access_key": "test",
        "secret_key": "test",
        "region": "us-east-1",
    })
    def test_converts_webp_to_jpeg(self, mock_request, mock_s3, mock_image):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"RIFF\x00\x00webp-data"
        mock_request.return_value = mock_response

        # Mock PIL Image conversion
        mock_img = MagicMock()
        mock_image.open.return_value.convert.return_value = mock_img
        jpeg_buffer = BytesIO(b"\xff\xd8\xff\xe0converted-jpeg")
        mock_img.save = MagicMock(side_effect=lambda buf, **kw: buf.write(b"\xff\xd8jpeg"))

        result = _upload_image_to_s3(
            "https://example.com/photo.webp", "ad_123"
        )
        # Should have attempted the conversion
        mock_image.open.assert_called_once()
