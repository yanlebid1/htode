#!/usr/bin/env python3
"""
Manual restore script: download a backup from S3 and restore with pg_restore.

Usage:
    python scripts/restore_backup.py --backup-key backups/postgresql/htode_backup_20260221_020000.dump
    python scripts/restore_backup.py --list  # List available backups
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from common.config import DB_CONFIG, AWS_CONFIG
from common.constants import BACKUP_S3_PREFIX
from common.utils.secrets import get_secret


def list_backups():
    """List available backups in S3."""
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_CONFIG["access_key"],
        aws_secret_access_key=AWS_CONFIG["secret_key"],
        region_name=AWS_CONFIG["region"],
    )
    bucket = AWS_CONFIG["s3_bucket"]

    paginator = s3.get_paginator("list_objects_v2")
    backups = []

    for page in paginator.paginate(Bucket=bucket, Prefix=BACKUP_S3_PREFIX):
        for obj in page.get("Contents", []):
            backups.append(obj)

    if not backups:
        print("No backups found.")
        return

    backups.sort(key=lambda o: o["LastModified"], reverse=True)
    print(f"{'Key':<70} {'Size (MB)':>10} {'Date':<25}")
    print("-" * 110)
    for b in backups:
        size_mb = b["Size"] / (1024 * 1024)
        print(f"{b['Key']:<70} {size_mb:>10.1f} {str(b['LastModified']):<25}")


def restore(backup_key: str, jobs: int = 4):
    """Download backup from S3 and restore with pg_restore."""
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_CONFIG["access_key"],
        aws_secret_access_key=AWS_CONFIG["secret_key"],
        region_name=AWS_CONFIG["region"],
    )
    bucket = AWS_CONFIG["s3_bucket"]

    db_host = os.getenv("DB_HOST", DB_CONFIG["host"])
    db_port = os.getenv("DB_PORT", DB_CONFIG["port"])
    db_user = DB_CONFIG["user"]
    db_name = DB_CONFIG["dbname"]
    db_password = get_secret("db_password", fallback_env="DB_PASS", default=DB_CONFIG["password"])

    print(f"Downloading {backup_key} from s3://{bucket}/...")
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=True) as tmp:
        s3.download_file(bucket, backup_key, tmp.name)
        file_size = os.path.getsize(tmp.name)
        print(f"Downloaded {file_size / (1024*1024):.1f} MB")

        print(f"Restoring to {db_host}:{db_port}/{db_name}...")
        print(f"Using {jobs} parallel jobs")

        result = subprocess.run(
            [
                "pg_restore",
                "--clean",        # Drop objects before recreating
                "--if-exists",    # Don't error on DROP for missing objects
                f"--jobs={jobs}",
                "-h", db_host,
                "-p", str(db_port),
                "-U", db_user,
                "-d", db_name,
                tmp.name,
            ],
            env={**os.environ, "PGPASSWORD": db_password or ""},
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"pg_restore warnings/errors:\n{result.stderr}")
            if "FATAL" in result.stderr or "could not connect" in result.stderr:
                print("FATAL: Restore failed.")
                sys.exit(1)
        else:
            print("Restore completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore PostgreSQL backup from S3")
    parser.add_argument("--backup-key", help="S3 key of the backup to restore")
    parser.add_argument("--list", action="store_true", help="List available backups")
    parser.add_argument("--jobs", type=int, default=4, help="Number of parallel restore jobs")
    args = parser.parse_args()

    if args.list:
        list_backups()
    elif args.backup_key:
        restore(args.backup_key, args.jobs)
    else:
        parser.print_help()
