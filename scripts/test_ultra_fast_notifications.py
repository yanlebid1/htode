#!/usr/bin/env python3
"""
Safe High-Performance Notification System Load Test

Tests the safe optimized notification system respecting Telegram's official limits:
- 25 msg/sec Telegram rate limit (1500/min) - Safe under 30/s official limit
- 15 batch/min rate limit (1,500 users/min)
- 100 users per batch
- 3x notification batch workers
- 3x telegram workers with 16 concurrency each

This test validates significant performance improvements while staying within safe limits.
"""

import time
import sys
import os
from typing import Dict, Any, List
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class UltraFastNotificationTester:
    """Test the ultra-fast notification system"""
    
    def __init__(self):
        self.test_ad_data = {
            "id": 99999,
            "external_id": "test_ultra_fast",
            "price": 50000,
            "city": "Київ",
            "address": "вул. Тестова, 1",
            "rooms_count": 2,
            "square_feet": 65,
            "floor": 5,
            "total_floors": 10,
            "resource_url": "https://test.com/ad/99999"
        }
    
    def create_test_users(self, count: int) -> List[int]:
        """Create test users for notification testing"""
        print(f"📝 Creating {count} test users...")
        
        from common.db.session import db_session
        from common.db.models import User
        
        user_ids = []
        with db_session() as db:
            for i in range(count):
                # Create unique telegram IDs for testing
                telegram_id = 1000000 + i
                
                user = User(
                    telegram_id=telegram_id,
                    username=f"test_user_{i}",
                    first_name=f"TestUser{i}",
                    is_active=True
                )
                db.add(user)
                
            db.commit()
            
            # Get the created user IDs
            users = db.query(User).filter(User.username.like("test_user_%")).all()
            user_ids = [user.id for user in users]
        
        print(f"✅ Created {len(user_ids)} test users")
        return user_ids
    
    def cleanup_test_users(self):
        """Clean up test users after testing"""
        print("🧹 Cleaning up test users...")
        
        from common.db.session import db_session
        from common.db.models import User
        
        with db_session() as db:
            # Delete test users
            db.query(User).filter(User.username.like("test_user_%")).delete()
            db.commit()
        
        print("✅ Test users cleaned up")
    
    def test_ultra_fast_batch_notification(self, user_count: int) -> Dict[str, Any]:
        """Test the ultra-fast batch notification system"""
        print(f"🚀 Testing ultra-fast notifications for {user_count} users...")
        
        from common.celery_app import celery_app
        
        # Create test users
        user_ids = self.create_test_users(user_count)
        
        # Record start time
        start_time = time.time()
        
        # Send batch notification using the new v2 system
        task = celery_app.send_task(
            "common.tasks.notify_user_batch",
            args=[user_ids, self.test_ad_data, "https://test.com/image.jpg"],
            queue="notification_queue",
            priority=9  # Highest priority for testing
        )
        
        # Wait for task completion
        try:
            result = task.get(timeout=300)  # 5 minute timeout
            end_time = time.time()
            
            total_time = end_time - start_time
            users_per_second = user_count / total_time if total_time > 0 else 0
            
            print(f"✅ Batch notification completed!")
            print(f"   📊 Results: {result}")
            print(f"   ⏱️  Total time: {total_time:.2f} seconds")
            print(f"   🚀 Throughput: {users_per_second:.0f} users/second")
            print(f"   📈 Throughput: {users_per_second * 60:.0f} users/minute")
            
            return {
                "success": True,
                "user_count": user_count,
                "total_time": total_time,
                "users_per_second": users_per_second,
                "users_per_minute": users_per_second * 60,
                "batch_result": result,
                "test_type": "ultra_fast_batch"
            }
            
        except Exception as e:
            end_time = time.time()
            print(f"❌ Batch notification failed: {e}")
            
            return {
                "success": False,
                "user_count": user_count,
                "total_time": end_time - start_time,
                "error": str(e),
                "test_type": "ultra_fast_batch"
            }
        
        finally:
            # Clean up
            self.cleanup_test_users()
    
    def print_performance_analysis(self, result: Dict[str, Any]):
        """Print performance analysis"""
        print(f"\n{'='*80}")
        print(f"📊 ULTRA-FAST NOTIFICATION PERFORMANCE ANALYSIS")
        print(f"{'='*80}")
        
        if result.get("success"):
            throughput = result.get('users_per_minute', 0)
            
            print(f"\n🏆 Performance Results:")
            print(f"   Users tested: {result.get('user_count', 0)}")
            print(f"   Throughput: {throughput:.0f} users/minute")
            print(f"   Processing time: {result.get('total_time', 0):.2f} seconds")
            
            # Scaling projections
            if throughput > 0:
                print(f"\n📈 Scaling Projections:")
                
                projections = [
                    (1000, "1,000 users"),
                    (10000, "10,000 users"), 
                    (50000, "50,000 users"),
                    (100000, "100,000 users"),
                ]
                
                for user_count, label in projections:
                    time_minutes = user_count / throughput
                    if time_minutes < 1:
                        time_str = f"{time_minutes * 60:.0f} seconds"
                    else:
                        time_str = f"{time_minutes:.1f} minutes"
                    print(f"   {label}: {time_str}")
                
                # Performance comparison with original
                original_throughput = 600  # Original: 10 msg/min = 600/hr = 10/min
                safe_expected = 1500  # Expected: 25 msg/sec = 1500/min
                improvement = throughput / original_throughput
                
                print(f"\n📊 Performance vs. Original System:")
                print(f"   Original: {original_throughput} users/minute")
                print(f"   Safe optimized: {throughput:.0f} users/minute")
                print(f"   Expected safe: {safe_expected} users/minute")
                print(f"   🚀 Improvement: {improvement:.1f}x faster!")
                
                # Time comparison for 50k users
                original_time_50k = 50000 / original_throughput  # ~28 minutes
                new_time_50k = 50000 / throughput
                time_saved = original_time_50k - new_time_50k
                
                print(f"\n⏱️ Time Comparison for 50,000 users:")
                print(f"   Original: {original_time_50k:.1f} minutes")
                print(f"   Ultra-fast: {new_time_50k:.1f} minutes")
                print(f"   ⚡ Time saved: {time_saved:.1f} minutes")
        else:
            print("❌ Test failed, no performance analysis available")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test ultra-fast notification system")
    parser.add_argument("--users", type=int, default=1000, help="Number of users to test")
    parser.add_argument("--quick", action="store_true", help="Quick test with 500 users")
    
    args = parser.parse_args()
    
    tester = UltraFastNotificationTester()
    
    if args.quick:
        print("🔥 Quick ultra-fast notification test")
        result = tester.test_ultra_fast_batch_notification(500)
    else:
        print(f"🚀 Ultra-fast notification test with {args.users} users")
        result = tester.test_ultra_fast_batch_notification(args.users)
    
    tester.print_performance_analysis(result)

if __name__ == "__main__":
    main() 