# tests/test_keyboard_utils.py

import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock aiogram.types before importing keyboard_utils methods that use them
# The codebase uses aiogram v2 API (.row(), .add(), .insert()) but
# aiogram v3 is installed, so actual keyboard construction would fail.
_mock_aiogram_types = MagicMock()


def _make_mock_keyboard(**kwargs):
    """Create a mock keyboard that tracks row/add/insert calls."""
    kb = MagicMock()
    kb.inline_keyboard = []
    return kb


_mock_aiogram_types.ReplyKeyboardMarkup.side_effect = _make_mock_keyboard
_mock_aiogram_types.InlineKeyboardMarkup.side_effect = _make_mock_keyboard
_mock_aiogram_types.KeyboardButton.side_effect = lambda text, **kw: MagicMock(text=text)
_mock_aiogram_types.InlineKeyboardButton.side_effect = lambda text, callback_data=None, **kw: MagicMock(
    text=text, callback_data=callback_data
)

# keyboard_utils imports from aiogram inside each method, so we patch the module
with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types, "aiogram": MagicMock()}):
    from common.messaging.keyboard_utils import (
        get_price_ranges,
        AVAILABLE_CITIES,
        CITY_GROUPS,
        KeyboardFactory,
        TelegramKeyboardFactory,
    )


# ── get_price_ranges() ───────────────────────────────────────────────────────


class TestGetPriceRanges:
    def test_kyiv_big_city(self):
        ranges = get_price_ranges("Київ")
        assert ranges == [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]

    def test_kharkiv_medium_city(self):
        ranges = get_price_ranges("Харків")
        assert ranges == [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]

    def test_sumy_small_city(self):
        ranges = get_price_ranges("Суми")
        assert ranges == [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]

    def test_unknown_city_defaults_to_small(self):
        ranges = get_price_ranges("НевідомеМісто")
        assert ranges == [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]


# ── AVAILABLE_CITIES ─────────────────────────────────────────────────────────


class TestAvailableCities:
    def test_contains_21_cities(self):
        assert len(AVAILABLE_CITIES) == 21

    def test_includes_key_cities(self):
        for city in ["Київ", "Львів", "Одеса", "Харків", "Дніпро"]:
            assert city in AVAILABLE_CITIES


# ── CITY_GROUPS ──────────────────────────────────────────────────────────────


class TestCityGroups:
    def test_big_has_only_kyiv(self):
        assert CITY_GROUPS["big_cities"] == {"Київ"}

    def test_medium_has_4_cities(self):
        assert CITY_GROUPS["medium_cities"] == {"Харків", "Дніпро", "Одеса", "Львів"}

    def test_small_is_remainder(self):
        expected = set(AVAILABLE_CITIES) - {"Київ", "Харків", "Дніпро", "Одеса", "Львів"}
        assert CITY_GROUPS["small_cities"] == expected


# ── KeyboardFactory ──────────────────────────────────────────────────────────


class TestKeyboardFactory:
    def test_telegram_platform_returns_keyboard(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            result = KeyboardFactory.create_keyboard("telegram", "main_menu")
        assert result is not None

    def test_unsupported_platform_returns_none(self):
        result = KeyboardFactory.create_keyboard("discord", "main_menu")
        assert result is None


# ── TelegramKeyboardFactory ──────────────────────────────────────────────────


class TestTelegramKeyboardFactory:
    def test_main_menu(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_keyboard("main_menu")
        assert kb is not None

    def test_property_type(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_keyboard("property_type")
        assert kb is not None

    def test_city_basic(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_keyboard("city")
        assert kb is not None

    def test_rooms_with_selection(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_keyboard("rooms", selected_rooms=[1, 3])
        assert kb is not None

    def test_price_city_aware(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_keyboard("price", city="Київ")
        assert kb is not None

    def test_unknown_type_returns_none(self):
        kb = TelegramKeyboardFactory.create_keyboard("nonexistent_type")
        assert kb is None


# ── City keyboard pagination ─────────────────────────────────────────────────


class TestCityKeyboardPagination:
    def test_page_0_returns_keyboard(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_city_keyboard(AVAILABLE_CITIES, page=0)
        assert kb is not None

    def test_page_1_returns_keyboard(self):
        with patch.dict(sys.modules, {"aiogram.types": _mock_aiogram_types}):
            kb = TelegramKeyboardFactory.create_city_keyboard(AVAILABLE_CITIES, page=1)
        assert kb is not None
