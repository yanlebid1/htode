# tests/test_ad_service.py

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import IntegrityError

from common.services.ad_service import AdService


@pytest.fixture
def mock_db():
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


# ── get_full_ad_data() ───────────────────────────────────────────────────────


class TestGetFullAdData:
    @patch("common.services.ad_service.AdCacheManager")
    @patch("common.services.ad_service.AdRepository")
    def test_cache_hit_returns_cached(self, mock_repo, mock_cache, mock_db):
        mock_cache.get_full_ad_data.return_value = {"id": 1, "price": 5000}
        result = AdService.get_full_ad_data(mock_db, 1)
        assert result == {"id": 1, "price": 5000}
        mock_repo.get_full_ad_data.assert_not_called()

    @patch("common.services.ad_service.AdCacheManager")
    @patch("common.services.ad_service.AdRepository")
    def test_cache_miss_queries_db_and_caches(self, mock_repo, mock_cache, mock_db):
        mock_cache.get_full_ad_data.return_value = None
        mock_repo.get_full_ad_data.return_value = {"id": 2, "price": 7000}
        result = AdService.get_full_ad_data(mock_db, 2)
        assert result == {"id": 2, "price": 7000}
        mock_cache.set_full_ad_data.assert_called_once_with(2, {"id": 2, "price": 7000})

    @patch("common.services.ad_service.AdCacheManager")
    @patch("common.services.ad_service.AdRepository")
    def test_ad_not_found(self, mock_repo, mock_cache, mock_db):
        mock_cache.get_full_ad_data.return_value = None
        mock_repo.get_full_ad_data.return_value = None
        result = AdService.get_full_ad_data(mock_db, 999)
        assert result is None
        mock_cache.set_full_ad_data.assert_not_called()


# ── process_and_insert_ad() ──────────────────────────────────────────────────


class TestProcessAndInsertAd:
    @patch("common.services.ad_service.AdRepository")
    def test_missing_ad_id_returns_none(self, mock_repo, mock_db):
        result = AdService.process_and_insert_ad(
            mock_db, {"no_id_field": True}, "apartment", 10009580
        )
        assert result is None

    @patch("common.services.ad_service.AdRepository")
    def test_successful_insert(self, mock_repo, mock_db):
        mock_repo.get_by_external_id.return_value = None
        mock_ad = MagicMock()
        mock_ad.id = 42
        mock_repo.create_ad.return_value = mock_ad

        with patch("common.utils.ad_utils.process_ad_images", return_value=[]), \
             patch("common.celery_app.celery_app") as mock_celery:
            result = AdService.process_and_insert_ad(
                mock_db,
                {"id": "ext_123", "header": "Test", "price": 5000},
                "apartment",
                10009580,
            )
        assert result == 42

    @patch("common.services.ad_service.AdRepository")
    def test_duplicate_ad_returns_existing_id(self, mock_repo, mock_db):
        """IntegrityError on insert → fetch existing."""
        mock_repo.get_by_external_id.side_effect = [None, MagicMock(id=7)]
        mock_repo.create_ad.side_effect = IntegrityError(
            "duplicate", params=None, orig=Exception()
        )

        with patch("common.utils.ad_utils.process_ad_images", return_value=[]), \
             patch("common.celery_app.celery_app"):
            result = AdService.process_and_insert_ad(
                mock_db,
                {"id": "dup_456", "header": "Dup"},
                "apartment",
                10009580,
            )
        assert result == 7

    @patch("common.services.ad_service.AdRepository")
    def test_images_processed_and_inserted(self, mock_repo, mock_db):
        mock_repo.get_by_external_id.return_value = None
        mock_ad = MagicMock()
        mock_ad.id = 10
        mock_repo.create_ad.return_value = mock_ad

        with patch(
            "common.utils.ad_utils.process_ad_images",
            return_value=["https://img1.jpg", "https://img2.jpg"],
        ), patch("common.celery_app.celery_app"):
            AdService.process_and_insert_ad(
                mock_db,
                {"id": "img_789", "header": "Images"},
                "apartment",
                10009580,
            )
        assert mock_repo.add_image.call_count == 2

    @patch("common.services.ad_service.AdRepository")
    def test_async_phone_extraction_scheduled(self, mock_repo, mock_db):
        mock_repo.get_by_external_id.return_value = None
        mock_ad = MagicMock()
        mock_ad.id = 15
        mock_repo.create_ad.return_value = mock_ad

        with patch("common.utils.ad_utils.process_ad_images", return_value=[]), \
             patch("common.celery_app.celery_app") as mock_celery:
            AdService.process_and_insert_ad(
                mock_db,
                {"id": "phone_001", "header": "Phone"},
                "apartment",
                10009580,
            )
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "common.tasks.extract_phones_for_ad"


# ── is_ad_inactive() ─────────────────────────────────────────────────────────


class TestIsAdInactive:
    @patch("common.services.ad_service.make_request")
    def test_404_returns_true(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        assert AdService.is_ad_inactive("https://example.com/ad/1") is True

    @patch("common.services.ad_service.make_request")
    def test_200_returns_false(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        assert AdService.is_ad_inactive("https://example.com/ad/2") is False

    @patch("common.services.ad_service.make_request")
    def test_no_response_returns_true(self, mock_request):
        mock_request.return_value = None
        assert AdService.is_ad_inactive("https://example.com/ad/3") is True

    @patch("common.services.ad_service.make_request")
    def test_exception_returns_true(self, mock_request):
        mock_request.side_effect = ConnectionError("timeout")
        assert AdService.is_ad_inactive("https://example.com/ad/4") is True


# ── clear_ad_cache() ─────────────────────────────────────────────────────────


class TestClearAdCache:
    @patch("common.services.ad_service.AdCacheManager")
    def test_invalidates_cache_keys(self, mock_cache):
        mock_cache.invalidate_all.return_value = 3
        AdService.clear_ad_cache(42, "https://example.com/ad/42")
        mock_cache.invalidate_all.assert_called_once_with(42, "https://example.com/ad/42")
