#!/usr/bin/env python3
"""
Test Multi-Bot Setup

Quick verification that the multi-bot architecture is configured correctly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.config_multibot import multibot_config
from common.db.database import engine
from sqlalchemy import text
import asyncio
from aiogram import Bot

async def test_bot_token(bot_name: str, token: str) -> bool:
    """Test if a bot token is valid"""
    try:
        bot = Bot(token=token)
        bot_info = await bot.get_me()
        print(f"  ✅ {bot_name}: @{bot_info.username} (ID: {bot_info.id})")
        await bot.close()
        return True
    except Exception as e:
        print(f"  ❌ {bot_name}: {str(e)}")
        return False

async def test_all_bots():
    """Test all configured bot tokens"""
    print("\n🤖 Testing Bot Tokens")
    print("=" * 50)
    
    # Test dispatcher
    dispatcher = multibot_config.get_dispatcher_config()
    if dispatcher['token']:
        print("\nDispatcher Bot:")
        await test_bot_token("Dispatcher", dispatcher['token'])
    else:
        print("\n❌ Dispatcher bot token not configured!")
    
    # Test pool bots
    pool_bots = multibot_config.get_active_bots()
    if pool_bots:
        print(f"\nPool Bots ({len(pool_bots)} configured):")
        valid_count = 0
        for bot in pool_bots:
            if await test_bot_token(bot.name, bot.token):
                valid_count += 1
        
        print(f"\n📊 Summary: {valid_count}/{len(pool_bots)} bots valid")
    else:
        print("\n❌ No pool bots configured!")
    
    return len(pool_bots)

def test_database():
    """Test database schema"""
    print("\n🗄️  Testing Database Schema")
    print("=" * 50)
    
    try:
        with engine.connect() as conn:
            # Check if columns exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('assigned_bot_name', 'assigned_bot_username', 
                                   'assignment_date', 'dispatcher_chat_id')
                ORDER BY column_name;
            """))
            
            columns = [row[0] for row in result]
            
            required_columns = [
                'assigned_bot_name',
                'assigned_bot_username', 
                'assignment_date',
                'dispatcher_chat_id'
            ]
            
            print("\nRequired columns:")
            for col in required_columns:
                if col in columns:
                    print(f"  ✅ {col}")
                else:
                    print(f"  ❌ {col} - MISSING!")
            
            return len(columns) == len(required_columns)
            
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        return False

def calculate_capacity(bot_count: int):
    """Calculate system capacity"""
    print("\n📈 System Capacity")
    print("=" * 50)
    
    users_per_bot = 5000
    messages_per_bot_per_min = 1500
    
    total_users = bot_count * users_per_bot
    total_throughput = bot_count * messages_per_bot_per_min
    time_for_100k = 100000 / total_throughput if total_throughput > 0 else float('inf')
    
    print(f"  Pool Bots: {bot_count}")
    print(f"  Users per bot: {users_per_bot:,}")
    print(f"  Total capacity: {total_users:,} users")
    print(f"  Throughput: {total_throughput:,} messages/min")
    print(f"  Time for 100k users: {time_for_100k:.1f} minutes")
    
    if bot_count >= 20:
        print("\n  ✅ Optimal configuration for 100k+ users!")
    elif bot_count >= 10:
        print("\n  ⚠️  Good for up to 50k users")
    else:
        print("\n  ⚠️  Limited capacity - consider adding more bots")

def main():
    """Run all tests"""
    print("\n🚀 Multi-Bot Setup Verification")
    print("=" * 50)
    
    # Test configuration
    print("\n📝 Configuration Source")
    print("=" * 50)
    if os.path.exists('.env'):
        print("  ✅ .env file found")
    else:
        print("  ❌ .env file not found!")
        print("  💡 Copy docs/env_multibot_template.txt to .env")
        return
    
    # Run async bot tests
    loop = asyncio.get_event_loop()
    bot_count = loop.run_until_complete(test_all_bots())
    
    # Test database
    db_ok = test_database()
    if not db_ok:
        print("\n  💡 Run: python scripts/migrate_multibot.py")
    
    # Calculate capacity
    calculate_capacity(bot_count)
    
    # Final summary
    print("\n" + "=" * 50)
    if bot_count > 0 and db_ok:
        print("✅ Multi-bot system is ready!")
        print("\nNext steps:")
        print("1. Start services: docker-compose -f docker-compose.multibot.yml up -d")
        print("2. Monitor: python scripts/monitor_multibot_system.py")
    else:
        print("❌ Setup incomplete - check errors above")

if __name__ == "__main__":
    main() 