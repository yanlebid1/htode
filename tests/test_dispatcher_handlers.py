# tests/test_dispatcher_handlers.py

import sys
import types
import importlib.util
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import contextmanager

# Pre-mock adspower_manager (imported via common.db.operations → phone_utils)
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

# aiogram v3 FSMContext is at aiogram.fsm.context — no pre-mocking needed

# Ensure common.db.database has get_db_session (handlers.py imports it)
try:
    from common.db.database import get_db_session  # noqa: F401
except (ImportError, AttributeError):
    import common.db.database as _db_mod
    _db_mod.get_db_session = MagicMock()

# ── Build fake dispatcher service package so handlers.py can import from it ──

# 1. Create a fake "services.dispatcher_service.app" package with a logger
import logging
_fake_app_pkg = types.ModuleType("services.dispatcher_service.app")
_fake_app_pkg.logger = logging.getLogger("test.dispatcher")

# 2. Create a fake "services.dispatcher_service.app.bot" with bot instance
_fake_bot_mod = types.ModuleType("services.dispatcher_service.app.bot")
_fake_bot_mod.bot = MagicMock()

# 3. Register all levels in sys.modules
sys.modules["services.dispatcher_service"] = types.ModuleType("services.dispatcher_service")
sys.modules["services.dispatcher_service.app"] = _fake_app_pkg
sys.modules["services.dispatcher_service.app.bot"] = _fake_bot_mod

# 4. Now load handlers.py from disk as a real module
_spec = importlib.util.spec_from_file_location(
    "services.dispatcher_service.app.handlers",
    "/home/lyk/projects/htode/services/dispatcher_service/app/handlers.py",
)
handlers = importlib.util.module_from_spec(_spec)
sys.modules["services.dispatcher_service.app.handlers"] = handlers
_spec.loader.exec_module(handlers)

import pytest


# ── Helper fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_message():
    """Create a mock Telegram message for testing handlers."""
    msg = AsyncMock(spec=[])  # spec=[] prevents arbitrary attr access
    msg.from_user = MagicMock(spec=[])
    msg.from_user.id = 999999
    msg.from_user.username = "testuser"
    msg.from_user.first_name = "Test"
    msg.chat = MagicMock()
    msg.chat.id = 999999
    msg.text = "/start"
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_admin_message():
    """Create a mock Telegram message from an admin."""
    msg = AsyncMock(spec=[])
    msg.from_user = MagicMock(spec=[])
    msg.from_user.id = 123456789  # Admin ID from handlers.py
    msg.from_user.username = "admin"
    msg.from_user.first_name = "Admin"
    msg.chat = MagicMock()
    msg.chat.id = 123456789
    msg.text = "/status"
    msg.answer = AsyncMock()
    return msg


@contextmanager
def mock_db_session_ctx(mock_session):
    """Helper to create a context manager that yields mock_session."""
    yield mock_session


# ── start_handler() ─────────────────────────────────────────────────────────


class TestStartHandler:
    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.bot_assignment_service")
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_new_user_assigns_bot(self, mock_get_db, mock_bot_service, mock_message):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        mock_bot_service.assign_user_to_bot.return_value = {
            "bot_name": "orchid",
            "bot_username": "@hto_de_orchid_bot",
        }

        await handlers.start_handler(mock_message)

        mock_message.answer.assert_called_once()
        call_text = mock_message.answer.call_args[0][0]
        assert "персонального бота" in call_text

    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_existing_user_with_bot_shows_existing(self, mock_get_db, mock_message):
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.assigned_bot_name = "orchid"
        mock_user.assigned_bot_username = "@hto_de_orchid_bot"
        mock_user.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        await handlers.start_handler(mock_message)

        mock_message.answer.assert_called_once()
        call_text = mock_message.answer.call_args[0][0]
        assert "вже зареєстровані" in call_text

    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.bot_assignment_service")
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_assignment_failure_shows_error(self, mock_get_db, mock_bot_service, mock_message):
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.assigned_bot_name = None
        mock_user.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        mock_bot_service.assign_user_to_bot.return_value = None

        await handlers.start_handler(mock_message)

        mock_message.answer.assert_called_once()
        call_text = mock_message.answer.call_args[0][0]
        assert "завантажені" in call_text


# ── status_handler() ────────────────────────────────────────────────────────


class TestStatusHandler:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, mock_message):
        mock_message.from_user.id = 999  # Not in admin list

        await handlers.status_handler(mock_message)

        mock_message.answer.assert_called_once()
        call_text = mock_message.answer.call_args[0][0]
        assert "адміністраторам" in call_text

    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.bot_assignment_service")
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_admin_shows_stats(self, mock_get_db, mock_bot_service, mock_admin_message):
        mock_session = MagicMock()
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        mock_bot_service.get_bot_statistics.return_value = {
            "total_capacity": 100000,
            "total_users": 50000,
            "overall_utilization": "50%",
            "bots": [
                {
                    "username": "@hto_de_orchid_bot",
                    "current_users": 2500,
                    "max_users": 5000,
                    "utilization": "50%",
                }
            ],
        }

        await handlers.status_handler(mock_admin_message)

        mock_admin_message.answer.assert_called_once()
        call_text = mock_admin_message.answer.call_args[0][0]
        assert "Статус системи" in call_text


# ── reassign_handler() ──────────────────────────────────────────────────────


class TestReassignHandler:
    @pytest.mark.asyncio
    async def test_non_admin_denied(self, mock_message):
        mock_message.from_user.id = 999
        mock_message.text = "/reassign 123 bot_5"

        await handlers.reassign_handler(mock_message)

        call_text = mock_message.answer.call_args[0][0]
        assert "адміністраторам" in call_text

    @pytest.mark.asyncio
    async def test_wrong_format_shows_usage(self, mock_admin_message):
        mock_admin_message.text = "/reassign"

        await handlers.reassign_handler(mock_admin_message)

        call_text = mock_admin_message.answer.call_args[0][0]
        assert "Використання" in call_text

    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.bot_assignment_service")
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_correct_format_reassigns(self, mock_get_db, mock_bot_service, mock_admin_message):
        mock_session = MagicMock()
        mock_get_db.return_value = mock_db_session_ctx(mock_session)
        mock_bot_service.reassign_user.return_value = True
        mock_admin_message.text = "/reassign 123 bot_5"

        await handlers.reassign_handler(mock_admin_message)

        call_text = mock_admin_message.answer.call_args[0][0]
        assert "переміщений" in call_text

    @pytest.mark.asyncio
    async def test_invalid_user_id_shows_error(self, mock_admin_message):
        mock_admin_message.text = "/reassign not_a_number bot_5"

        await handlers.reassign_handler(mock_admin_message)

        call_text = mock_admin_message.answer.call_args[0][0]
        assert "Невірний формат" in call_text


# ── default_handler() ───────────────────────────────────────────────────────


class TestDefaultHandler:
    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_assigned_user_redirects_to_bot(self, mock_get_db, mock_message):
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.assigned_bot_username = "@hto_de_orchid_bot"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        await handlers.default_handler(mock_message)

        call_text = mock_message.answer.call_args[0][0]
        assert "персонального бота" in call_text

    @pytest.mark.asyncio
    @patch("services.dispatcher_service.app.handlers.get_db_session")
    async def test_unassigned_user_prompts_start(self, mock_get_db, mock_message):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db_session_ctx(mock_session)

        await handlers.default_handler(mock_message)

        call_text = mock_message.answer.call_args[0][0]
        assert "/start" in call_text
