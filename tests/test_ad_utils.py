# tests/test_ad_utils.py

import sys
from unittest.mock import patch, MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.ad_utils import (
    process_and_insert_ad,
    process_ad_images,
    insert_ad_images,
    get_ad_images,
)


# ── process_and_insert_ad() ────────────────────────────────────────────────


class TestProcessAndInsertAd:
    @patch("common.services.ad_service.AdService.process_and_insert_ad", return_value=42)
    @patch("common.utils.ad_utils.db_session")
    def test_delegates_to_ad_service(self, mock_session_ctx, mock_proc):
        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = process_and_insert_ad(
            ad_data={"id": 1}, property_type="apartment", geo_id=10009580
        )
        assert result == 42
        mock_proc.assert_called_once_with(
            db=mock_db,
            ad_data={"id": 1},
            property_type="apartment",
            geo_id=10009580,
            extract_phones_sync=True,
        )

    @patch("common.services.ad_service.AdService.process_and_insert_ad")
    @patch("common.utils.ad_utils.db_session")
    def test_passes_extract_phones_sync_flag(self, mock_session_ctx, mock_proc):
        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        process_and_insert_ad(
            ad_data={"id": 1}, property_type="house", geo_id=1, extract_phones_sync=False
        )
        call_kwargs = mock_proc.call_args
        assert call_kwargs.kwargs.get("extract_phones_sync") is False


# ── process_ad_images() ────────────────────────────────────────────────────


class TestProcessAdImages:
    @patch("common.utils.ad_utils._upload_image_to_s3")
    def test_uploads_images_to_s3(self, mock_upload):
        mock_upload.return_value = "https://s3.example.com/img1.webp"

        ad_data = {"images": [{"image_id": "abc123"}]}
        result = process_ad_images(ad_data, "unique_1")

        assert result == ["https://s3.example.com/img1.webp"]
        mock_upload.assert_called_once()

    @patch("common.utils.ad_utils._upload_image_to_s3")
    def test_skips_images_without_image_id(self, mock_upload):
        ad_data = {"images": [{"other_field": "val"}, {"image_id": "ok"}]}
        mock_upload.return_value = "https://s3.example.com/ok.webp"

        result = process_ad_images(ad_data, "unique_1")
        # Only the second image has image_id
        assert len(result) == 1
        mock_upload.assert_called_once()

    @patch("common.utils.ad_utils._upload_image_to_s3")
    def test_returns_uploaded_urls(self, mock_upload):
        mock_upload.side_effect = ["url1", "url2"]
        ad_data = {"images": [{"image_id": "a"}, {"image_id": "b"}]}

        result = process_ad_images(ad_data, "u1")
        assert result == ["url1", "url2"]

    @patch("common.utils.ad_utils._upload_image_to_s3")
    def test_handles_s3_upload_failure(self, mock_upload):
        mock_upload.return_value = None  # upload failed

        ad_data = {"images": [{"image_id": "abc"}]}
        result = process_ad_images(ad_data, "u1")
        assert result == []

    @patch("common.utils.ad_utils._upload_image_to_s3")
    def test_handles_exception_returns_partial_results(self, mock_upload):
        mock_upload.side_effect = ["url1", Exception("boom")]
        ad_data = {"images": [{"image_id": "a"}, {"image_id": "b"}]}

        result = process_ad_images(ad_data, "u1")
        # First image succeeded, exception on second → returns partial
        assert result == ["url1"]


# ── insert_ad_images() ─────────────────────────────────────────────────────


class TestInsertAdImages:
    @patch("common.utils.ad_utils.AdRepository")
    @patch("common.utils.ad_utils.db_session")
    def test_inserts_images(self, mock_session_ctx, mock_repo):
        mock_db = MagicMock()
        mock_db.query.return_value.get.return_value = MagicMock()  # ad exists
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        insert_ad_images(42, ["url1", "url2"])
        assert mock_repo.add_image.call_count == 2

    def test_skips_if_empty_list(self):
        # Should return immediately without DB access
        insert_ad_images(42, [])

    @patch("common.utils.ad_utils.db_session")
    def test_handles_ad_not_found(self, mock_session_ctx):
        mock_db = MagicMock()
        mock_db.query.return_value.get.return_value = None  # ad not found
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        insert_ad_images(42, ["url1"])


# ── get_ad_images() ────────────────────────────────────────────────────────


class TestGetAdImages:
    @patch("common.utils.ad_utils.AdRepository")
    @patch("common.utils.ad_utils.db_session")
    def test_returns_image_urls(self, mock_session_ctx, mock_repo):
        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_ad_images.return_value = ["img1.jpg", "img2.jpg"]

        result = get_ad_images(42)
        assert result == ["img1.jpg", "img2.jpg"]

    @patch("common.utils.ad_utils.AdRepository")
    @patch("common.utils.ad_utils.db_session")
    def test_accepts_dict_with_id_key(self, mock_session_ctx, mock_repo):
        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_ad_images.return_value = ["img.jpg"]

        result = get_ad_images({"id": 42})
        mock_repo.get_ad_images.assert_called_once_with(mock_db, 42)
        assert result == ["img.jpg"]

    def test_returns_empty_list_if_no_ad_id(self):
        result = get_ad_images({"name": "no id"})
        assert result == []

    @patch("common.utils.ad_utils.AdRepository")
    @patch("common.utils.ad_utils.db_session")
    def test_handles_exception_returns_empty_list(self, mock_session_ctx, mock_repo):
        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_ad_images.side_effect = Exception("DB error")

        result = get_ad_images(42)
        assert result == []
