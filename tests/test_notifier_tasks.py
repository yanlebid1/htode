# tests/test_notifier_tasks.py

import sys
from unittest.mock import patch, MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
# common.utils.phone_utils.adspower_manager imports selenium at module level
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from common.constants import NOTIFICATION_BATCH_SIZE


# ── get_ad_images_local() ───────────────────────────────────────────────────


class TestGetAdImagesLocal:
    @patch("services.notifier_service.app.tasks.utils_get_ad_images")
    def test_returns_images(self, mock_get_images):
        from services.notifier_service.app.tasks import get_ad_images_local

        mock_get_images.return_value = ["img1.jpg", "img2.jpg"]
        result = get_ad_images_local({"id": 42})
        assert result == ["img1.jpg", "img2.jpg"]
        mock_get_images.assert_called_once_with(42)

    @patch("services.notifier_service.app.tasks.utils_get_ad_images")
    def test_handles_none(self, mock_get_images):
        from services.notifier_service.app.tasks import get_ad_images_local

        mock_get_images.return_value = None
        result = get_ad_images_local({"id": 42})
        assert result is None


# ── insert_ad() ─────────────────────────────────────────────────────────────


class TestInsertAd:
    @patch("services.notifier_service.app.tasks.process_and_insert_ad")
    def test_delegates_to_process_and_insert(self, mock_insert):
        from services.notifier_service.app.tasks import insert_ad

        mock_insert.return_value = 99
        result = insert_ad({"id": 1}, "apartment", 10009580)
        assert result == 99
        mock_insert.assert_called_once_with({"id": 1}, "apartment", 10009580)


# ── sort_and_notify_new_ads() ───────────────────────────────────────────────


class TestSortAndNotifyNewAds:
    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.find_users_for_ad")
    @patch("services.notifier_service.app.tasks.get_ad_images_local")
    def test_dispatches_batch_tasks(self, mock_images, mock_find_users, mock_celery):
        from services.notifier_service.app.tasks import sort_and_notify_new_ads

        mock_images.return_value = ["img.jpg"]
        mock_find_users.return_value = [100, 200, 300]

        ad = {
            "id": 1,
            "external_id": "ext1",
            "price": 5000,
            "city": "Kyiv",
            "address": "Test St",
            "rooms_count": 2,
            "square_feet": 50,
            "floor": 3,
            "total_floors": 9,
            "resource_url": "https://example.com",
        }

        sort_and_notify_new_ads([ad])
        mock_celery.send_task.assert_called()
        # Verify it was called with notification queue
        call_kwargs = mock_celery.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "notification_queue"

    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.find_users_for_ad")
    @patch("services.notifier_service.app.tasks.get_ad_images_local")
    def test_no_users_no_tasks_dispatched(self, mock_images, mock_find_users, mock_celery):
        from services.notifier_service.app.tasks import sort_and_notify_new_ads

        mock_images.return_value = ["img.jpg"]
        mock_find_users.return_value = []

        ad = {"id": 1, "external_id": "ext1", "price": 5000, "city": "Kyiv",
              "address": "a", "rooms_count": 2, "square_feet": 50,
              "floor": 3, "total_floors": 9, "resource_url": "https://example.com"}

        sort_and_notify_new_ads([ad])
        mock_celery.send_task.assert_not_called()

    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.find_users_for_ad")
    @patch("services.notifier_service.app.tasks.get_ad_images_local")
    def test_respects_batch_size(self, mock_images, mock_find_users, mock_celery):
        from services.notifier_service.app.tasks import sort_and_notify_new_ads

        mock_images.return_value = ["img.jpg"]
        # Create more users than NOTIFICATION_BATCH_SIZE
        users = list(range(NOTIFICATION_BATCH_SIZE + 10))
        mock_find_users.return_value = users

        ad = {"id": 1, "external_id": "ext1", "price": 5000, "city": "Kyiv",
              "address": "a", "rooms_count": 2, "square_feet": 50,
              "floor": 3, "total_floors": 9, "resource_url": "https://example.com"}

        sort_and_notify_new_ads([ad])
        # Should be called at least 2 times (users > batch size)
        assert mock_celery.send_task.call_count >= 2

    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.find_users_for_ad")
    @patch("services.notifier_service.app.tasks.get_ad_images_local")
    def test_multiple_ads_each_dispatched(self, mock_images, mock_find_users, mock_celery):
        from services.notifier_service.app.tasks import sort_and_notify_new_ads

        mock_images.return_value = ["img.jpg"]
        mock_find_users.return_value = [100]

        ads = [
            {"id": i, "external_id": f"ext{i}", "price": 5000, "city": "Kyiv",
             "address": "a", "rooms_count": 2, "square_feet": 50,
             "floor": 3, "total_floors": 9, "resource_url": f"https://example.com/{i}"}
            for i in range(3)
        ]

        sort_and_notify_new_ads(ads)
        assert mock_celery.send_task.call_count == 3

    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.find_users_for_ad")
    @patch("services.notifier_service.app.tasks.get_ad_images_local")
    def test_exception_in_one_ad_doesnt_stop_others(self, mock_images, mock_find_users, mock_celery):
        from services.notifier_service.app.tasks import sort_and_notify_new_ads

        mock_images.return_value = ["img.jpg"]
        mock_find_users.side_effect = [Exception("boom"), [100]]

        ads = [
            {"id": 1, "external_id": "ext1", "price": 5000, "city": "Kyiv",
             "address": "a", "rooms_count": 2, "square_feet": 50,
             "floor": 3, "total_floors": 9, "resource_url": "https://example.com/1"},
            {"id": 2, "external_id": "ext2", "price": 5000, "city": "Kyiv",
             "address": "a", "rooms_count": 2, "square_feet": 50,
             "floor": 3, "total_floors": 9, "resource_url": "https://example.com/2"},
        ]

        # Should not raise — first ad fails, second succeeds
        sort_and_notify_new_ads(ads)
        # Second ad should still dispatch
        assert mock_celery.send_task.call_count == 1


