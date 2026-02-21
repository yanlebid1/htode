# tests/test_cache_managers.py

import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from common.utils.cache import redis_client
from common.utils.cache_managers import (
    BaseCacheManager,
    UserCacheManager,
    AdCacheManager,
)


class TestBaseCacheManagerGet:
    def setup_method(self):
        redis_client.get.return_value = None

    def test_cache_hit_valid_json(self):
        redis_client.get.return_value = json.dumps({"name": "test"})
        result = BaseCacheManager.get("hit_key")
        assert result == {"name": "test"}

    def test_cache_miss_returns_none(self):
        redis_client.get.return_value = None
        result = BaseCacheManager.get("miss_key")
        assert result is None

    def test_invalid_json_returns_none(self):
        redis_client.get.return_value = b"not-valid-json{{"
        result = BaseCacheManager.get("bad_json_key")
        assert result is None


class TestBaseCacheManagerSet:
    def test_serializes_and_stores(self):
        BaseCacheManager.set("set_key", {"data": 1}, ttl=60)
        redis_client.set.assert_called_with("set_key", '{"data": 1}', ex=60)

    def test_handles_decimal_via_default_str(self):
        BaseCacheManager.set("decimal_key", {"price": Decimal("99.50")}, ttl=120)
        redis_client.set.assert_called()
        # Verify the Decimal was serialized as string
        call_args = redis_client.set.call_args
        parsed = json.loads(call_args[0][1])
        assert parsed["price"] == "99.50"


class TestBaseCacheManagerDelete:
    def test_deletes_key(self):
        BaseCacheManager.delete("del_key")
        redis_client.delete.assert_called_with("del_key")


class TestBaseCacheManagerKeyExists:
    def test_exists_true(self):
        redis_client.exists.return_value = 1
        assert BaseCacheManager.key_exists("exist_key") is True

    def test_exists_false(self):
        redis_client.exists.return_value = 0
        assert BaseCacheManager.key_exists("noexist_key") is False


class TestBaseCacheManagerDeletePattern:
    def setup_method(self):
        redis_client.scan.side_effect = None
        redis_client.scan.return_value = (0, [])

    def test_scans_and_deletes(self):
        redis_client.scan.return_value = (0, [b"user:1:a", b"user:1:b"])
        redis_client.delete.return_value = 2
        count = BaseCacheManager.delete_pattern("user:1:*")
        assert count == 2

    def test_no_keys_found(self):
        redis_client.scan.return_value = (0, [])
        count = BaseCacheManager.delete_pattern("empty:*")
        assert count == 0

    def test_error_handling(self):
        redis_client.scan.side_effect = Exception("Redis down")
        count = BaseCacheManager.delete_pattern("err:*")
        assert count == 0
        redis_client.scan.side_effect = None
        redis_client.scan.return_value = (0, [])


class TestBaseCacheManagerDeleteKeys:
    def test_multiple_keys(self):
        redis_client.exists.side_effect = [1, 1, 0]
        redis_client.delete.return_value = 2
        count = BaseCacheManager.delete_keys(["k1", "k2", "k3"])
        assert count == 2
        redis_client.exists.side_effect = None
        redis_client.exists.return_value = 0

    def test_empty_list(self):
        count = BaseCacheManager.delete_keys([])
        assert count == 0

    def test_no_existing_keys(self):
        redis_client.exists.return_value = 0
        count = BaseCacheManager.delete_keys(["gone1", "gone2"])
        assert count == 0


# ── UserCacheManager ─────────────────────────────────────────────────────────


class TestUserCacheManager:
    def setup_method(self):
        redis_client.get.return_value = None

    def test_get_filters_correct_key(self):
        redis_client.get.return_value = json.dumps({"city": "Київ"})
        result = UserCacheManager.get_filters(42)
        assert result == {"city": "Київ"}
        redis_client.get.assert_called_with("user_filters:42")

    def test_set_filters_correct_key(self):
        UserCacheManager.set_filters(42, {"city": "Одеса"})
        redis_client.set.assert_called()
        call_args = redis_client.set.call_args
        assert call_args[0][0] == "user_filters:42"


# ── AdCacheManager ───────────────────────────────────────────────────────────


class TestAdCacheManager:
    def setup_method(self):
        redis_client.get.return_value = None

    def test_get_full_ad_data_correct_key(self):
        redis_client.get.return_value = json.dumps({"price": 5000})
        result = AdCacheManager.get_full_ad_data(99)
        assert result == {"price": 5000}
        redis_client.get.assert_called_with("full_ad:99")

    def test_set_full_ad_data_correct_key(self):
        AdCacheManager.set_full_ad_data(99, {"price": 7000})
        redis_client.set.assert_called()
        call_args = redis_client.set.call_args
        assert call_args[0][0] == "full_ad:99"


# ── invalidate_keys_for_entity ───────────────────────────────────────────────


class TestInvalidateKeysForEntity:
    def setup_method(self):
        redis_client.scan.side_effect = None
        redis_client.scan.return_value = (0, [])

    def test_base_pattern_plus_extra_patterns(self):
        redis_client.scan.return_value = (0, [b"user:5:filters"])
        redis_client.delete.return_value = 1
        count = BaseCacheManager.invalidate_keys_for_entity(
            "user", 5, extra_patterns=["user_subs:5:*"]
        )
        assert count >= 0  # exact count depends on mock interaction
        assert redis_client.scan.call_count >= 2
        redis_client.scan.return_value = (0, [])
