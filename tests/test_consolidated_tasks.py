# tests/test_consolidated_tasks.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.messaging.consolidated_tasks import (
    send_notification,
    send_property_notification,
    send_subscription_reminder,
    send_batch_notifications,
    get_description_and_notify,
    process_new_listings,
)


# ── send_notification() ─────────────────────────────────────────────────


class TestSendNotification:
    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    def test_sends_formatted_message(self, mock_send):
        mock_send.return_value = True
        result = send_notification(
            user_id=123,
            template="Hello {name}!",
            data={"name": "Alice"},
        )
        assert result is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert "Alice" in call_kwargs.kwargs.get("text", call_kwargs[1].get("text", ""))

    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    def test_sends_raw_template_when_no_data(self, mock_send):
        mock_send.return_value = True
        result = send_notification(user_id=123, template="Plain text")
        assert result is True

    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    def test_handles_send_failure(self, mock_send):
        mock_send.side_effect = Exception("connection lost")
        result = send_notification(user_id=123, template="test")
        assert result is False

    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    def test_handles_template_format_error(self, mock_send):
        """When template has placeholders but data doesn't match, falls back to raw template."""
        mock_send.return_value = True
        result = send_notification(
            user_id=123,
            template="Hello {missing_key}!",
            data={"wrong_key": "value"},
        )
        assert result is True
        # Should still send (using raw template as fallback)
        mock_send.assert_called_once()


# ── send_property_notification() ─────────────────────────────────────────


class TestSendPropertyNotification:
    @patch("common.messaging.consolidated_tasks.messaging_service")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_fetches_ad_and_sends(self, mock_db_ctx, mock_msg_svc):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # First db_session call: get_full_ad_data
        mock_ad_data = {"id": 1, "title": "Nice apartment"}
        # Second db_session call: get_ad_images
        mock_images = ["https://cdn.example.com/img1.jpg"]

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_repo.get_full_ad_data.return_value = mock_ad_data
            mock_repo.get_ad_images.return_value = mock_images
            mock_msg_svc.send_ad = AsyncMock(return_value=True)

            result = send_property_notification(user_id=42, ad_id=1)
            assert result is True

    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_missing_ad(self, mock_db_ctx):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_repo.get_full_ad_data.return_value = None
            result = send_property_notification(user_id=42, ad_id=999)
            assert result is False

    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_exception_gracefully(self, mock_db_ctx):
        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = send_property_notification(user_id=42, ad_id=1)
        assert result is False


# ── send_subscription_reminder() ─────────────────────────────────────────


class TestSendSubscriptionReminder:
    @patch("common.messaging.consolidated_tasks.send_notification")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_queries_and_sends_reminders(self, mock_db_ctx, mock_send):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # Mock user with subscription expiring in 2 days
        mock_user = MagicMock()
        mock_user.id = 100
        mock_user.subscription_until = datetime.now() + timedelta(days=2)

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_user]

        mock_send.delay = MagicMock()

        result = send_subscription_reminder()
        assert result["status"] == "success"
        assert result["reminders_sent"] >= 1

    @patch("common.messaging.consolidated_tasks.send_notification")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_skips_when_no_expiring_subscriptions(self, mock_db_ctx, mock_send):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # No users found
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_send.delay = MagicMock()

        result = send_subscription_reminder()
        assert result["status"] == "success"
        assert result["reminders_sent"] == 0

    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_db_error(self, mock_db_ctx):
        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB connection failed")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = send_subscription_reminder()
        assert result["status"] == "error"


# ── send_batch_notifications() ───────────────────────────────────────────