# ── _notify_user_about_ad() ────────────────────────────────────────────────


class TestNotifyUserAboutAd:
    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.build_ad_text")
    def test_sends_celery_task_with_correct_args(self, mock_build, mock_celery):
        from services.notifier_service.app.tasks import _notify_user_about_ad

        mock_build.return_value = "Ad text here"

        ad = {"id": 1, "external_id": "ext1", "resource_url": "https://example.com"}
        _notify_user_about_ad(user_id=100, ad=ad, s3_image_urls="img.jpg")

        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "common.messaging.tasks.send_ad_with_extra_buttons"
        args = call_args.kwargs.get("args") or call_args[1].get("args")
        assert args[0] == 100  # user_id
        assert args[1] == "Ad text here"
        assert args[2] == "img.jpg"


# ── notify_user_with_ads() ──────────────────────────────────────────────────


class TestNotifyUserWithAds:
    @patch("services.notifier_service.app.tasks.celery_app")
    @patch("services.notifier_service.app.tasks.build_ad_text")
    @patch("services.notifier_service.app.tasks.utils_get_ad_images")
    @patch("services.notifier_service.app.tasks.process_and_insert_ad")
    @patch("services.notifier_service.app.tasks.fetch_ads_flatfy")
    @patch("services.notifier_service.app.tasks.get_key_by_value")
    def test_fetches_and_sends(self, mock_geo, mock_fetch, mock_insert, mock_images,
                                mock_build, mock_celery):
        from services.notifier_service.app.tasks import notify_user_with_ads

        mock_geo.return_value = 10009580
        mock_fetch.return_value = [
            {"id": 1, "price": 5000, "header": "Nice apt", "room_count": 2,
             "area_total": 50, "floor": 3, "floor_count": 9}
        ]
        mock_insert.return_value = 42
        mock_images.return_value = ["s3_img.jpg"]
        mock_build.return_value = "Formatted ad"

        filters = {"city": "Київ", "rooms": "2", "price_min": 3000, "price_max": 7000}
        notify_user_with_ads(telegram_id=12345, user_filters=filters)

        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        args = call_args.kwargs.get("args") or call_args[1].get("args")
        assert args[0] == 12345  # telegram_id

    @patch("services.notifier_service.app.tasks.fetch_ads_flatfy")
    @patch("services.notifier_service.app.tasks.get_key_by_value")
    def test_no_data_returns_early(self, mock_geo, mock_fetch):
        from services.notifier_service.app.tasks import notify_user_with_ads

        mock_geo.return_value = 10009580
        mock_fetch.return_value = []

        filters = {"city": "Київ"}
        # Should return without error
        notify_user_with_ads(telegram_id=12345, user_filters=filters)
