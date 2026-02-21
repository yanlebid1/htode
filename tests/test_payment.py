# tests/test_payment.py

import os
import pytest
import hmac
import hashlib
from unittest.mock import patch, MagicMock

# Ensure payment env vars are set before import
os.environ.setdefault("WAYFORPAY_MERCHANT_LOGIN", "test_merchant_login")
os.environ.setdefault("WAYFORPAY_MERCHANT_SECRET", "test_merchant_secret_key")


class TestGenerateSignature:
    """Tests for WayForPay HMAC signature generation."""

    def test_deterministic(self):
        """Same data produces same signature."""
        from services.telegram_service.app.payment.wayforpay import generate_signature

        data = {"amount": "100", "orderReference": "order_1", "merchantAccount": "test"}
        sig1 = generate_signature(data)
        sig2 = generate_signature(data)
        assert sig1 == sig2

    def test_changes_with_data(self):
        """Different data produces different signatures."""
        from services.telegram_service.app.payment.wayforpay import generate_signature

        sig1 = generate_signature({"amount": "100", "order": "a"})
        sig2 = generate_signature({"amount": "200", "order": "a"})
        assert sig1 != sig2

    def test_key_ordering(self):
        """Signature is based on sorted keys, so order doesn't matter."""
        from services.telegram_service.app.payment.wayforpay import generate_signature

        data_ordered = {"a_key": "1", "b_key": "2", "c_key": "3"}
        data_reversed = {"c_key": "3", "a_key": "1", "b_key": "2"}
        assert generate_signature(data_ordered) == generate_signature(data_reversed)

    def test_returns_hex_string(self):
        """Signature is a 32-char hex string (MD5)."""
        from services.telegram_service.app.payment.wayforpay import generate_signature

        sig = generate_signature({"key": "value"})
        assert len(sig) == 32
        assert all(c in "0123456789abcdef" for c in sig)


class TestCreatePaymentRequest:
    """Tests for create_payment_request()."""

    def test_correct_structure(self):
        """Payment request contains all required fields."""
        from services.telegram_service.app.payment.wayforpay import create_payment_request

        request = create_payment_request(
            user_id=42, amount=199.0, order_id="sub_42_test", product_name="Monthly"
        )
        assert request["amount"] == 199.0
        assert request["orderReference"] == "sub_42_test"
        assert request["currency"] == "UAH"
        assert "productName" in request
        assert "productCount" in request
        assert "productPrice" in request
        assert request["clientFirstName"] == "User42"

    def test_includes_signature(self):
        """Payment request includes a generated merchantSignature."""
        from services.telegram_service.app.payment.wayforpay import create_payment_request

        request = create_payment_request(
            user_id=1, amount=100.0, order_id="test_order", product_name="Sub"
        )
        assert "merchantSignature" in request
        assert len(request["merchantSignature"]) == 32


class TestVerifyPaymentCallback:
    """Tests for verify_payment_callback()."""

    def _make_callback_data(self, status="Approved"):
        """Helper to construct valid callback data."""
        from services.telegram_service.app.payment.wayforpay import (
            generate_signature,
            MERCHANT_ACCOUNT,
        )

        data = {
            "merchantAccount": MERCHANT_ACCOUNT,
            "orderReference": "test_order_123",
            "amount": "100.0",
            "transactionStatus": status,
        }
        data["merchantSignature"] = generate_signature(data)
        return data

    def test_valid_callback(self):
        """Valid approved callback returns True."""
        from services.telegram_service.app.payment.wayforpay import verify_payment_callback

        data = self._make_callback_data(status="Approved")
        assert verify_payment_callback(data) is True

    def test_invalid_signature(self):
        """Tampered signature returns False."""
        from services.telegram_service.app.payment.wayforpay import verify_payment_callback

        data = self._make_callback_data()
        data["merchantSignature"] = "00000000000000000000000000000000"
        assert verify_payment_callback(data) is False

    def test_wrong_status(self):
        """Non-approved status returns False (even with valid signature)."""
        from services.telegram_service.app.payment.wayforpay import verify_payment_callback

        data = self._make_callback_data(status="Declined")
        assert verify_payment_callback(data) is False

    def test_missing_signature(self):
        """Callback with no merchantSignature returns False."""
        from services.telegram_service.app.payment.wayforpay import verify_payment_callback

        data = {
            "merchantAccount": "test",
            "orderReference": "ord",
            "transactionStatus": "Approved",
        }
        assert verify_payment_callback(data) is False
