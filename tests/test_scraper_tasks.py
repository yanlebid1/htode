# tests/test_scraper_tasks.py

import sys
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Pre-mock heavy imports before importing scraper tasks
# adspower_manager imports selenium at module level
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest


# ── acquire_lock() ──────────────────────────────────────────────────────────


class TestAcquireLock:
    @patch("services.scraper_service.app.tasks.redis_client")
    def test_acquires_lock_returns_lock_id(self, mock_redis):
        from services.scraper_service.app.tasks import acquire_lock

        mock_redis.set.return_value = True

        result = acquire_lock("test_lock", expire_time=60)
        assert result is not None  # Returns UUID lock_id
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("nx") is True

    @patch("services.scraper_service.app.tasks.redis_client")
    def test_returns_none_if_already_locked(self, mock_redis):
        from services.scraper_service.app.tasks import acquire_lock

        mock_redis.set.return_value = False

        result = acquire_lock("test_lock")
        assert result is None

    @patch("services.scraper_service.app.tasks.redis_client")
    def test_error_returns_none(self, mock_redis):
        from services.scraper_service.app.tasks import acquire_lock

        mock_redis.set.side_effect = Exception("Redis down")

        result = acquire_lock("test_lock")
        assert result is None


# ── release_lock() ──────────────────────────────────────────────────────────


class TestReleaseLock:
    @patch("services.scraper_service.app.tasks.redis_client")
    def test_releases_lock_returns_true(self, mock_redis):
        from services.scraper_service.app.tasks import release_lock

        mock_redis.eval.return_value = 1

        result = release_lock("test_lock", "lock-uuid-123")
        assert result is True

    @patch("services.scraper_service.app.tasks.redis_client")
    def test_not_owner_returns_false(self, mock_redis):
        from services.scraper_service.app.tasks import release_lock

        mock_redis.eval.return_value = 0

        result = release_lock("test_lock", "wrong-uuid")
        assert result is False

    @patch("services.scraper_service.app.tasks.redis_client")
    def test_error_returns_false(self, mock_redis):
        from services.scraper_service.app.tasks import release_lock

        mock_redis.eval.side_effect = Exception("Redis down")

        result = release_lock("test_lock", "lock-uuid-123")
        assert result is False


# ── redis_lock() context manager ────────────────────────────────────────────


class TestRedisLock:
    @patch("services.scraper_service.app.tasks.redis_client")
    def test_acquires_and_yields(self, mock_redis):
        from services.scraper_service.app.tasks import redis_lock

        mock_redis.set.return_value = True
        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = (b"some-uuid", 1)
        mock_redis.pipeline.return_value = mock_pipeline

        with redis_lock("test_lock") as (acquired, lock_id):
            assert acquired is True
            assert lock_id is not None

    @patch("services.scraper_service.app.tasks.redis_client")
    def test_not_acquired_yields_false(self, mock_redis):
        from services.scraper_service.app.tasks import redis_lock

        mock_redis.set.return_value = False

        with redis_lock("test_lock") as (acquired, lock_id):
            assert acquired is False


# ── parse_date() ────────────────────────────────────────────────────────────


class TestParseDate:
    def test_parses_iso_date(self):
        from services.scraper_service.app.tasks import parse_date

        result = parse_date("2024-06-15T10:30:00+00:00")
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15
        assert result.tzinfo == timezone.utc

    def test_invalid_date_raises_value_error(self):
        from services.scraper_service.app.tasks import parse_date

        with pytest.raises(ValueError):
            parse_date("not-a-date")

    def test_parses_utc_datetime(self):
        from services.scraper_service.app.tasks import parse_date

        result = parse_date("2025-01-01T00:00:00+00:00")
        assert result == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ── is_initial_load_done() ──────────────────────────────────────────────────


