# tests/test_unified_interface.py

import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.messaging.unified_interface import (
    MessagingInterface,
    MessengerFactory,
)


# ── Concrete implementation for testing abstract class ───────────────────


class MockMessenger(MessagingInterface):
    """Concrete implementation for testing the abstract interface."""

    @property
    def platform_name(self) -> str:
        return "test_platform"

    async def format_user_id(self, user_id: str) -> str:
        return user_id

    async def send_text(self, user_id, text, keyboard=None, **kwargs):
        return {"status": "sent", "text": text}

    async def send_media(self, user_id, media_url, caption=None, keyboard=None, **kwargs):
        return {"status": "sent", "media_url": media_url}

    async def send_menu(self, user_id, text, options, **kwargs):
        return {"status": "sent", "options": options}

    async def send_ad(self, user_id, ad_data, image_url=None, **kwargs):
        return {"status": "sent", "ad_id": ad_data.get("id")}

    @classmethod
    def create_keyboard(cls, options, **kwargs):
        return {"type": "keyboard", "options": options}


# ── MessagingInterface default methods ───────────────────────────────────


class TestMessagingInterfaceDefaults:
    @pytest.mark.asyncio
    async def test_send_document_delegates_to_send_media(self):
        messenger = MockMessenger()
        result = await messenger.send_document(
            user_id="123", document_url="https://example.com/doc.pdf", caption="A doc"
        )
        assert result["status"] == "sent"
        assert result["media_url"] == "https://example.com/doc.pdf"

    @pytest.mark.asyncio
    async def test_send_location_sends_text_with_coordinates(self):
        messenger = MockMessenger()
        result = await messenger.send_location(
            user_id="123", latitude=50.45, longitude=30.52, title="Kyiv"
        )
        assert result["status"] == "sent"
        assert "50.45" in result["text"]
        assert "Kyiv" in result["text"]

    @pytest.mark.asyncio
    async def test_send_location_without_title(self):
        messenger = MockMessenger()
        result = await messenger.send_location(
            user_id="123", latitude=50.45, longitude=30.52
        )
        assert "50.45" in result["text"]

    @pytest.mark.asyncio
    async def test_get_user_info_returns_none(self):
        messenger = MockMessenger()
        result = await messenger.get_user_info("123")
        assert result is None

    def test_platform_name_property(self):
        messenger = MockMessenger()
        assert messenger.platform_name == "test_platform"

    @pytest.mark.asyncio
    async def test_format_user_id(self):
        messenger = MockMessenger()
        result = await messenger.format_user_id("abc123")
        assert result == "abc123"

    def test_create_keyboard(self):
        options = [{"text": "A", "value": "a"}]
        result = MockMessenger.create_keyboard(options)
        assert result["type"] == "keyboard"


# ── MessengerFactory ────────────────────────────────────────────────────


class TestMessengerFactory:
    def setup_method(self):
        """Clear factory state between tests."""
        MessengerFactory._messengers.clear()

    def test_register_messenger_stores_class(self):
        MessengerFactory.register_messenger("test", MockMessenger)
        assert "test" in MessengerFactory._messengers

    def test_get_messenger_returns_none_for_unregistered(self):
        result = MessengerFactory.get_messenger("nonexistent")
        assert result is None

    def test_get_messenger_returns_none_for_non_telegram_platform(self):
        MessengerFactory.register_messenger("viber", MockMessenger)
        # The factory only handles "telegram" in its get_messenger logic
        result = MessengerFactory.get_messenger("viber")
        assert result is None

    def test_get_messenger_handles_import_error(self):
        """When telegram bot import fails, returns None."""
        MessengerFactory.register_messenger("telegram", MockMessenger)
        # The factory tries to import services.telegram_service.app.bot
        # which will fail in test environment
        result = MessengerFactory.get_messenger("telegram")
        assert result is None  # ImportError caught internally
