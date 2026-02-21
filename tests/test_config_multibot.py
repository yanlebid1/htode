# tests/test_config_multibot.py

import os
import sys
import importlib
import pytest
from unittest.mock import patch

# Restore real common.config_multibot if another test replaced it with a MagicMock
_real_module_path = os.path.join(os.path.dirname(__file__), "..", "common", "config_multibot.py")
if "common.config_multibot" in sys.modules:
    mod = sys.modules["common.config_multibot"]
    if not hasattr(mod, "__file__") or mod.__file__ is None:
        # It's a MagicMock — force reimport
        del sys.modules["common.config_multibot"]
        import common.config_multibot  # noqa: F401


class TestBotConfigDefaults:
    """Tests for BotConfig dataclass defaults."""

    def test_default_max_users(self):
        from common.config_multibot import BotConfig

        bot = BotConfig(name="test", token="tok", username="@test")
        assert bot.max_users == 5000

    def test_default_is_active(self):
        from common.config_multibot import BotConfig

        bot = BotConfig(name="test", token="tok", username="@test")
        assert bot.is_active is True


class TestMultiBotConfigLoadBotPool:
    """Tests for MultiBotConfig._load_bot_pool() env loading."""

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "TELEGRAM_DISPATCHER_USERNAME": "@dispatch_bot",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
        "BOT_POOL_2_TOKEN": "tok2",
        "BOT_POOL_2_USERNAME": "@hto_de_tulip_bot",
    }, clear=False)
    def test_loads_bots_from_env(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        assert len(config.pool_bots) >= 2

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
    }, clear=True)
    def test_stops_at_first_missing_token(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        # BOT_POOL_2_TOKEN is missing → only 1 bot loaded
        assert len(config.pool_bots) == 1

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
    }, clear=True)
    def test_extracts_flower_name(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        assert config.pool_bots[0].name == "orchid"

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@custom_bot",
    }, clear=True)
    def test_non_flower_username_uses_bot_n_fallback(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        assert config.pool_bots[0].name == "bot_1"

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
        "BOT_POOL_1_MAX_USERS": "3000",
        "BOT_POOL_1_ACTIVE": "false",
    }, clear=True)
    def test_parses_max_users_and_active(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        assert config.pool_bots[0].max_users == 3000
        assert config.pool_bots[0].is_active is False


class TestMultiBotConfigMethods:
    """Tests for MultiBotConfig query methods."""

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "TELEGRAM_DISPATCHER_USERNAME": "@my_dispatcher",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
        "BOT_POOL_1_ACTIVE": "true",
        "BOT_POOL_2_TOKEN": "tok2",
        "BOT_POOL_2_USERNAME": "@hto_de_tulip_bot",
        "BOT_POOL_2_ACTIVE": "false",
    }, clear=True)
    def test_get_active_bots_filters_inactive(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        active = config.get_active_bots()
        names = [b.name for b in active]
        assert "orchid" in names
        assert "tulip" not in names

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
    }, clear=True)
    def test_get_bot_by_name_found(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        bot = config.get_bot_by_name("orchid")
        assert bot is not None
        assert bot.token == "tok1"

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
    }, clear=True)
    def test_get_bot_by_name_not_found(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        assert config.get_bot_by_name("nonexistent") is None

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "BOT_POOL_1_TOKEN": "tok1",
        "BOT_POOL_1_USERNAME": "@hto_de_orchid_bot",
        "BOT_POOL_1_MAX_USERS": "5000",
        "BOT_POOL_1_ACTIVE": "true",
        "BOT_POOL_2_TOKEN": "tok2",
        "BOT_POOL_2_USERNAME": "@hto_de_tulip_bot",
        "BOT_POOL_2_MAX_USERS": "3000",
        "BOT_POOL_2_ACTIVE": "false",
    }, clear=True)
    def test_get_total_capacity_sums_active_only(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        # Only orchid (5000) is active; tulip (3000) is inactive
        assert config.get_total_capacity() == 5000

    @patch.dict(os.environ, {
        "TELEGRAM_DISPATCHER_TOKEN": "dispatch_tok",
        "TELEGRAM_DISPATCHER_USERNAME": "@my_dispatch",
    }, clear=True)
    def test_get_dispatcher_config(self):
        from common.config_multibot import MultiBotConfig

        config = MultiBotConfig()
        dc = config.get_dispatcher_config()
        assert dc["token"] == "dispatch_tok"
        assert dc["username"] == "@my_dispatch"
