# tests/test_verification.py

import pytest
from unittest.mock import patch, MagicMock


# ── Email service tests ──────────────────────────────────────────────────────


class TestSendVerificationEmail:
    @patch("common.verification.email_service.smtplib.SMTP")
    @patch("common.verification.email_service.SMTP_PASSWORD", "pass")
    @patch("common.verification.email_service.SMTP_USERNAME", "user@test.com")
    @patch("common.verification.email_service.FROM_EMAIL", "user@test.com")
    def test_success_with_smtp(self, mock_smtp_cls):
        from common.verification.email_service import send_verification_email

        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        result = send_verification_email("recipient@test.com", "TOKEN123")
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("common.verification.email_service.SMTP_PASSWORD", None)
    @patch("common.verification.email_service.SMTP_USERNAME", None)
    def test_incomplete_config_returns_true(self):
        from common.verification.email_service import send_verification_email

        result = send_verification_email("test@test.com", "TOKEN")
        assert result is True  # skips send, returns True

    @patch("common.verification.email_service.smtplib.SMTP")
    @patch("common.verification.email_service.SMTP_PASSWORD", "pass")
    @patch("common.verification.email_service.SMTP_USERNAME", "user@test.com")
    @patch("common.verification.email_service.FROM_EMAIL", "user@test.com")
    def test_smtp_error_returns_false(self, mock_smtp_cls):
        from common.verification.email_service import send_verification_email

        mock_smtp_cls.side_effect = Exception("SMTP connection failed")
        result = send_verification_email("fail@test.com", "TOKEN")
        assert result is False


class TestSendVerificationEmailWithToken:
    @patch("common.verification.email_service.send_verification_email", return_value=True)
    @patch("common.verification.email_service.db_session")
    def test_success_creates_token_and_sends(self, mock_db_ctx, mock_send):
        from common.verification.email_service import send_verification_email_with_token

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.verification.email_service.VerificationRepository"
        ) as mock_repo:
            mock_repo.create_verification.return_value = "abc123"
            result = send_verification_email_with_token("test@email.com")
        assert result == "abc123"
        mock_send.assert_called_once()

    @patch(
        "common.verification.email_service.send_verification_email", return_value=False
    )
    @patch("common.verification.email_service.db_session")
    def test_send_failure_returns_none(self, mock_db_ctx, mock_send):
        from common.verification.email_service import send_verification_email_with_token

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.verification.email_service.VerificationRepository"
        ) as mock_repo:
            mock_repo.create_verification.return_value = "tok"
            result = send_verification_email_with_token("fail@email.com")
        assert result is None


class TestVerifyEmailToken:
    @patch("common.verification.email_service.db_session")
    def test_valid_token(self, mock_db_ctx):
        from common.verification.email_service import verify_email_token

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.verification.email_service.VerificationRepository"
        ) as mock_repo:
            mock_repo.verify_code.return_value = True
            result = verify_email_token("ok@email.com", "valid_token")
        assert result is True

    @patch("common.verification.email_service.db_session")
    def test_invalid_token(self, mock_db_ctx):
        from common.verification.email_service import verify_email_token

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.verification.email_service.VerificationRepository"
        ) as mock_repo:
            mock_repo.verify_code.return_value = False
            result = verify_email_token("bad@email.com", "wrong_token")
        assert result is False

    @patch("common.verification.email_service.db_session")
    def test_error_handling(self, mock_db_ctx):
        from common.verification.email_service import verify_email_token

        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB error")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = verify_email_token("err@email.com", "token")
        assert result is False


class TestEmailLinkMessengerAccount:
    def test_success_links_user(self):
        from common.verification.email_service import link_messenger_account

        mock_user = MagicMock()
        mock_user.id = 55
        with patch("common.db.operations.link_telegram_to_email", create=True, return_value=mock_user):
            result = link_messenger_account("user@email.com", "telegram", "tg_999")
        assert result == 55

    def test_user_not_found(self):
        from common.verification.email_service import link_messenger_account

        with patch("common.db.operations.link_telegram_to_email", create=True, return_value=None):
            result = link_messenger_account("none@email.com", "telegram", "tg_000")
        assert result is None


# ── Phone service tests ──────────────────────────────────────────────────────


class TestCreateVerificationCode:
    @patch("common.verification.phone_service.db_session")
    def test_creates_code_via_repository(self, mock_db_ctx):
        from common.verification.phone_service import create_verification_code

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "common.verification.phone_service.VerificationRepository"
        ) as mock_repo:
            mock_repo.create_verification.return_value = "123456"
            result = create_verification_code("+380501234567")
        assert result == "123456"


class TestGetUserByPhone:
    @patch("common.verification.phone_service.db_session")
    def test_found_returns_dict(self, mock_db_ctx):
        from common.verification.phone_service import get_user_by_phone

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.telegram_id = "tg_42"
        mock_user.phone_number = "+380501234567"
        mock_user.email = "test@test.com"

        with patch("common.verification.phone_service.UserRepository") as mock_repo:
            mock_repo.get_by_phone.return_value = mock_user
            result = get_user_by_phone("+380501234567")
        assert result["id"] == 42
        assert result["phone_number"] == "+380501234567"

    @patch("common.verification.phone_service.db_session")
    def test_not_found_returns_none(self, mock_db_ctx):
        from common.verification.phone_service import get_user_by_phone

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with patch("common.verification.phone_service.UserRepository") as mock_repo:
            mock_repo.get_by_phone.return_value = None
            result = get_user_by_phone("+380000000000")
        assert result is None

    @patch("common.verification.phone_service.db_session")
    def test_error_returns_none(self, mock_db_ctx):
        from common.verification.phone_service import get_user_by_phone

        mock_db_ctx.return_value.__enter__ = MagicMock(
            side_effect=Exception("DB down")
        )
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = get_user_by_phone("+380111111111")
        assert result is None


class TestPhoneLinkMessengerAccount:
    def test_success(self):
        from common.verification.phone_service import link_messenger_account

        mock_user = MagicMock()
        mock_user.id = 77
        with patch("common.db.operations.link_telegram_to_phone", create=True, return_value=mock_user):
            result = link_messenger_account("+380501234567", "telegram", "tg_77")
        assert result == 77

    def test_user_not_found(self):
        from common.verification.phone_service import link_messenger_account

        with patch("common.db.operations.link_telegram_to_phone", create=True, return_value=None):
            result = link_messenger_account("+380000000000", "telegram", "tg_00")
        assert result is None