class TestSendBatchNotifications:
    @patch("common.messaging.consolidated_tasks.send_notification")
    def test_sends_to_each_user(self, mock_send):
        mock_send.delay = MagicMock()
        user_ids = [1, 2, 3, 4, 5]
        result = send_batch_notifications(
            user_ids=user_ids, template="Hello!"
        )
        assert result["total"] == 5
        assert result["success"] == 5
        assert result["failed"] == 0
        assert mock_send.delay.call_count == 5

    @patch("common.messaging.consolidated_tasks.send_notification")
    def test_tracks_success_failed_counts(self, mock_send):
        # 2nd and 4th calls fail
        mock_send.delay = MagicMock(
            side_effect=[None, Exception("fail"), None, Exception("fail"), None]
        )
        user_ids = [1, 2, 3, 4, 5]
        result = send_batch_notifications(
            user_ids=user_ids, template="Hello!"
        )
        assert result["success"] == 3
        assert result["failed"] == 2

    @patch("common.messaging.consolidated_tasks.send_notification")
    def test_handles_individual_failures_without_stopping(self, mock_send):
        mock_send.delay = MagicMock(
            side_effect=[Exception("fail"), None, None]
        )
        result = send_batch_notifications(
            user_ids=[1, 2, 3], template="Test"
        )
        # Despite first failure, continues to process remaining
        assert result["success"] == 2
        assert result["failed"] == 1


# ── get_description_and_notify() ─────────────────────────────────────────


class TestGetDescriptionAndNotify:
    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_fetches_ad_and_sends_description(self, mock_db_ctx, mock_send):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_ad = MagicMock()
            mock_ad.description = "Beautiful 2BR apartment in Kyiv center"
            mock_repo.get_by_resource_url.return_value = mock_ad
            mock_send.return_value = True

            result = get_description_and_notify(
                user_id=123, resource_url="https://example.com/ad/1"
            )
            assert result is True
            # Verify the description text was sent
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args
            sent_text = call_kwargs.kwargs.get("text", call_kwargs[1].get("text", ""))
            assert "Beautiful" in sent_text

    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_ad_not_found(self, mock_db_ctx, mock_send):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_repo.get_by_resource_url.return_value = None
            mock_send.return_value = True

            result = get_description_and_notify(
                user_id=123, resource_url="https://example.com/ad/missing"
            )
            assert result is False

    @patch("common.messaging.consolidated_tasks.safe_send_message", new_callable=AsyncMock)
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_exception(self, mock_db_ctx, mock_send):
        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = get_description_and_notify(
            user_id=123, resource_url="https://example.com/ad/1"
        )
        assert result is False


# ── process_new_listings() ───────────────────────────────────────────────


class TestProcessNewListings:
    @patch("common.messaging.consolidated_tasks.send_property_notification")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_finds_matching_users_and_dispatches(self, mock_db_ctx, mock_send_prop):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad = MagicMock()
        mock_db.query.return_value.get.return_value = mock_ad

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_repo.find_users_for_ad.return_value = [10, 20, 30]
            mock_send_prop.delay = MagicMock()

            result = process_new_listings(ad_ids=[1])
            assert result["status"] == "success"
            assert result["notifications_sent"] == 3
            assert mock_send_prop.delay.call_count == 3

    @patch("common.messaging.consolidated_tasks.send_property_notification")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_no_matching_users(self, mock_db_ctx, mock_send_prop):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad = MagicMock()
        mock_db.query.return_value.get.return_value = mock_ad

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            mock_repo.find_users_for_ad.return_value = []
            mock_send_prop.delay = MagicMock()

            result = process_new_listings(ad_ids=[1])
            assert result["status"] == "success"
            assert result["notifications_sent"] == 0

    @patch("common.messaging.consolidated_tasks.db_session")
    def test_handles_exception(self, mock_db_ctx):
        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = process_new_listings(ad_ids=[1, 2])
        assert result["status"] == "error"

    @patch("common.messaging.consolidated_tasks.send_property_notification")
    @patch("common.messaging.consolidated_tasks.db_session")
    def test_respects_max_notifications_per_user(self, mock_db_ctx, mock_send_prop):
        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad = MagicMock()
        mock_db.query.return_value.get.return_value = mock_ad

        with patch(
            "common.messaging.consolidated_tasks.AdRepository"
        ) as mock_repo:
            # Same user matches all 3 ads
            mock_repo.find_users_for_ad.return_value = [42]
            mock_send_prop.delay = MagicMock()

            result = process_new_listings(
                ad_ids=[1, 2, 3], max_notifications_per_user=2
            )
            assert result["status"] == "success"
            # User 42 should only get 2 notifications (not 3)
            assert result["notifications_sent"] == 2
            assert mock_send_prop.delay.call_count == 2
