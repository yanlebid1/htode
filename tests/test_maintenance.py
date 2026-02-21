# tests/test_maintenance.py

import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# The maintenance module has a deep import chain that pulls in selenium, geoip2,
# etc. via system.maintenance.__init__ -> .cache -> common.db.operations -> phone_utils.
# Instead of trying to import the full module, we import just cleanup directly
# by pre-mocking the problematic transitive imports.

# Mock the adspower_manager that requires selenium
_adspower_mock = MagicMock()
_adspower_mock.adspower_manager = MagicMock()
sys.modules["common.utils.phone_utils.adspower_manager"] = _adspower_mock

# Now import cleanup directly (bypassing __init__.py which imports other modules)
import system.maintenance.cleanup


class TestCleanupOldAds:
    """Tests for the cleanup_old_ads maintenance task."""

    @patch("system.maintenance.cleanup.clear_ad_cache")
    @patch("system.maintenance.cleanup.delete_s3_image", return_value=True)
    @patch("system.maintenance.cleanup.db_session")
    @patch("system.maintenance.cleanup.AdRepository")
    def test_cleanup_deletes_inactive_ads(
        self, mock_repo, mock_db_ctx, mock_s3, mock_cache
    ):
        """Test that inactive ads are deleted with their S3 images."""
        from system.maintenance.cleanup import cleanup_old_ads

        mock_ad = MagicMock()
        mock_ad.id = 1
        mock_ad.resource_url = "https://example.com/ad/1"

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_repo.get_older_than.return_value = [mock_ad]
        mock_repo.get_ad_images.return_value = ["https://s3/img1.jpg", "https://s3/img2.jpg"]
        mock_repo.delete_with_related.return_value = True

        with patch("common.services.ad_service.AdService.is_ad_inactive", return_value=True):
            result = cleanup_old_ads(days_old=30, check_activity=True)

        assert result["status"] == "completed"
        assert result["ads_deleted"] == 1
        assert result["images_deleted"] == 2

    @patch("system.maintenance.cleanup.clear_ad_cache")
    @patch("system.maintenance.cleanup.db_session")
    @patch("system.maintenance.cleanup.AdRepository")
    def test_cleanup_skips_active_ads(self, mock_repo, mock_db_ctx, mock_cache):
        """Test that active ads are not deleted when check_activity=True."""
        from system.maintenance.cleanup import cleanup_old_ads

        mock_ad = MagicMock()
        mock_ad.id = 1
        mock_ad.resource_url = "https://example.com/ad/1"

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_repo.get_older_than.return_value = [mock_ad]

        with patch("common.services.ad_service.AdService.is_ad_inactive", return_value=False):
            result = cleanup_old_ads(days_old=30, check_activity=True)

        assert result["status"] == "completed"
        assert result["ads_deleted"] == 0

    @patch("system.maintenance.cleanup.db_session")
    def test_cleanup_handles_db_error(self, mock_db_ctx):
        """Test that database errors are handled gracefully."""
        from system.maintenance.cleanup import cleanup_old_ads

        mock_db_ctx.return_value.__enter__ = MagicMock(side_effect=Exception("DB connection error"))
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_old_ads(days_old=30)

        assert result["status"] == "error"
        assert "DB connection error" in result["error"]


class TestCleanupExpiredVerificationCodes:
    """Tests for cleanup_expired_verification_codes."""

    @patch("system.maintenance.cleanup.db_session")
    def test_cleanup_expired_codes(self, mock_db_ctx):
        """Test that expired verification codes and email tokens are cleaned up."""
        from system.maintenance.cleanup import cleanup_expired_verification_codes

        mock_db = MagicMock()
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # Mock the query chain for verification codes
        mock_db.query.return_value.filter.return_value.delete.return_value = 5

        # Mock the execute for email tokens
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 3
        mock_db.execute.return_value = mock_execute_result

        result = cleanup_expired_verification_codes()

        assert result["verification_codes_deleted"] == 5
        assert result["email_tokens_deleted"] == 3

    @patch("system.maintenance.cleanup.db_session")
    def test_cleanup_handles_error(self, mock_db_ctx):
        """Test that errors are handled gracefully."""
        from system.maintenance.cleanup import cleanup_expired_verification_codes

        mock_db_ctx.return_value.__enter__ = MagicMock(side_effect=Exception("DB error"))
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = cleanup_expired_verification_codes()

        assert result["verification_codes_deleted"] == 0
        assert result["email_tokens_deleted"] == 0
        assert "error" in result
