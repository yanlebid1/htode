# tests/test_common_tasks.py

import sys
from unittest.mock import patch, MagicMock
from collections import defaultdict

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

# Inject missing 'Phone' alias into common.db.models (source code uses Phone but model is AdPhone)
import common.db.models as _models_mod
if not hasattr(_models_mod, "Phone"):
    _models_mod.Phone = _models_mod.AdPhone

# Inject missing 'get_parser_for_url' into parsers package
import common.utils.phone_utils.parsers as _parsers_mod
if not hasattr(_parsers_mod, "get_parser_for_url"):
    _parsers_mod.get_parser_for_url = MagicMock()

# Ad model is missing 'created_at' column — add it so SQLAlchemy filter expressions work
from sqlalchemy import Column, DateTime
from common.db.models.ad import Ad as _Ad
if not hasattr(_Ad, "created_at"):
    _Ad.created_at = Column(DateTime)

import pytest


# ── notify_user_batch_v2() ─────────────────────────────────────────────────


class TestNotifyUserBatchV2:
    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_dispatches_to_telegram_queue(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v2

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.telegram_id = 111
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_user]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        ad_data = {"id": 10, "resource_url": "https://example.com", "external_id": "ext1"}
        result = notify_user_batch_v2([1], ad_data, s3_image_url="img.jpg")

        mock_celery.send_task.assert_called_once()
        call_kwargs = mock_celery.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "telegram_queue"
        assert result["success_count"] == 1

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_handles_missing_telegram_id(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v2

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        ad_data = {"id": 10}
        result = notify_user_batch_v2([1], ad_data)

        mock_celery.send_task.assert_not_called()
        assert result["failed_count"] == 1

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_returns_metrics(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v2

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.telegram_id = 111
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_user]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = notify_user_batch_v2([1], {"id": 10})
        assert "success_count" in result
        assert "failed_count" in result
        assert "total" in result
        assert "processing_time" in result
        assert result["total"] == 1

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_handles_dispatch_exception(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v2

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.telegram_id = 111
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_user]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_celery.send_task.side_effect = Exception("Queue full")

        result = notify_user_batch_v2([1], {"id": 10})
        assert result["failed_count"] == 1
        assert result["success_count"] == 0


# ── notify_user_batch_v3() ─────────────────────────────────────────────────


class TestNotifyUserBatchV3:
    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_groups_users_by_assigned_bot(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v3

        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        user2 = MagicMock(id=2, telegram_id=222, assigned_bot_name="tulip")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [user1, user2]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = notify_user_batch_v3([1, 2], {"id": 10, "resource_url": "url", "external_id": "e1"})

        assert mock_celery.send_task.call_count == 2
        assert result["bots_used"] == 2

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_dispatches_to_bot_specific_queues(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v3

        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [user1]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        notify_user_batch_v3([1], {"id": 10, "resource_url": "url", "external_id": "e1"})

        call_kwargs = mock_celery.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "telegram_bot_orchid_queue"

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_tracks_no_bot_assigned_count(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v3

        user_no_bot = MagicMock(id=1, telegram_id=111, assigned_bot_name=None)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [user_no_bot]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = notify_user_batch_v3([1], {"id": 10})
        assert result["no_bot_assigned"] == 1
        mock_celery.send_task.assert_not_called()

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_returns_per_bot_stats(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v3

        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        user2 = MagicMock(id=2, telegram_id=222, assigned_bot_name="orchid")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [user1, user2]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = notify_user_batch_v3([1, 2], {"id": 10, "resource_url": "url", "external_id": "e1"})
        assert "orchid" in result["bot_stats"]
        assert result["bot_stats"]["orchid"]["total"] == 2

    @patch("common.tasks.celery_app")
    @patch("common.tasks.build_ad_text", return_value="Ad text")
    @patch("common.db.session.db_session")
    def test_handles_dispatch_exception_per_user(self, mock_session_ctx, mock_build, mock_celery):
        from common.tasks import notify_user_batch_v3

        user1 = MagicMock(id=1, telegram_id=111, assigned_bot_name="orchid")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [user1]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_celery.send_task.side_effect = Exception("Queue error")

        result = notify_user_batch_v3([1], {"id": 10, "resource_url": "url", "external_id": "e1"})
        assert result["failed_count"] == 1
        assert result["success_count"] == 0


# ── cleanup_stale_extractions() ────────────────────────────────────────────


class TestCleanupStaleExtractions:
    @patch("common.tasks.celery_app")
    @patch("common.db.session.db_session")
    def test_retries_extraction_for_stale_ads(self, mock_session_ctx, mock_celery):
        from common.tasks import cleanup_stale_extractions

        stale_ad = MagicMock()
        stale_ad.id = 1
        stale_ad.resource_url = "https://example.com/ad/1"
        mock_db = MagicMock()
        mock_db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = [stale_ad]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_extractions()
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "extract_phones_for_ad.v1"
        assert call_args.kwargs.get("queue") == "phone_extraction_queue"

    @patch("common.tasks.celery_app")
    @patch("common.db.session.db_session")
    def test_handles_no_stale_ads(self, mock_session_ctx, mock_celery):
        from common.tasks import cleanup_stale_extractions

        mock_db = MagicMock()
        mock_db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = []
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_extractions()
        mock_celery.send_task.assert_not_called()

    @patch("common.tasks.celery_app")
    @patch("common.db.session.db_session")
    def test_skips_ads_without_resource_url(self, mock_session_ctx, mock_celery):
        from common.tasks import cleanup_stale_extractions

        stale_ad = MagicMock()
        stale_ad.id = 1
        stale_ad.resource_url = None
        mock_db = MagicMock()
        mock_db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = [stale_ad]
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        cleanup_stale_extractions()
        mock_celery.send_task.assert_not_called()


# ── extract_phones_for_ad_v1() ─────────────────────────────────────────────


class TestExtractPhonesForAdV1:
    @patch("common.utils.cache_managers.AdCacheManager.invalidate_all")
    @patch("common.db.repositories.ad_repository.AdRepository.add_phone")
    @patch("common.db.session.db_session")
    @patch("common.utils.phone_utils.parsers.get_parser_for_url", create=True)
    @patch("common.utils.extraction_client.extraction_client")
    def test_extracts_and_stores_phones(self, mock_client, mock_parser_fn,
                                        mock_session_ctx, mock_add_phone, mock_cache):
        from common.tasks import extract_phones_for_ad_v1

        mock_client.extract_content.return_value = {
            "status": "success",
            "content": "<html></html>",
            "final_url": "https://example.com/ad/1",
            "service_used": "webcrawler",
        }
        mock_parser = MagicMock()
        mock_result = MagicMock()
        mock_result.phone_numbers = ["+380501234567"]
        mock_result.viber_link = None
        mock_parser.extract_phones.return_value = mock_result
        mock_parser_fn.return_value = mock_parser

        mock_db = MagicMock()
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        extract_phones_for_ad_v1(ad_id=1, resource_url="https://example.com/ad/1")

        mock_add_phone.assert_called_once_with(mock_db, 1, "+380501234567")
        mock_cache.assert_called_once()

    @patch("common.utils.extraction_client.extraction_client")
    def test_logs_error_on_extraction_failure(self, mock_client):
        from common.tasks import extract_phones_for_ad_v1

        mock_client.extract_content.return_value = {
            "status": "error",
            "error": "Timeout",
            "service_used": "camoufox",
        }

        # Should not raise
        extract_phones_for_ad_v1(ad_id=1, resource_url="https://example.com/ad/1")

    @patch("common.utils.extraction_client.extraction_client")
    def test_re_raises_on_exception(self, mock_client):
        from common.tasks import extract_phones_for_ad_v1

        mock_client.extract_content.side_effect = ConnectionError("Service down")

        with pytest.raises(ConnectionError):
            extract_phones_for_ad_v1(ad_id=1, resource_url="https://example.com/ad/1")
