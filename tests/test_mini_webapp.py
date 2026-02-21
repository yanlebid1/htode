# tests/test_mini_webapp.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI app
from services.webapps.mini_webapp import (
    app,
    verify_wayforpay_signature,
    validate_telegram_init_data,
)

# Create a test client
client = TestClient(app)


def test_health_endpoint():
    """Test that the health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_gallery_endpoint():
    """Test that the gallery endpoint returns HTML."""
    response = client.get(
        "/gallery?images=https://example.com/image1.jpg,https://example.com/image2.jpg"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "Фотогалерея" in response.text
    assert "galleryDiv" in response.text


def test_phones_endpoint():
    """Test that the phones endpoint returns HTML."""
    response = client.get("/phones?numbers=1234567890,9876543210")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "Телефони" in response.text
    assert "phone-list" in response.text


def test_verify_wayforpay_signature_success():
    """Test that signature verification works correctly."""
    with patch("services.webapps.mini_webapp.MERCHANT_SECRET", "test_secret"), patch(
        "services.webapps.mini_webapp.MERCHANT_ACCOUNT", "test_account"
    ), patch("services.webapps.mini_webapp.hmac.new") as mock_hmac:
        # Mock the HMAC verification
        mock_hmac_instance = MagicMock()
        mock_hmac_instance.hexdigest.return_value = "valid_signature"
        mock_hmac.return_value = mock_hmac_instance

        data = {
            "merchantSignature": "valid_signature",
            "merchantAccount": "test_account",
            "orderReference": "test_order",
            "amount": 100.0,
        }

        assert verify_wayforpay_signature(data) is True


def test_verify_wayforpay_signature_failure():
    """Test that signature verification fails with invalid signature."""
    with patch("services.webapps.mini_webapp.MERCHANT_SECRET", "test_secret"), patch(
        "services.webapps.mini_webapp.MERCHANT_ACCOUNT", "test_account"
    ), patch("services.webapps.mini_webapp.hmac.new") as mock_hmac:
        # Mock the HMAC verification
        mock_hmac_instance = MagicMock()
        mock_hmac_instance.hexdigest.return_value = "valid_signature"
        mock_hmac.return_value = mock_hmac_instance

        data = {
            "merchantSignature": "invalid_signature",
            "merchantAccount": "test_account",
            "orderReference": "test_order",
            "amount": 100.0,
        }

        assert verify_wayforpay_signature(data) is False


@pytest.mark.asyncio
async def test_payment_callback_approved():
    """Test the payment callback endpoint with approved payment."""
    with patch(
        "services.webapps.mini_webapp.verify_wayforpay_signature", return_value=True
    ), patch("services.webapps.mini_webapp.process_approved_payment") as mock_process:
        payload = {
            "merchantSignature": "valid_signature",
            "merchantAccount": "test_account",
            "orderReference": "test_order",
            "transactionStatus": "Approved",
            "amount": 100.0,
            "authCode": "test_auth",
            "cardPan": "1234********5678",
        }

        response = client.post("/payment/callback", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "accept"
        assert mock_process.called


@pytest.mark.asyncio
async def test_payment_callback_not_approved():
    """Test the payment callback endpoint with non-approved payment."""
    with patch(
        "services.webapps.mini_webapp.verify_wayforpay_signature", return_value=True
    ), patch(
        "services.webapps.mini_webapp.update_non_approved_payment_status"
    ) as mock_update:
        payload = {
            "merchantSignature": "valid_signature",
            "merchantAccount": "test_account",
            "orderReference": "test_order",
            "transactionStatus": "Declined",
            "amount": 100.0,
            "authCode": "test_auth",
            "cardPan": "1234********5678",
        }

        response = client.post("/payment/callback", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"
        assert mock_update.called


def test_validate_telegram_init_data_valid():
    """Test Telegram initData validation with a valid hash."""
    import hashlib
    import hmac as hmac_mod
    from urllib.parse import urlencode

    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    # Build data pairs
    data_pairs = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": '{"id":123456789,"first_name":"Test","last_name":"User","username":"testuser"}',
        "auth_date": "1234567890",
    }

    # Compute expected hash
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data_pairs.items())
    )
    secret_key = hmac_mod.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac_mod.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    data_pairs["hash"] = expected_hash
    init_data = urlencode(data_pairs)

    with patch("services.webapps.mini_webapp.TELEGRAM_TOKEN", bot_token):
        assert validate_telegram_init_data(init_data) is True


def test_validate_telegram_init_data_invalid_hash():
    """Test Telegram initData validation rejects tampered hash."""
    from urllib.parse import urlencode

    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    data_pairs = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": '{"id":123456789}',
        "auth_date": "1234567890",
        "hash": "0000000000000000000000000000000000000000000000000000000000000000",
    }
    init_data = urlencode(data_pairs)

    with patch("services.webapps.mini_webapp.TELEGRAM_TOKEN", bot_token):
        assert validate_telegram_init_data(init_data) is False


def test_validate_telegram_init_data_missing_hash():
    """Test Telegram initData validation rejects data without hash."""
    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    init_data = "query_id=test&auth_date=1234567890"

    with patch("services.webapps.mini_webapp.TELEGRAM_TOKEN", bot_token):
        assert validate_telegram_init_data(init_data) is False


def test_validate_telegram_init_data_no_token():
    """Test Telegram initData validation fails when token is not configured."""
    init_data = "query_id=test&auth_date=1234567890&hash=abc"

    with patch("services.webapps.mini_webapp.TELEGRAM_TOKEN", ""):
        assert validate_telegram_init_data(init_data) is False


def test_gallery_contains_telegram_guard():
    """Test that gallery HTML includes Telegram WebApp guard."""
    response = client.get(
        "/gallery?images=https://example.com/image1.jpg"
    )
    assert response.status_code == 200
    assert "window.Telegram" in response.text
    assert "Ця сторінка доступна лише через Telegram" in response.text


def test_phones_contains_telegram_guard():
    """Test that phones HTML includes Telegram WebApp guard."""
    response = client.get("/phones?numbers=380999999999")
    assert response.status_code == 200
    assert "window.Telegram" in response.text
    assert "Ця сторінка доступна лише через Telegram" in response.text
