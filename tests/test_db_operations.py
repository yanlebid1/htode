# tests/test_db_operations.py

import sys
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.db.operations import (
    create_telegram_user,
    update_user_filter,
    get_user_filters,
    find_users_for_ad,
    batch_find_users_for_ads,
    get_full_ad_data,
    add_favorite_ad,
    store_ad_phones,
    list_subscriptions,
)


# ── create_telegram_user() ──────────────────────────────────────────────────


class TestCreateTelegramUser:
    @patch("common.db.operations.db_session")
    def test_creates_new_user(self, mock_db_session):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db.refresh = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        # Patch User constructor to return our mock
        with patch("common.db.operations.User") as mock_user_cls:
            mock_user_cls.return_value = mock_user
            result = create_telegram_user("12345")

        assert result is mock_user
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("common.db.operations.db_session")
    def test_existing_user_returns_existing(self, mock_db_session):
        mock_db = MagicMock()
        existing_user = MagicMock()
        existing_user.id = 42
        mock_db.query.return_value.filter.return_value.first.return_value = existing_user
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = create_telegram_user("12345")
        assert result is existing_user
        mock_db.add.assert_not_called()

    @patch("common.db.operations.db_session")
    def test_error_returns_none(self, mock_db_session):
        mock_db_session.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = create_telegram_user("12345")
        assert result is None


# ── update_user_filter() ────────────────────────────────────────────────────


class TestUpdateUserFilter:
    @patch("common.db.operations.invalidate_subscription_caches")
    @patch("common.db.operations.SubscriptionRepository")
    @patch("common.db.operations.UserRepository")
    @patch("common.db.operations.db_session")
    def test_updates_filter_with_cache_invalidation(
        self, mock_db_session, mock_user_repo, mock_sub_repo, mock_invalidate
    ):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_user = MagicMock()
        mock_user_repo.get_by_id.return_value = mock_user

        mock_filter = MagicMock()
        mock_sub_repo.update_user_filter.return_value = mock_filter

        filters = {"property_type": "apartment", "city": "Київ"}
        result = update_user_filter(1, filters)

        assert result is mock_filter
        mock_invalidate.assert_called_once_with(1)

    @patch("common.db.operations.UserRepository")
    @patch("common.db.operations.db_session")
    def test_user_not_found_raises_value_error(self, mock_db_session, mock_user_repo):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_user_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="does not exist"):
            update_user_filter(999, {"city": "Київ"})


# ── get_user_filters() ──────────────────────────────────────────────────────


class TestGetUserFilters:
    @patch("common.db.operations.UserCacheManager")
    def test_cache_hit_returns_cached(self, mock_cache):
        mock_cache.get_filters.return_value = {"city": "Київ"}

        result = get_user_filters(1)
        assert result == {"city": "Київ"}

    @patch("common.db.operations.UserCacheManager")
    @patch("common.db.operations.SubscriptionRepository")
    @patch("common.db.operations.db_session")
    def test_cache_miss_queries_db(self, mock_db_session, mock_sub_repo, mock_cache):
        mock_cache.get_filters.return_value = None

        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_sub_repo.get_user_filters.return_value = {"city": "Київ", "rooms": 2}

        result = get_user_filters(1)
        assert result == {"city": "Київ", "rooms": 2}
        mock_cache.set_filters.assert_called_once_with(1, {"city": "Київ", "rooms": 2})


# ── find_users_for_ad() ─────────────────────────────────────────────────────


class TestFindUsersForAd:
    @patch("common.db.operations.BaseCacheManager")
    @patch("common.db.operations.get_entity_cache_key")
    def test_cache_hit_returns_cached(self, mock_cache_key, mock_cache):
        mock_cache_key.return_value = "matching_users:1"
        mock_cache.get.return_value = [100, 200]

        result = find_users_for_ad({"id": 1})
        assert result == [100, 200]

    @patch("common.db.operations.BaseCacheManager")
    @patch("common.db.operations.get_entity_cache_key")
    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.db_session")
    def test_cache_miss_queries_db(self, mock_db_session, mock_ad_repo, mock_cache_key, mock_cache):
        mock_cache_key.return_value = "matching_users:1"
        mock_cache.get.return_value = None

        mock_db = MagicMock()
        mock_db.query.return_value.get.return_value = None
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad_repo.find_users_for_ad.return_value = [300, 400]

        result = find_users_for_ad({"id": 1, "city": "Kyiv", "rooms_count": 2, "price": 5000, "property_type": "apartment"})
        assert result == [300, 400]

    def test_no_ad_id_returns_empty(self):
        result = find_users_for_ad({})
        assert result == []

    @patch("common.db.operations.BaseCacheManager")
    @patch("common.db.operations.get_entity_cache_key")
    def test_error_returns_empty(self, mock_cache_key, mock_cache):
        mock_cache_key.return_value = "matching_users:1"
        mock_cache.get.side_effect = Exception("Cache error")

        result = find_users_for_ad({"id": 1})
        assert result == []


# ── batch_find_users_for_ads() ──────────────────────────────────────────────


