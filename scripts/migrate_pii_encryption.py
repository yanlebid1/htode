#!/usr/bin/env python3
"""
One-time migration script to encrypt existing PII data in the database.

Usage:
    python scripts/migrate_pii_encryption.py --dry-run    # Preview changes
    python scripts/migrate_pii_encryption.py              # Execute migration

Prerequisites:
    - ENCRYPTION_MASTER_KEY and ENCRYPTION_HMAC_KEY must be set in environment
    - Database must be accessible
    - New columns (email_encrypted, email_search_token, etc.) must exist in schema

Generate keys:
    python -c "from common.utils.encryption import generate_fernet_key, generate_hmac_key; print(f'ENCRYPTION_MASTER_KEY={generate_fernet_key()}'); print(f'ENCRYPTION_HMAC_KEY={generate_hmac_key()}')"
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.utils.encryption import (
    encrypt,
    decrypt,
    make_search_token,
    is_encryption_configured,
)


def migrate_users(db, dry_run: bool) -> dict:
    """Encrypt email and phone_number for all users."""
    from common.db.models.user import User

    stats = {"total": 0, "email_encrypted": 0, "phone_encrypted": 0, "errors": 0}

    users = db.query(User).all()
    stats["total"] = len(users)

    for user in users:
        try:
            # Encrypt email
            if user.email and not user.email_encrypted:
                encrypted = encrypt(user.email)
                token = make_search_token(user.email)
                if encrypted and token:
                    if not dry_run:
                        user.email_encrypted = encrypted
                        user.email_search_token = token
                    stats["email_encrypted"] += 1

                    # Verify round-trip
                    decrypted = decrypt(encrypted)
                    if decrypted != user.email:
                        print(f"  WARNING: Round-trip failed for user {user.id} email")
                        stats["errors"] += 1

            # Encrypt phone
            if user.phone_number and not user.phone_encrypted:
                encrypted = encrypt(user.phone_number)
                token = make_search_token(user.phone_number)
                if encrypted and token:
                    if not dry_run:
                        user.phone_encrypted = encrypted
                        user.phone_search_token = token
                    stats["phone_encrypted"] += 1

                    # Verify round-trip
                    decrypted = decrypt(encrypted)
                    if decrypted != user.phone_number:
                        print(f"  WARNING: Round-trip failed for user {user.id} phone")
                        stats["errors"] += 1

        except Exception as e:
            print(f"  ERROR: Failed to encrypt user {user.id}: {e}")
            stats["errors"] += 1

    if not dry_run:
        db.commit()

    return stats


def migrate_verifications(db, dry_run: bool) -> dict:
    """Encrypt target field for all verifications."""
    from common.db.models.verification import Verification

    stats = {"total": 0, "encrypted": 0, "errors": 0}

    verifications = db.query(Verification).all()
    stats["total"] = len(verifications)

    for v in verifications:
        try:
            if v.target and not v.target_encrypted:
                encrypted = encrypt(v.target)
                token = make_search_token(v.target)
                if encrypted and token:
                    if not dry_run:
                        v.target_encrypted = encrypted
                        v.target_search_token = token
                    stats["encrypted"] += 1

                    # Verify round-trip
                    decrypted = decrypt(encrypted)
                    if decrypted != v.target:
                        print(f"  WARNING: Round-trip failed for verification {v.id}")
                        stats["errors"] += 1

        except Exception as e:
            print(f"  ERROR: Failed to encrypt verification {v.id}: {e}")
            stats["errors"] += 1

    if not dry_run:
        db.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate PII data to encrypted columns")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database",
    )
    args = parser.parse_args()

    if not is_encryption_configured():
        print("ERROR: ENCRYPTION_MASTER_KEY and ENCRYPTION_HMAC_KEY must be set")
        print("\nGenerate keys with:")
        print(
            '  python -c "from common.utils.encryption import generate_fernet_key, generate_hmac_key; '
            "print(f'ENCRYPTION_MASTER_KEY={generate_fernet_key()}'); "
            "print(f'ENCRYPTION_HMAC_KEY={generate_hmac_key()}')\""
        )
        sys.exit(1)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n=== PII Encryption Migration ({mode}) ===\n")

    from common.db.session import db_session

    with db_session() as db:
        # Migrate users
        print("Migrating users...")
        user_stats = migrate_users(db, args.dry_run)
        print(f"  Total users: {user_stats['total']}")
        print(f"  Emails encrypted: {user_stats['email_encrypted']}")
        print(f"  Phones encrypted: {user_stats['phone_encrypted']}")
        print(f"  Errors: {user_stats['errors']}")

        # Migrate verifications
        print("\nMigrating verifications...")
        verif_stats = migrate_verifications(db, args.dry_run)
        print(f"  Total verifications: {verif_stats['total']}")
        print(f"  Targets encrypted: {verif_stats['encrypted']}")
        print(f"  Errors: {verif_stats['errors']}")

    total_errors = user_stats["errors"] + verif_stats["errors"]
    if total_errors > 0:
        print(f"\nCompleted with {total_errors} errors — review above")
        sys.exit(1)
    else:
        print(f"\nMigration {'preview' if args.dry_run else 'completed'} successfully")


if __name__ == "__main__":
    main()
