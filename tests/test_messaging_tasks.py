# tests/test_messaging_tasks.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.messaging.tasks import (
    send_notification,
    send_ad,
    send_menu,
    process_show_more_description,
)


# ── send_notification task ───────────────────────────────────────────────


class TestSendNotificationTask:
    @patch("common.messaging.tasks.messaging_service")
    def test_returns_true_on_success(self, mock_svc):
        mock_svc.send_notification = AsyncMock(return_value=True)
        result = send_notification(user_id=42, text="Hello!")
        assert result is True

    @patch("common.messaging.tasks.messaging_service")
    def test_returns_false_when_service_returns_false(self, mock_svc):
        mock_svc.send_notification = AsyncMock(return_value=False)
        result = send_notification(user_id=42, text="Hello!")
        assert result is False

    @patch("common.messaging.tasks.messaging_service")
    def test_returns_false_on_exception(self, mock_svc):
        mock_svc.send_notification = AsyncMock(side_effect=Exception("fail"))
        result = send_notification(user_id=42, text="Hello!")
        assert result is False


# ── send_ad task ─────────────────────────────────────────────────────────


class TestSendAdTask:
    @patch("common.messaging.tasks.messaging_service")
    def test_returns_true_on_success(self, mock_svc):
        mock_svc.send_ad = AsyncMock(return_value=True)
        ad_data = {"id": 1, "title": "Nice apartment"}
        result = send_ad(user_id=42, ad_data=ad_data)
        assert result is True

    @patch("common.messaging.tasks.messaging_service")
    def test_returns_false_when_service_returns_false(self, mock_svc):
        mock_svc.send_ad = AsyncMock(return_value=False)
        result = send_ad(user_id=42, ad_data={"id": 1})
        assert result is False

    @patch("common.messaging.tasks.messaging_service")
    def test_returns_false_on_exception(self, mock_svc):
        mock_svc.send_ad = AsyncMock(side_effect=RuntimeError("send failed"))
        result = send_ad(user_id=42, ad_data={"id": 1})
        assert result is False

    @patch("common.messaging.tasks.messaging_service")
    def test_passes_image_url_to_service(self, mock_svc):
        mock_svc.send_ad = AsyncMock(return_value=True)
        result = send_ad(
            user_id=42, ad_data={"id": 1},
            image_url="https://cdn.example.com/img.jpg"
        )
        assert result is True
        call_kwargs = mock_svc.send_ad.call_args
        assert call_kwargs.kwargs.get("image_url") == "https://cdn.example.com/img.jpg"


# ── send_menu task ───────────────────────────────────────────────────────


class TestSendMenuTask:
    @patch("common.messaging.tasks.messaging_service")
    def test_returns_true_on_success(self, mock_svc):
        mock_messenger = AsyncMock()
        mock_messenger.format_user_id = AsyncMock(return_value="123456")
        mock_messenger.send_menu = AsyncMock()
        mock_svc.get_messenger_for_user = AsyncMock(
            return_value=("telegram", "123456", mock_messenger)
        )

        options = [{"text": "A", "value": "a"}]
        result = send_menu(user_id=42, text="Choose:", options=options)
        assert result is True

    @patch("common.messaging.tasks.messaging_service")
    def test_returns_false_when_no_messenger(self, mock_svc):
        mock_svc.get_messenger_for_user = AsyncMock(
            return_value=(None, None, None)
        )

        result = send_menu(user_id=42, text="Choose:", options=[])
        assert result is False


# ── process_show_more_description task ───────────────────────────────────


class TestProcessShowMoreDescription:
    @patch("common.messaging.unified_platform_utils.safe_send_message", new_callable=AsyncMock)
    @patch("common.db.operations.get_full_ad_description")
    def test_sends_description_to_user(self, mock_get_desc, mock_send):
        mock_get_desc.return_value = "Full apartment description here."
        mock_send.return_value = True

        process_show_more_description(
            user_id=42, resource_url="https://example.com/ad/1"
        )
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "Full apartment description" in sent_text

    @patch("common.messaging.unified_platform_utils.safe_send_message", new_callable=AsyncMock)
    @patch("common.db.operations.get_full_ad_description")
    def test_sends_fallback_when_no_description(self, mock_get_desc, mock_send):
        mock_get_desc.return_value = None
        mock_send.return_value = True

        process_show_more_description(
            user_id=42, resource_url="https://example.com/ad/missing"
        )
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "недоступний" in sent_text
