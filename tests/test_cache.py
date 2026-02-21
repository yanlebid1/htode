# tests/test_cache.py

import json
import hashlib
import pytest
from unittest.mock import patch, MagicMock, call

from common.utils.cache import (
    cache_key,
    get_entity_cache_key,
    CacheTTL,
    _scan_keys,
    redis_cache,
    redis_client,
)


# ── CacheTTL constants ───────────────────────────────────────────────────────


class TestCacheTTL:
    def test_short_is_60(self):
        assert CacheTTL.SHORT == 60

    def test_medium_is_300(self):
        assert CacheTTL.MEDIUM == 300

    def test_standard_is_3600(self):
        assert CacheTTL.STANDARD == 3600

    def test_long_is_86400(self):
        assert CacheTTL.LONG == 86400

    def test_extended_is_604800(self):
        assert CacheTTL.EXTENDED == 604800


# ── cache_key() ──────────────────────────────────────────────────────────────


class TestCacheKey:
    def test_basic_key(self):
        result = cache_key("prefix", "arg1", "arg2")
        assert result == "prefix:arg1:arg2"

    def test_with_kwargs_sorted(self):
        result = cache_key("pfx", z="3", a="1", m="2")
        assert result == "pfx:a:1:m:2:z:3"

    def test_long_key_hashed(self):
        """Keys longer than 200 chars get MD5-hashed."""
        long_arg = "x" * 250
        result = cache_key("prefix", long_arg)
        assert result.startswith("prefix:")
        # Should be an MD5 hex digest after the prefix
        hex_part = result.split(":", 1)[1]
        assert len(hex_part) == 32  # MD5 hex length

    def test_empty_prefix(self):
        result = cache_key("", "a")
        assert result == ":a"


# ── get_entity_cache_key() ───────────────────────────────────────────────────


class TestGetEntityCacheKey:
    def test_basic(self):
        assert get_entity_cache_key("user", 42) == "user:42"

    def test_with_suffix(self):
        assert get_entity_cache_key("ad", 7, suffix="images") == "ad:7:images"

    def test_without_suffix(self):
        assert get_entity_cache_key("sub", "abc") == "sub:abc"


# ── _scan_keys() ─────────────────────────────────────────────────────────────


class TestScanKeys:
    def test_returns_matching_keys(self):
        redis_client.scan.side_effect = [
            (0, [b"key1", b"key2"]),
        ]
        result = _scan_keys("pattern:*")
        assert result == [b"key1", b"key2"]
        # Reset
        redis_client.scan.side_effect = None
        redis_client.scan.return_value = (0, [])

    def test_empty_result(self):
        redis_client.scan.return_value = (0, [])
        result = _scan_keys("nothing:*")
        assert result == []

    def test_multi_page_scan(self):
        """SCAN that returns a non-zero cursor on first call."""
        redis_client.scan.side_effect = [
            (42, [b"k1"]),
            (0, [b"k2", b"k3"]),
        ]
        result = _scan_keys("multi:*")
        assert result == [b"k1", b"k2", b"k3"]
        # Reset
        redis_client.scan.side_effect = None
        redis_client.scan.return_value = (0, [])


# ── redis_cache decorator ────────────────────────────────────────────────────


class TestRedisCacheDecorator:
    def setup_method(self):
        """Reset redis mock state before each test."""
        redis_client.get.return_value = None
        redis_client.delete.return_value = 1
        redis_client.scan.return_value = (0, [])
        redis_client.scan.side_effect = None

    def test_cache_hit_returns_cached(self):
        redis_client.get.return_value = json.dumps({"cached": True})

        @redis_cache("test_prefix")
        def my_func(x):
            return {"computed": x}

        result = my_func(1)
        assert result == {"cached": True}
        # Reset
        redis_client.get.return_value = None

    def test_cache_miss_calls_function(self):
        redis_client.get.return_value = None

        call_count = 0

        @redis_cache("miss_prefix")
        def my_func(x):
            nonlocal call_count
            call_count += 1
            return {"value": x}

        result = my_func(5)
        assert result == {"value": 5}
        assert call_count == 1
        # Verify it tried to cache the result
        redis_client.set.assert_called()

    def test_invalidate_cache_specific_key(self):
        @redis_cache("inv_prefix")
        def my_func(x):
            return x

        my_func.invalidate_cache(42)
        redis_client.delete.assert_called()

    def test_invalidate_cache_all_prefix(self):
        redis_client.scan.return_value = (0, [b"inv_all:key1", b"inv_all:key2"])

        @redis_cache("inv_all")
        def my_func(x):
            return x

        my_func.invalidate_cache()
        redis_client.scan.assert_called()
