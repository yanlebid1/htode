#!/usr/bin/env python3
"""
Migration script: Enable Row-Level Security on user-owned tables.

Safe to run multiple times — uses IF NOT EXISTS guards via DO $$ blocks.

Usage:
    python scripts/migrate_rls.py
"""

import os
import sys

import psycopg2

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import DB_CONFIG


RLS_TABLES = [
    "user_filters",
    "favorite_ads",
    "subscriptions",
    "payment_orders",
    "payment_history",
    "verification_codes",
]

# Each table gets two policies: user policy (when app.current_user_id is set)
# and system policy (when it's unset/empty — for maintenance, notifier, scraper).
POLICY_TEMPLATE = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = '{table}_user_policy') THEN
        CREATE POLICY {table}_user_policy ON {table}
            USING (user_id = current_setting('app.current_user_id', true)::integer)
            WITH CHECK (user_id = current_setting('app.current_user_id', true)::integer);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = '{table}_system_policy') THEN
        CREATE POLICY {table}_system_policy ON {table}
            USING (current_setting('app.current_user_id', true) IS NULL
                   OR current_setting('app.current_user_id', true) = '');
    END IF;
END $$;
"""


def migrate():
    conn = psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        dbname=DB_CONFIG["dbname"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    for table in RLS_TABLES:
        print(f"Enabling RLS on {table}...")
        cur.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

        policy_sql = POLICY_TEMPLATE.format(table=table)
        cur.execute(policy_sql)
        print(f"  -> Policies created for {table}")

    cur.close()
    conn.close()
    print("\nRLS migration complete.")


if __name__ == "__main__":
    migrate()
