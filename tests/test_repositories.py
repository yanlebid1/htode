# tests/test_repositories.py

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from common.db.models.user import User
from common.db.models.ad import Ad, AdImage, AdPhone
from common.db.models.payment import Payment
from common.db.models.favorite import FavoriteAd


# ── UserRepository ──────────────────────────────────────────────────────────


class TestUserRepository:
    """Tests for UserRepository using in-memory SQLite."""

    def _create_user(self, db, telegram_id="123456", **kwargs):
        user = User(telegram_id=telegram_id, **kwargs)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def test_create_user(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        user = UserRepository.create_user(
            db_session, {"telegram_id": "tg_user_1", "email": "test@example.com"}
        )
        assert user.id is not None
        assert user.telegram_id == "tg_user_1"
        assert user.email == "test@example.com"

    def test_get_by_id_found(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        user = self._create_user(db_session)
        found = UserRepository.get_by_id(db_session, user.id)
        assert found is not None
        assert found.id == user.id

    def test_get_by_id_not_found(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        found = UserRepository.get_by_id(db_session, 99999)
        assert found is None

    def test_get_by_messenger_id(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        self._create_user(db_session, telegram_id="tg_test_42")
        found = UserRepository.get_by_messenger_id(db_session, "tg_test_42", "telegram")
        assert found is not None
        assert found.telegram_id == "tg_test_42"

    def test_get_by_phone(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        self._create_user(db_session, telegram_id="ph_user", phone_number="+380501234567")
        found = UserRepository.get_by_phone(db_session, "+380501234567")
        assert found is not None
        assert found.phone_number == "+380501234567"

    def test_get_by_email(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        self._create_user(db_session, telegram_id="em_user", email="user@test.com")
        found = UserRepository.get_by_email(db_session, "user@test.com")
        assert found is not None

    def test_start_free_subscription(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        user = self._create_user(db_session, telegram_id="sub_user")
        result = UserRepository.start_free_subscription(db_session, user.id)
        assert result is True

        db_session.refresh(user)
        assert user.free_until is not None
        # SQLite returns naive datetimes; normalize for comparison
        free_until = user.free_until
        if free_until.tzinfo is None:
            free_until = free_until.replace(tzinfo=timezone.utc)
        assert free_until > datetime.now(timezone.utc)

    def test_start_free_subscription_user_not_found(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        result = UserRepository.start_free_subscription(db_session, 99999)
        assert result is False

    def test_get_subscription_status(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        user = self._create_user(
            db_session,
            telegram_id="stat_user",
            free_until=datetime.now(timezone.utc) + timedelta(days=5),
        )
        status = UserRepository.get_subscription_status(db_session, user.id)
        assert status["active"] is True
        assert status["free_active"] is True

    def test_get_subscription_status_user_not_found(self, db_session):
        from common.db.repositories.user_repository import UserRepository

        status = UserRepository.get_subscription_status(db_session, 99999)
        assert status["active"] is False


# ── AdRepository ─────────────────────────────────────────────────────────────


class TestAdRepository:
    """Tests for AdRepository using in-memory SQLite."""

    def _create_ad(self, db, external_id="ext_1", **kwargs):
        defaults = {
            "external_id": external_id,
            "property_type": "apartment",
            "city": 10009580,
            "address": "Test St 1",
            "price": 5000,
            "rooms_count": 2,
            "floor": 3,
            "total_floors": 9,
            "resource_url": f"https://example.com/{external_id}",
        }
        defaults.update(kwargs)
        ad = Ad(**defaults)
        db.add(ad)
        db.commit()
        db.refresh(ad)
        return ad

    def test_create_ad(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = AdRepository.create_ad(
            db_session,
            {
                "external_id": "new_ad_1",
                "property_type": "house",
                "city": 10012684,
                "price": 10000,
                "resource_url": "https://example.com/new_ad_1",
            },
        )
        assert ad.id is not None
        assert ad.external_id == "new_ad_1"

    def test_create_ad_duplicate_returns_existing(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad1 = AdRepository.create_ad(
            db_session,
            {
                "external_id": "dup_ad",
                "property_type": "apartment",
                "price": 5000,
                "resource_url": "https://example.com/dup_ad",
            },
        )
        ad2 = AdRepository.create_ad(
            db_session,
            {
                "external_id": "dup_ad",
                "property_type": "apartment",
                "price": 6000,
                "resource_url": "https://example.com/dup_ad_2",
            },
        )
        assert ad1.id == ad2.id

    def test_get_by_id(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="get_id_ad")
        found = AdRepository.get_by_id(db_session, ad.id)
        assert found is not None
        assert found.external_id == "get_id_ad"

    def test_get_by_external_id(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="ext_lookup")
        found = AdRepository.get_by_external_id(db_session, "ext_lookup")
        assert found is not None
        assert found.id == ad.id

    def test_get_by_resource_url(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(
            db_session,
            external_id="url_ad",
            resource_url="https://olx.ua/d/ad/123",
        )
        found = AdRepository.get_by_resource_url(db_session, "https://olx.ua/d/ad/123")
        assert found is not None
        assert found.id == ad.id

    def test_update_ad(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="upd_ad", price=5000)
        updated = AdRepository.update_ad(db_session, ad.id, {"price": 7000})
        assert updated is not None
        assert float(updated.price) == 7000.0

    def test_delete_ad(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="del_ad")
        assert AdRepository.delete_ad(db_session, ad.id) is True
        assert AdRepository.get_by_id(db_session, ad.id) is None

    def test_get_ads_by_filter_price_range(self, db_session):
        from common.db.repositories.ad_repository import AdRepository

        self._create_ad(db_session, external_id="cheap", price=3000)
        self._create_ad(db_session, external_id="mid", price=6000)
        self._create_ad(db_session, external_id="expensive", price=15000)

        ads = AdRepository.get_ads_by_filter(
            db_session, {"price_min": 4000, "price_max": 10000}
        )
        assert len(ads) == 1
        assert ads[0].external_id == "mid"

    @patch("common.db.repositories.ad_repository.invalidate_ad_caches")
    def test_add_image(self, mock_invalidate, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="img_ad")
        image = AdRepository.add_image(db_session, ad.id, "https://s3/img.jpg")
        assert image.id is not None
        assert image.ad_id == ad.id
        assert image.image_url == "https://s3/img.jpg"

    @patch("common.db.repositories.ad_repository.invalidate_ad_caches")
    def test_add_phone(self, mock_invalidate, db_session):
        from common.db.repositories.ad_repository import AdRepository

        ad = self._create_ad(db_session, external_id="phone_ad")
        phone = AdRepository.add_phone(
            db_session, ad.id, "+380501234567", viber_link="viber://add?number=380501234567"
        )
        assert phone.id is not None
        assert phone.phone == "+380501234567"
        assert phone.viber_link is not None


# ── FavoriteRepository ───────────────────────────────────────────────────────


class TestFavoriteRepository:
    """Tests for FavoriteRepository using in-memory SQLite."""

    def _create_user_and_ad(self, db):
        user = User(telegram_id="fav_user")
        db.add(user)
        db.flush()
        ad = Ad(
            external_id="fav_ad",
            property_type="apartment",
            price=5000,
            resource_url="https://example.com/fav_ad",
        )
        db.add(ad)
        db.commit()
        db.refresh(user)
        db.refresh(ad)
        return user, ad

    def test_add_favorite(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        user, ad = self._create_user_and_ad(db_session)
        fav = FavoriteRepository.add_favorite(db_session, user.id, ad.id)
        assert fav is not None
        assert fav.user_id == user.id
        assert fav.ad_id == ad.id

    def test_add_favorite_duplicate_returns_existing(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        user, ad = self._create_user_and_ad(db_session)
        fav1 = FavoriteRepository.add_favorite(db_session, user.id, ad.id)
        fav2 = FavoriteRepository.add_favorite(db_session, user.id, ad.id)
        assert fav1.id == fav2.id

    def test_add_favorite_exceeds_limit(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        user = User(telegram_id="limit_user")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Add 50 favorites
        for i in range(50):
            ad = Ad(
                external_id=f"limit_ad_{i}",
                property_type="apartment",
                price=1000,
                resource_url=f"https://example.com/limit_{i}",
            )
            db_session.add(ad)
            db_session.commit()
            db_session.refresh(ad)
            FavoriteRepository.add_favorite(db_session, user.id, ad.id)

        # 51st should raise
        ad_51 = Ad(
            external_id="limit_ad_51",
            property_type="apartment",
            price=1000,
            resource_url="https://example.com/limit_51",
        )
        db_session.add(ad_51)
        db_session.commit()
        db_session.refresh(ad_51)

        with pytest.raises(ValueError, match="50"):
            FavoriteRepository.add_favorite(db_session, user.id, ad_51.id)

    def test_remove_favorite(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        user, ad = self._create_user_and_ad(db_session)
        FavoriteRepository.add_favorite(db_session, user.id, ad.id)
        result = FavoriteRepository.remove_favorite(db_session, user.id, ad.id)
        assert result is True

    def test_remove_nonexistent_favorite(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        result = FavoriteRepository.remove_favorite(db_session, 999, 999)
        assert result is False

    def test_list_favorites(self, db_session):
        from common.db.repositories.favorite_repository import FavoriteRepository

        user, ad = self._create_user_and_ad(db_session)
        FavoriteRepository.add_favorite(db_session, user.id, ad.id)
        favorites = FavoriteRepository.list_favorites(db_session, user.id)
        assert len(favorites) == 1
        assert favorites[0]["ad_id"] == ad.id


# ── PaymentRepository ────────────────────────────────────────────────────────


class TestPaymentRepository:
    """Tests for PaymentRepository using in-memory SQLite."""

    def _create_user(self, db):
        user = User(telegram_id="pay_user")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def test_create_payment(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        payment = PaymentRepository.create_payment(
            db_session, user.id, "order_001", 100.0, "1 month"
        )
        assert payment.id is not None
        assert payment.status == "pending"
        assert payment.order_id == "order_001"
        assert float(payment.amount) == 100.0

    def test_get_payment_by_order_id(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        PaymentRepository.create_payment(
            db_session, user.id, "order_find", 50.0, "1 week"
        )
        found = PaymentRepository.get_payment_by_order_id(db_session, "order_find")
        assert found is not None
        assert found.order_id == "order_find"

    def test_get_payment_by_order_id_not_found(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        found = PaymentRepository.get_payment_by_order_id(db_session, "nonexistent")
        assert found is None

    def test_update_payment_status(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        PaymentRepository.create_payment(
            db_session, user.id, "order_upd", 200.0, "1 month"
        )
        updated = PaymentRepository.update_payment_status(
            db_session,
            "order_upd",
            "completed",
            transaction_id="txn_123",
            card_mask="****5678",
        )
        assert updated is not None
        assert updated.status == "completed"
        assert updated.transaction_id == "txn_123"
        assert updated.card_mask == "****5678"
        assert updated.completed_at is not None

    def test_get_user_payments_filtered_by_status(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        PaymentRepository.create_payment(
            db_session, user.id, "ord_a", 100.0, "1 month"
        )
        PaymentRepository.create_payment(
            db_session, user.id, "ord_b", 200.0, "1 month"
        )
        PaymentRepository.update_payment_status(db_session, "ord_a", "completed")

        pending = PaymentRepository.get_user_payments(
            db_session, user.id, status="pending"
        )
        assert len(pending) == 1
        assert pending[0].order_id == "ord_b"

    def test_cleanup_expired_pending_payments(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        # Create an old pending payment
        payment = Payment(
            user_id=user.id,
            order_id="old_order",
            amount=100.0,
            period="1 month",
            status="pending",
            created_at=datetime.now(timezone.utc) - timedelta(hours=48),
        )
        db_session.add(payment)
        db_session.commit()

        count = PaymentRepository.cleanup_expired_pending_payments(db_session, hours=24)
        assert count == 1

        db_session.refresh(payment)
        assert payment.status == "expired"

    def test_get_payment_statistics(self, db_session):
        from common.db.repositories.payment_repository import PaymentRepository

        user = self._create_user(db_session)
        PaymentRepository.create_payment(
            db_session, user.id, "stat_1", 100.0, "1 month"
        )
        PaymentRepository.create_payment(
            db_session, user.id, "stat_2", 200.0, "1 month"
        )
        PaymentRepository.update_payment_status(db_session, "stat_1", "completed")

        stats = PaymentRepository.get_payment_statistics(db_session, user.id)
        assert stats["total_payments"] == 2
        assert stats["completed"] == 1
        assert stats["pending"] == 1
        assert stats["total_spent"] == 100.0
