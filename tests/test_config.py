# tests/test_config.py

import pytest
from common.config import build_ad_text, get_key_by_value, GEO_ID_MAPPING
from common.constants import (
    FREE_TRIAL_DAYS,
    NOTIFICATION_BATCH_SIZE,
    DEFAULT_BATCH_SIZE,
    MAX_SUBSCRIPTIONS_PER_USER,
    DEFAULT_MAX_USERS_PER_BOT,
    CLEANUP_DEFAULT_DAYS,
)


class TestBuildAdText:
    """Tests for build_ad_text() formatting."""

    def test_plain_text_format(self, test_ad_data):
        """Test plain text formatting (no markdown)."""
        text = build_ad_text(test_ad_data, markdown=False)

        assert "5000" in text
        assert "Київ" in text
        assert "Test Address" in text
        assert "2" in text  # rooms_count
        assert "65.5" in text  # square_feet
        assert "3" in text  # floor
        assert "9" in text  # total_floors

    def test_markdown_format(self, test_ad_data):
        """Test markdown formatting wraps values with asterisks."""
        text = build_ad_text(test_ad_data, markdown=True)

        assert "*5000*" in text
        assert "*Київ*" in text
        assert "*Test Address*" in text
        assert "*2*" in text

    def test_geo_id_lookup(self):
        """Test that integer city values are resolved via GEO_ID_MAPPING."""
        ad = {"city": 10012684, "price": 1000}  # Lviv
        text = build_ad_text(ad)
        assert "Львів" in text

    def test_unknown_city_geo_id(self):
        """Test that unknown geo_ids fall back to 'Невідомо'."""
        ad = {"city": 99999999, "price": 1000}
        text = build_ad_text(ad)
        assert "Невідомо" in text

    def test_missing_fields_use_defaults(self):
        """Test that missing fields get default placeholder values."""
        ad = {"price": 0}
        text = build_ad_text(ad)

        assert "Не вказано" in text  # address default
        assert "?" in text  # rooms_count, square_feet, floor, total_floors

    def test_string_city_passthrough(self):
        """Test that string city values are used directly."""
        ad = {"city": "Одеса", "price": 3000}
        text = build_ad_text(ad)
        assert "Одеса" in text

    def test_none_city_falls_back(self):
        """Test that None city results in 'Невідомо'."""
        ad = {"city": None, "price": 1000}
        text = build_ad_text(ad)
        assert "Невідомо" in text


class TestGetKeyByValue:
    """Tests for get_key_by_value() reverse lookup."""

    def test_found(self):
        """Test successful reverse lookup."""
        result = get_key_by_value("Київ", GEO_ID_MAPPING)
        assert result == 10009580

    def test_not_found(self):
        """Test that unknown value returns None."""
        result = get_key_by_value("Nonexistent City", GEO_ID_MAPPING)
        assert result is None


class TestGeoIdMapping:
    """Tests for GEO_ID_MAPPING completeness."""

    def test_contains_major_cities(self):
        """Test that major Ukrainian cities are present."""
        city_names = set(GEO_ID_MAPPING.values())
        assert "Київ" in city_names
        assert "Львів" in city_names
        assert "Одеса" in city_names
        assert "Дніпро" in city_names
        assert "Харків" in city_names


class TestConstants:
    """Tests for constants module values."""

    def test_free_trial_days_is_positive(self):
        assert FREE_TRIAL_DAYS > 0
        assert isinstance(FREE_TRIAL_DAYS, int)

    def test_notification_batch_size_is_positive(self):
        assert NOTIFICATION_BATCH_SIZE > 0
        assert isinstance(NOTIFICATION_BATCH_SIZE, int)

    def test_default_batch_size_is_positive(self):
        assert DEFAULT_BATCH_SIZE > 0

    def test_max_subscriptions_per_user(self):
        assert MAX_SUBSCRIPTIONS_PER_USER > 0

    def test_default_max_users_per_bot(self):
        assert DEFAULT_MAX_USERS_PER_BOT > 0

    def test_cleanup_default_days(self):
        assert CLEANUP_DEFAULT_DAYS > 0