class TestBatchFindUsersForAds:
    def test_empty_list_returns_empty_dict(self):
        result = batch_find_users_for_ads([])
        assert result == {}

    @patch("common.db.operations.batch_get_user_filters")
    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.db_session")
    @patch("common.db.operations.BaseCacheManager")
    @patch("common.db.operations.get_entity_cache_key")
    def test_mixed_cache_hits_and_misses(
        self, mock_cache_key, mock_cache, mock_db_session, mock_ad_repo, mock_batch_filters
    ):
        # First ad is cached, second is not
        mock_cache_key.side_effect = lambda *args: f"matching_users:{args[1]}"
        mock_cache.get.side_effect = lambda key: [100] if "1" in key else None
        mock_cache.set = MagicMock()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [(1,)]
        mock_db.query.return_value.get.return_value = None
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad_repo.find_users_for_ad.return_value = [200]

        ads = [{"id": 1}, {"id": 2, "city": "Kyiv", "rooms_count": 2, "price": 5000, "property_type": "apartment"}]
        result = batch_find_users_for_ads(ads)

        assert 1 in result
        assert result[1] == [100]  # from cache


# ── get_full_ad_data() ──────────────────────────────────────────────────────


class TestGetFullAdData:
    @patch("common.db.operations.AdCacheManager")
    def test_cache_hit_returns_cached(self, mock_cache):
        mock_cache.get_full_ad_data.return_value = {"id": 1, "price": 5000}

        result = get_full_ad_data(1)
        assert result == {"id": 1, "price": 5000}

    @patch("common.db.operations.AdCacheManager")
    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.db_session")
    def test_cache_miss_queries_db(self, mock_db_session, mock_ad_repo, mock_cache):
        mock_cache.get_full_ad_data.return_value = None

        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad_repo.get_full_ad_data.return_value = {"id": 2, "price": 7000}

        result = get_full_ad_data(2)
        assert result == {"id": 2, "price": 7000}
        mock_cache.set_full_ad_data.assert_called_once_with(2, {"id": 2, "price": 7000})

    @patch("common.db.operations.AdCacheManager")
    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.db_session")
    def test_not_found_returns_none(self, mock_db_session, mock_ad_repo, mock_cache):
        mock_cache.get_full_ad_data.return_value = None

        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad_repo.get_full_ad_data.return_value = None

        result = get_full_ad_data(999)
        assert result is None


# ── add_favorite_ad() ───────────────────────────────────────────────────────


class TestAddFavoriteAd:
    @patch("common.db.operations.invalidate_favorite_caches")
    @patch("common.db.operations.FavoriteRepository")
    @patch("common.db.operations.db_session")
    def test_success_returns_id(self, mock_db_session, mock_fav_repo, mock_invalidate):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_favorite = MagicMock()
        mock_favorite.id = 42
        mock_fav_repo.add_favorite.return_value = mock_favorite

        result = add_favorite_ad(user_id=1, ad_id=100)
        assert result == 42
        mock_invalidate.assert_called_once_with(1)

    @patch("common.db.operations.FavoriteRepository")
    @patch("common.db.operations.db_session")
    def test_duplicate_returns_none(self, mock_db_session, mock_fav_repo):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_fav_repo.add_favorite.return_value = None

        result = add_favorite_ad(user_id=1, ad_id=100)
        assert result is None


# ── store_ad_phones() ───────────────────────────────────────────────────────


class TestStoreAdPhones:
    @patch("common.db.operations.invalidate_ad_caches")
    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.extract_phone_numbers_from_resource")
    @patch("common.db.operations.db_session")
    def test_extracts_and_stores_phones(
        self, mock_db_session, mock_extract, mock_ad_repo, mock_invalidate
    ):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad = MagicMock()
        mock_ad_repo.get_by_id.return_value = mock_ad

        mock_result = MagicMock()
        mock_result.phone_numbers = ["+380501234567", "+380671234567"]
        mock_result.viber_link = None
        mock_extract.return_value = mock_result

        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        result = store_ad_phones("https://example.com/ad/123", ad_id=42)
        assert result == 2
        assert mock_ad_repo.add_phone.call_count == 2

    @patch("common.db.operations.AdRepository")
    @patch("common.db.operations.db_session")
    def test_ad_not_found_returns_zero(self, mock_db_session, mock_ad_repo):
        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ad_repo.get_by_id.return_value = None

        result = store_ad_phones("https://example.com/ad/123", ad_id=999)
        assert result == 0


# ── list_subscriptions() ────────────────────────────────────────────────────


class TestListSubscriptions:
    @patch("common.db.operations.SubscriptionCacheManager")
    def test_cache_hit_returns_cached(self, mock_cache):
        mock_cache.get_user_subscriptions.return_value = [{"id": 1, "city": "Київ"}]

        result = list_subscriptions(1)
        assert result == [{"id": 1, "city": "Київ"}]

    @patch("common.db.operations.SubscriptionCacheManager")
    @patch("common.db.operations.SubscriptionRepository")
    @patch("common.db.operations.db_session")
    def test_cache_miss_queries_db(self, mock_db_session, mock_sub_repo, mock_cache):
        mock_cache.get_user_subscriptions.return_value = None

        mock_db = MagicMock()
        mock_db_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_sub_repo.list_subscriptions.return_value = [{"id": 2, "city": "Львів"}]

        result = list_subscriptions(1)
        assert result == [{"id": 2, "city": "Львів"}]
        mock_cache.set_user_subscriptions.assert_called_once()

    @patch("common.db.operations.SubscriptionCacheManager")
    @patch("common.db.operations.db_session")
    def test_error_returns_empty(self, mock_db_session, mock_cache):
        mock_cache.get_user_subscriptions.return_value = None
        mock_db_session.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_session.return_value.__exit__ = MagicMock(return_value=False)

        result = list_subscriptions(1)
        assert result == []
