# system/maintenance/backup.py
"""
PostgreSQL backup tasks: daily pg_dump to S3, weekly cleanup of old backups.
"""

from ._common import (
    celery_app,
    os,
    time,
    datetime,
    timezone,
    timedelta,
    logger,
    log_operation,
    log_context,
    Dict,
    Any,
)

import subprocess
import tempfile

import boto3
from botocore.exceptions import ClientError

from common.config import DB_CONFIG, AWS_CONFIG
from common.constants import BACKUP_RETENTION_DAYS, BACKUP_S3_PREFIX
from common.utils.secrets import get_secret


@celery_app.task(name="system.maintenance.backup_database")
@log_operation("backup_database")
def backup_database() -> Dict[str, Any]:
    """Daily PostgreSQL backup to S3.

    Uses pg_dump in custom format (compressed, supports parallel pg_restore).
    Uploads to s3://<bucket>/backups/postgresql/<filename>.
    """

    start_time = time.time()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"htode_backup_{timestamp}.dump"
    s3_key = f"{BACKUP_S3_PREFIX}{filename}"

    # Resolve DB connection params (use direct host, not PgBouncer, for pg_dump)
    db_host = os.getenv("DB_HOST", DB_CONFIG["host"])
    db_port = os.getenv("DB_PORT", DB_CONFIG["port"])
    db_user = DB_CONFIG["user"]
    db_name = DB_CONFIG["dbname"]
    db_password = get_secret("db_password", fallback_env="DB_PASS", default=DB_CONFIG["password"])

    with log_context(logger, task="backup_database", backup_file=filename):
        try:
            with tempfile.NamedTemporaryFile(suffix=".dump", delete=True) as tmp:
                logger.info("Starting pg_dump", extra={"db_host": db_host, "db_name": db_name})

                result = subprocess.run(
                    [
                        "pg_dump",
                        "-Fc",  # Custom format (compressed)
                        "-h", db_host,
                        "-p", str(db_port),
                        "-U", db_user,
                        "-d", db_name,
                        "-f", tmp.name,
                    ],
                    env={**os.environ, "PGPASSWORD": db_password or ""},
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 min max
                )

                if result.returncode != 0:
                    logger.error(
                        "pg_dump failed",
                        extra={"returncode": result.returncode, "stderr": result.stderr[:500]},
                    )
                    raise RuntimeError(f"pg_dump failed: {result.stderr[:500]}")

                # Get file size
                file_size = os.path.getsize(tmp.name)
                logger.info("pg_dump completed", extra={"size_bytes": file_size})

                # Upload to S3
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=AWS_CONFIG["access_key"],
                    aws_secret_access_key=AWS_CONFIG["secret_key"],
                    region_name=AWS_CONFIG["region"],
                )

                bucket = AWS_CONFIG["s3_bucket"]
                logger.info("Uploading backup to S3", extra={"s3_key": s3_key, "bucket": bucket})
                s3_client.upload_file(tmp.name, bucket, s3_key)

            execution_time = time.time() - start_time
            logger.info(
                "Backup completed successfully",
                extra={
                    "s3_key": s3_key,
                    "size_bytes": file_size,
                    "execution_time_seconds": execution_time,
                },
            )

            return {
                "status": "success",
                "s3_key": s3_key,
                "size_bytes": file_size,
                "execution_time_seconds": execution_time,
            }

        except subprocess.TimeoutExpired:
            logger.error("pg_dump timed out after 30 minutes")
            return {
                "status": "error",
                "error": "pg_dump timed out after 30 minutes",
                "execution_time_seconds": time.time() - start_time,
            }
        except ClientError as e:
            logger.error(
                "S3 upload failed",
                exc_info=True,
                extra={"s3_key": s3_key, "error_type": type(e).__name__},
            )
            return {
                "status": "error",
                "error": f"S3 upload failed: {e}",
                "execution_time_seconds": time.time() - start_time,
            }
        except Exception as e:
            logger.error(
                "Backup failed",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time,
            }


@celery_app.task(name="system.maintenance.cleanup_old_backups")
@log_operation("cleanup_old_backups")
def cleanup_old_backups(retention_days: int = BACKUP_RETENTION_DAYS) -> Dict[str, Any]:
    """Remove backups older than retention_days from S3."""
    with log_context(logger, task="cleanup_old_backups", retention_days=retention_days):
        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=AWS_CONFIG["access_key"],
                aws_secret_access_key=AWS_CONFIG["secret_key"],
                region_name=AWS_CONFIG["region"],
            )
            bucket = AWS_CONFIG["s3_bucket"]
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

            # List objects under the backup prefix
            paginator = s3_client.get_paginator("list_objects_v2")
            to_delete = []

            for page in paginator.paginate(Bucket=bucket, Prefix=BACKUP_S3_PREFIX):
                for obj in page.get("Contents", []):
                    if obj["LastModified"].replace(tzinfo=timezone.utc) < cutoff:
                        to_delete.append({"Key": obj["Key"]})

            deleted_count = 0
            if to_delete:
                # S3 delete_objects supports up to 1000 keys per call
                for i in range(0, len(to_delete), 1000):
                    batch = to_delete[i:i + 1000]
                    s3_client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": batch},
                    )
                    deleted_count += len(batch)

            logger.info(
                "Old backup cleanup completed",
                extra={"deleted_count": deleted_count, "retention_days": retention_days},
            )

            return {
                "status": "success",
                "deleted_count": deleted_count,
                "retention_days": retention_days,
            }

        except ClientError as e:
            logger.error(
                "Backup cleanup failed",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.error(
                "Unexpected error during backup cleanup",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            return {"status": "error", "error": str(e)}