class TestIsInitialLoadDone:
    @patch("services.scraper_service.app.tasks.db_session")
    def test_returns_true_when_ads_exist(self, mock_db_session):
        from services.scraper_service.app.tasks import is_initial_load_done

        mock_db = MagicMock()
        mock_db.query.return_value.scalar.return_value = 100
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = is_initial_load_done()
        assert result is True

    @patch("services.scraper_service.app.tasks.db_session")
    def test_returns_false_when_no_ads(self, mock_db_session):
        from services.scraper_service.app.tasks import is_initial_load_done

        mock_db = MagicMock()
        mock_db.query.return_value.scalar.return_value = 0
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = is_initial_load_done()
        assert result is False

    @patch("services.scraper_service.app.tasks.db_session")
    def test_error_returns_false(self, mock_db_session):
        from services.scraper_service.app.tasks import is_initial_load_done

        mock_db_session.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB down")
        )
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = is_initial_load_done()
        assert result is False


# ── insert_ad() ─────────────────────────────────────────────────────────────


class TestInsertAd:
    @patch("services.scraper_service.app.tasks.process_and_insert_ad")
    def test_delegates_to_process_and_insert(self, mock_insert):
        from services.scraper_service.app.tasks import insert_ad

        mock_insert.return_value = 42
        result = insert_ad({"id": "test123"}, "apartment", 10009580)
        assert result == 42
        mock_insert.assert_called_once_with({"id": "test123"}, "apartment", 10009580)

    @patch("services.scraper_service.app.tasks.process_and_insert_ad")
    def test_missing_id_returns_none(self, mock_insert):
        from services.scraper_service.app.tasks import insert_ad

        result = insert_ad({}, "apartment", 10009580)
        assert result is None

    @patch("services.scraper_service.app.tasks.process_and_insert_ad")
    def test_exception_returns_none(self, mock_insert):
        from services.scraper_service.app.tasks import insert_ad

        mock_insert.side_effect = Exception("DB error")
        result = insert_ad({"id": "test"}, "apartment", 10009580)
        assert result is None


# ── handle_new_records() ────────────────────────────────────────────────────


class TestHandleNewRecords:
    @patch("services.scraper_service.app.tasks.celery_app")
    @patch("services.scraper_service.app.tasks.AdRepository")
    @patch("services.scraper_service.app.tasks.db_session")
    def test_dispatches_to_notifier(self, mock_db_session, mock_repo, mock_celery):
        from services.scraper_service.app.tasks import handle_new_records

        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_repo.get_full_ad_data.return_value = {"id": 1, "price": 5000}

        handle_new_records([1])

        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "notifier_service.app.tasks.sort_and_notify_new_ads"

    @patch("services.scraper_service.app.tasks.celery_app")
    @patch("services.scraper_service.app.tasks.db_session")
    def test_empty_list_returns_early(self, mock_db_session, mock_celery):
        from services.scraper_service.app.tasks import handle_new_records

        handle_new_records([])
        mock_celery.send_task.assert_not_called()


# ── extract_phone_adspower() ────────────────────────────────────────────────


class TestExtractPhoneAdspower:
    @patch("services.scraper_service.app.tasks.adspower_manager")
    def test_success_returns_result_dict(self, mock_adspower):
        from services.scraper_service.app.tasks import extract_phone_adspower

        mock_adspower.extract_phone_with_rotation.return_value = "+380501234567"
        mock_adspower.get_stats.return_value = {"total": 100, "success": 90}

        result = extract_phone_adspower("https://olx.ua/ad/123")
        assert result["success"] is True
        assert result["phone"] == "+380501234567"
        assert result["method"] == "adspower"

    @patch("services.scraper_service.app.tasks.adspower_manager")
    def test_failure_returns_failure_dict(self, mock_adspower):
        from services.scraper_service.app.tasks import extract_phone_adspower

        mock_adspower.extract_phone_with_rotation.return_value = None
        mock_adspower.get_stats.return_value = {"total": 100, "success": 89}

        result = extract_phone_adspower("https://olx.ua/ad/123")
        assert result["success"] is False
        assert result["phone"] is None

    @patch("services.scraper_service.app.tasks.adspower_manager")
    def test_exception_returns_error_dict(self, mock_adspower):
        from services.scraper_service.app.tasks import extract_phone_adspower

        mock_adspower.extract_phone_with_rotation.side_effect = Exception("Browser crash")

        result = extract_phone_adspower("https://olx.ua/ad/123")
        assert result["success"] is False
        assert "Browser crash" in result["error"]
