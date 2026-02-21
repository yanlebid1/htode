#!/usr/bin/env python3
"""
Database Migration for Multi-Bot Architecture

This script adds the necessary columns to support the dispatcher/pool bot pattern.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from common.db.database import engine
from common.utils.logging_config import setup_logging

logger = setup_logging(__name__)

def run_migration():
    """Add multi-bot columns to users table"""
    
    migration_queries = [
        """
        -- Add columns for multi-bot architecture
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS assigned_bot_name VARCHAR(50);
        """,
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS assigned_bot_username VARCHAR(100);
        """,
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS assignment_date TIMESTAMP;
        """,
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS dispatcher_chat_id VARCHAR(50);
        """,
        """
        -- Create index for efficient bot assignment queries
        CREATE INDEX IF NOT EXISTS idx_users_assigned_bot 
        ON users(assigned_bot_name);
        """,
        """
        -- Create index for active users per bot
        CREATE INDEX IF NOT EXISTS idx_users_bot_active 
        ON users(assigned_bot_name) 
        WHERE assigned_bot_name IS NOT NULL;
        """
    ]
    
    try:
        with engine.connect() as conn:
            for query in migration_queries:
                logger.info("Executing migration", extra={"query_preview": query.strip()[:50]})
                conn.execute(text(query))
                conn.commit()
                logger.info("✓ Success")
            
        logger.info("Migration completed successfully!")
        
        # Show current table structure
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'users'
                AND column_name IN ('assigned_bot_name', 'assigned_bot_username', 
                                   'assignment_date', 'dispatcher_chat_id')
                ORDER BY ordinal_position;
            """))
            
            logger.info("\nNew columns:")
            for row in result:
                logger.info("Column info", extra={"column": row[0], "type": row[1], "nullable": row[2]})
                
    except Exception as e:
        logger.error("Migration failed", extra={"error": str(e)})
        raise

def rollback_migration():
    """Rollback multi-bot columns (use with caution!)"""
    
    rollback_queries = [
        "DROP INDEX IF EXISTS idx_users_assigned_bot;",
        "DROP INDEX IF EXISTS idx_users_bot_active;",
        "ALTER TABLE users DROP COLUMN IF EXISTS assigned_bot_name;",
        "ALTER TABLE users DROP COLUMN IF EXISTS assigned_bot_username;",
        "ALTER TABLE users DROP COLUMN IF EXISTS assignment_date;",
        "ALTER TABLE users DROP COLUMN IF EXISTS dispatcher_chat_id;"
    ]
    
    confirm = input("⚠️  This will remove multi-bot columns. Are you sure? (yes/no): ")
    if confirm.lower() != 'yes':
        logger.info("Rollback cancelled")
        return
    
    try:
        with engine.connect() as conn:
            for query in rollback_queries:
                logger.info("Executing rollback", extra={"query_preview": query.strip()[:50]})
                conn.execute(text(query))
                conn.commit()
                
        logger.info("Rollback completed")
    except Exception as e:
        logger.error("Rollback failed", extra={"error": str(e)})
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-bot database migration")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration (removes columns)"
    )
    
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration() 