# tests/test_messaging_service.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.messaging.service import MessagingService


# ── MessagingService ─────────────────────────────────────────────────────


class TestMessagingServiceInit:
    def test_starts_with_no_messenger(self):
        svc = MessagingService()
        assert svc.get_messenger() is None

    def test_register_messenger_stores_instance(self):
        svc = MessagingService()
        mock_messenger = MagicMock()
        svc.register_messenger("telegram", mock_messenger)
        assert svc.get_messenger() is mock_messenger

    def test_get_messenger_ignores_platform_arg(self):
        """get_messenger always returns telegram messenger regardless of arg."""
        svc = MessagingService()
        mock_messenger = MagicMock()
        svc.register_messenger("telegram", mock_messenger)
        assert svc.get_messenger("viber") is mock_messenger
        assert svc.get_messenger("anything") is mock_messenger


class TestMessagingServiceSendNotification:
    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_text_via_messenger(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        svc.register_messenger("telegram", mock_messenger)

        result = await svc.send_notification(user_id=42, text="Hello!")
        assert result is True
        mock_messenger.send_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_media_when_image_url_provided(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        svc.register_messenger("telegram", mock_messenger)

        result = await svc.send_notification(
            user_id=42, text="Check this!", image_url="https://cdn.example.com/img.jpg"
        )
        assert result is True
        mock_messenger.send_media.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_menu_when_options_provided(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        svc.register_messenger("telegram", mock_messenger)

        options = [{"text": "Option A", "value": "a"}]
        result = await svc.send_notification(
            user_id=42, text="Choose:", options=options
        )
        assert result is True
        mock_messenger.send_menu.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_false_when_no_platform_found(self, mock_resolve):
        mock_resolve.return_value = (None, None, None)
        svc = MessagingService()

        result = await svc.send_notification(user_id=999, text="Hello!")
        assert result is False

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_false_when_no_messenger_registered(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        # No messenger registered

        result = await svc.send_notification(user_id=42, text="Hello!")
        assert result is False

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_false_on_send_exception(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        mock_messenger.send_text.side_effect = Exception("network error")
        svc.register_messenger("telegram", mock_messenger)

        result = await svc.send_notification(user_id=42, text="Hello!")
        assert result is False


class TestMessagingServiceSendAd:
    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_sends_ad_via_messenger(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        svc.register_messenger("telegram", mock_messenger)

        ad_data = {"id": 1, "title": "Nice apartment"}
        result = await svc.send_ad(user_id=42, ad_data=ad_data)
        assert result is True
        mock_messenger.send_ad.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_false_when_no_platform(self, mock_resolve):
        mock_resolve.return_value = (None, None, None)
        svc = MessagingService()

        result = await svc.send_ad(user_id=999, ad_data={"id": 1})
        assert result is False

    @pytest.mark.asyncio
    @patch("common.messaging.unified_platform_utils.resolve_user_id")
    async def test_returns_false_on_exception(self, mock_resolve):
        mock_resolve.return_value = (42, "telegram", "123456789")
        svc = MessagingService()
        mock_messenger = AsyncMock()
        mock_messenger.send_ad.side_effect = RuntimeError("send failed")
        svc.register_messenger("telegram", mock_messenger)

        result = await svc.send_ad(user_id=42, ad_data={"id": 1})
        assert result is False


class TestMessagingServiceCreateForService:
    def test_creates_new_instance(self):
        svc = MessagingService.create_for_service("telegram")
        assert isinstance(svc, MessagingService)
        assert svc.get_messenger() is None
