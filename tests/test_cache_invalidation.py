# tests/test_cache_invalidation.py

import sys
from unittest.mock import patch, MagicMock, call

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.utils.cache_invalidation import (
    invalidate_ad_caches,
    invalidate_phone_caches,
    invalidate_user_caches,
    invalidate_subscription_caches,
    invalidate_favorite_caches,
    warm_cache_for_user,
)


# ── invalidate_ad_caches() ─────────────────────────────────────────────────


class TestInvalidateAdCaches:
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=0)
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_keys", return_value=3)
    def test_deletes_entity_keys(self, mock_del_keys, mock_del_pattern):
        result = invalidate_ad_caches(ad_id=42)
        # delete_keys called with full_ad, ad_images, matching_users keys
        keys = mock_del_keys.call_args[0][0]
        assert len(keys) == 3
        assert result >= 3

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=0)
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_keys", return_value=5)
    def test_includes_resource_url_keys(self, mock_del_keys, mock_del_pattern):
        invalidate_ad_caches(ad_id=42, resource_url="https://example.com/ad/42")
        keys = mock_del_keys.call_args[0][0]
        # 3 base keys + 2 resource_url keys = 5
        assert len(keys) == 5

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=0)
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_keys", return_value=3)
    def test_skips_resource_url_keys_when_none(self, mock_del_keys, mock_del_pattern):
        invalidate_ad_caches(ad_id=42, resource_url=None)
        keys = mock_del_keys.call_args[0][0]
        assert len(keys) == 3

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=2)
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_keys", return_value=3)
    def test_calls_delete_pattern_for_ad_patterns(self, mock_del_keys, mock_del_pattern):
        invalidate_ad_caches(ad_id=42)
        # Should call delete_pattern for ad:{id}:* and matching_users:*
        assert mock_del_pattern.call_count == 2

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=5)
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_keys", return_value=3)
    def test_returns_total_deleted_count(self, mock_del_keys, mock_del_pattern):
        result = invalidate_ad_caches(ad_id=42)
        # 3 from delete_keys + 5*2 from delete_pattern (called twice)
        assert result == 3 + 5 + 5


# ── invalidate_phone_caches() ──────────────────────────────────────────────


class TestInvalidatePhoneCaches:
    @patch("common.utils.cache_invalidation.invalidate_ad_caches", return_value=7)
    def test_delegates_to_invalidate_ad_caches(self, mock_inv_ad):
        result = invalidate_phone_caches(ad_id=42)
        mock_inv_ad.assert_called_once_with(42)
        assert result == 7


# ── invalidate_user_caches() ───────────────────────────────────────────────


class TestInvalidateUserCaches:
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=2)
    def test_deletes_user_patterns(self, mock_del_pattern):
        result = invalidate_user_caches(user_id=100)
        # 5 patterns: user:, user_filters:, subscription_status:, user_favorites:, user_subscriptions_list:
        assert mock_del_pattern.call_count == 5
        assert result == 10  # 2 * 5

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=0)
    def test_returns_zero_when_nothing_deleted(self, mock_del_pattern):
        result = invalidate_user_caches(user_id=100)
        assert result == 0


# ── invalidate_subscription_caches() ───────────────────────────────────────


class TestInvalidateSubscriptionCaches:
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=1)
    def test_base_patterns_without_subscription_id(self, mock_del_pattern):
        result = invalidate_subscription_caches(user_id=100)
        # 3 base patterns
        assert mock_del_pattern.call_count == 3
        assert result == 3

    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=1)
    def test_includes_subscription_pattern_when_id_provided(self, mock_del_pattern):
        result = invalidate_subscription_caches(user_id=100, subscription_id=55)
        # 3 base patterns + 1 subscription-specific
        assert mock_del_pattern.call_count == 4
        assert result == 4


# ── invalidate_favorite_caches() ───────────────────────────────────────────


class TestInvalidateFavoriteCaches:
    @patch("common.utils.cache_invalidation.BaseCacheManager.delete_pattern", return_value=3)
    def test_deletes_favorites_pattern(self, mock_del_pattern):
        result = invalidate_favorite_caches(user_id=100)
        assert mock_del_pattern.call_count == 1
        pattern = mock_del_pattern.call_args[0][0]
        assert "user_favorites:100" in pattern
        assert result == 3


# ── warm_cache_for_user() ──────────────────────────────────────────────────


class TestWarmCacheForUser:
    @patch("common.db.operations.batch_get_full_ad_data", return_value={})
    @patch("common.db.operations.get_subscription_data_for_user", return_value={"id": 1})
    @patch("common.db.operations.list_favorites", return_value=[])
    @patch("common.db.operations.get_user_filters", return_value={"city": "Київ"})
    @patch("common.utils.cache_managers.SubscriptionCacheManager")
    @patch("common.utils.cache_managers.UserCacheManager")
    def test_calls_get_user_filters_and_caches(self, mock_ucm, mock_scm,
                                                mock_filters, mock_favs,
                                                mock_sub, mock_batch):
        warm_cache_for_user(user_id=100)
        mock_filters.assert_called_once_with(100)
        mock_ucm.set_filters.assert_called_once_with(100, {"city": "Київ"})

    @patch("common.db.operations.batch_get_full_ad_data", return_value={10: {"id": 10}})
    @patch("common.db.operations.get_subscription_data_for_user", return_value=None)
    @patch("common.db.operations.list_favorites", return_value=[{"ad_id": 10}])
    @patch("common.db.operations.get_user_filters", return_value=None)
    @patch("common.utils.cache_managers.AdCacheManager")
    @patch("common.utils.cache_managers.FavoriteCacheManager")
    @patch("common.utils.cache_managers.SubscriptionCacheManager")
    @patch("common.utils.cache_managers.UserCacheManager")
    def test_prefetches_ad_data_for_favorites(self, mock_ucm, mock_scm,
                                               mock_fcm, mock_acm,
                                               mock_filters, mock_favs,
                                               mock_sub, mock_batch):
        warm_cache_for_user(user_id=100)
        mock_batch.assert_called_once_with([10])
        mock_acm.set_full_ad_data.assert_called_once_with(10, {"id": 10})

    @patch("common.db.operations.get_user_filters", side_effect=Exception("DB down"))
    def test_handles_errors_gracefully(self, mock_filters):
        # Should not raise
        warm_cache_for_user(user_id=100)
