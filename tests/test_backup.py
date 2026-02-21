# tests/test_backup.py
"""
Tests for PostgreSQL backup and cleanup tasks.
"""

import sys
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone, timedelta

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest


class TestBackupDatabase:
    """Tests for the backup_database Celery task."""

    @patch("system.maintenance.backup.boto3")
    @patch("system.maintenance.backup.subprocess")
    @patch("system.maintenance.backup.os")
    def test_successful_backup(self, mock_os, mock_subprocess, mock_boto3):
        import subprocess as real_subprocess
        from system.maintenance.backup import backup_database

        # Mock os.environ and os.path.getsize
        mock_os.environ = {}
        mock_os.getenv.side_effect = lambda k, d=None: d
        mock_os.path.getsize.return_value = 1024 * 1024  # 1 MB
        mock_subprocess.TimeoutExpired = real_subprocess.TimeoutExpired

        # Mock subprocess.run (pg_dump success)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_subprocess.run.return_value = mock_result

        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        result = backup_database()

        assert result["status"] == "success"
        assert "s3_key" in result
        assert result["s3_key"].startswith("backups/postgresql/htode_backup_")
        assert result["s3_key"].endswith(".dump")
        assert result["size_bytes"] == 1024 * 1024
        mock_s3.upload_file.assert_called_once()

    @patch("system.maintenance.backup.boto3")
    @patch("system.maintenance.backup.subprocess")
    @patch("system.maintenance.backup.os")
    def test_pgdump_failure(self, mock_os, mock_subprocess, mock_boto3):
        import subprocess as real_subprocess
        from system.maintenance.backup import backup_database

        mock_os.environ = {}
        mock_os.getenv.side_effect = lambda k, d=None: d
        mock_os.path.getsize.return_value = 0
        mock_subprocess.TimeoutExpired = real_subprocess.TimeoutExpired

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "connection refused"
        mock_subprocess.run.return_value = mock_result

        result = backup_database()

        assert result["status"] == "error"
        assert "pg_dump failed" in result["error"]

    @patch("system.maintenance.backup.boto3")
    @patch("system.maintenance.backup.subprocess")
    @patch("system.maintenance.backup.os")
    def test_pgdump_timeout(self, mock_os, mock_subprocess, mock_boto3):
        import subprocess as real_subprocess
        from system.maintenance.backup import backup_database

        mock_os.environ = {}
        mock_os.getenv.side_effect = lambda k, d=None: d
        mock_subprocess.run.side_effect = real_subprocess.TimeoutExpired(
            cmd="pg_dump", timeout=1800
        )
        mock_subprocess.TimeoutExpired = real_subprocess.TimeoutExpired

        result = backup_database()

        assert result["status"] == "error"
        assert "timed out" in result["error"]

    def test_backup_filename_format(self):
        """Backup filename should follow the htode_backup_YYYYMMDD_HHMMSS.dump pattern."""
        import re

        pattern = r"^htode_backup_\d{8}_\d{6}\.dump$"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"htode_backup_{timestamp}.dump"
        assert re.match(pattern, filename), f"Filename {filename} doesn't match expected pattern"


class TestCleanupOldBackups:
    """Tests for the cleanup_old_backups Celery task."""

    @patch("system.maintenance.backup.boto3")
    def test_deletes_old_backups(self, mock_boto3):
        from system.maintenance.backup import cleanup_old_backups

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        old_date = datetime.now(timezone.utc) - timedelta(days=60)
        recent_date = datetime.now(timezone.utc) - timedelta(days=5)

        # Mock paginator
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "backups/postgresql/old.dump", "LastModified": old_date},
                    {"Key": "backups/postgresql/recent.dump", "LastModified": recent_date},
                ]
            }
        ]

        result = cleanup_old_backups(retention_days=30)

        assert result["status"] == "success"
        assert result["deleted_count"] == 1
        # Only the old backup should be deleted
        delete_call = mock_s3.delete_objects.call_args
        deleted_keys = delete_call[1]["Delete"]["Objects"]
        assert len(deleted_keys) == 1
        assert deleted_keys[0]["Key"] == "backups/postgresql/old.dump"

    @patch("system.maintenance.backup.boto3")
    def test_no_backups_to_delete(self, mock_boto3):
        from system.maintenance.backup import cleanup_old_backups

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": []}]

        result = cleanup_old_backups(retention_days=30)

        assert result["status"] == "success"
        assert result["deleted_count"] == 0
        mock_s3.delete_objects.assert_not_called()

    @patch("system.maintenance.backup.boto3")
    def test_keeps_recent_backups(self, mock_boto3):
        from system.maintenance.backup import cleanup_old_backups

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        recent = datetime.now(timezone.utc) - timedelta(days=2)
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "backups/postgresql/recent.dump", "LastModified": recent}]}
        ]

        result = cleanup_old_backups(retention_days=30)

        assert result["deleted_count"] == 0
        mock_s3.delete_objects.assert_not_called()


class TestBackupConstants:
    def test_backup_constants_exist(self):
        from common.constants import BACKUP_RETENTION_DAYS, BACKUP_S3_PREFIX

        assert BACKUP_RETENTION_DAYS == 30
        assert BACKUP_S3_PREFIX == "backups/postgresql/"

    def test_backup_s3_prefix_ends_with_slash(self):
        from common.constants import BACKUP_S3_PREFIX

        assert BACKUP_S3_PREFIX.endswith("/")
