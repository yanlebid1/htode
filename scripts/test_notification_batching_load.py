#!/usr/bin/env python3
"""
Notification Batching Load Test

This script tests the notification batching system under high load
to verify it can handle tens of thousands of concurrent notifications efficiently.
"""

import asyncio
import time
import sys
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.celery_app import celery_app
from common.db.session import db_session
from common.db.models.user import User

class NotificationBatchingLoadTest:
    def __init__(self):
        self.results = []
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def create_test_users(self, count: int) -> List[int]:
        """Create test users for load testing"""
        print(f"📝 Creating {count} test users...")
        
        user_ids = []
        with db_session() as db:
            for i in range(count):
                telegram_id = f"test_user_{int(time.time())}_{i}"
                
                # Check if user already exists
                existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
                if existing_user:
                    user_ids.append(existing_user.id)
                    continue
                
                user = User(telegram_id=telegram_id)
                db.add(user)
                db.flush()  # Get the ID without committing
                user_ids.append(user.id)
                
                if i % 100 == 0:
                    db.commit()  # Commit in batches
                    print(f"   Created {i+1}/{count} users...")
            
            db.commit()  # Final commit
        
        print(f"✅ Created {len(user_ids)} test users")
        return user_ids
    
    def create_test_ad_data(self) -> Dict[str, Any]:
        """Create sample ad data for notifications"""
        return {
            "id": random.randint(10000, 99999),
            "external_id": f"test_ad_{int(time.time())}",
            "price": random.randint(5000, 50000),
            "city": random.choice(["Київ", "Львів", "Харків", "Одеса"]),
            "address": f"Test Address {random.randint(1, 100)}",
            "rooms_count": random.randint(1, 4),
            "square_feet": random.randint(30, 150),
            "floor": random.randint(1, 20),
            "total_floors": random.randint(5, 25),
            "resource_url": f"https://test.com/ad/{random.randint(1000, 9999)}"
        }
    
    def send_batch_notification(self, user_ids: List[int], ad_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a batch notification and measure performance"""
        start_time = time.time()
        
        try:
            # Send the batch notification task
            result = celery_app.send_task(
                "common.tasks.notify_user_batch",
                args=[user_ids, ad_data, None],  # No image for load test
                queue="notification_queue",
                priority=1
            )
            
            end_time = time.time()
            
            return {
                "success": True,
                "duration": end_time - start_time,
                "batch_size": len(user_ids),
                "task_id": result.id,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "duration": end_time - start_time,
                "batch_size": len(user_ids),
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
    
    def run_concurrent_batch_test(self, total_users: int, batch_size: int = 100, max_workers: int = 10) -> Dict[str, Any]:
        """Run concurrent batch notification test"""
        print(f"🚀 Starting batch notification load test...")
        print(f"   Total Users: {total_users}")
        print(f"   Batch Size: {batch_size}")
        print(f"   Max Workers: {max_workers}")
        
        # Create test users
        user_ids = self.create_test_users(total_users)
        
        # Create test ad data
        ad_data = self.create_test_ad_data()
        
        # Split users into batches
        batches = []
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            batches.append(batch)
        
        print(f"📦 Split into {len(batches)} batches")
        
        self.start_time = time.time()
        self.results = []
        self.errors = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batch tasks
            future_to_batch = {
                executor.submit(self.send_batch_notification, batch, ad_data): i
                for i, batch in enumerate(batches)
            }
            
            # Collect results
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    result = future.result()
                    if result["success"]:
                        self.results.append(result)
                        print(f"✅ Batch {batch_idx + 1}/{len(batches)} completed in {result['duration']:.3f}s")
                    else:
                        self.errors.append(result)
                        print(f"❌ Batch {batch_idx + 1}/{len(batches)} failed: {result['error']}")
                except Exception as e:
                    error_result = {
                        "batch_idx": batch_idx,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": datetime.now().isoformat()
                    }
                    self.errors.append(error_result)
                    print(f"❌ Batch {batch_idx + 1}/{len(batches)} exception: {e}")
        
        self.end_time = time.time()
        return self.get_test_summary(total_users)
    
    def get_test_summary(self, total_users: int) -> Dict[str, Any]:
        """Generate test summary statistics"""
        total_batches = len(self.results) + len(self.errors)
        success_count = len(self.results)
        error_count = len(self.errors)
        
        if self.results:
            durations = [r["duration"] for r in self.results]
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            
            batch_sizes = [r["batch_size"] for r in self.results]
            total_successful_users = sum(batch_sizes)
        else:
            avg_duration = min_duration = max_duration = 0
            total_successful_users = 0
        
        total_time = self.end_time - self.start_time if self.start_time and self.end_time else 0
        
        return {
            "total_users": total_users,
            "total_batches": total_batches,
            "successful_batches": success_count,
            "failed_batches": error_count,
            "batch_success_rate": (success_count / total_batches) * 100 if total_batches > 0 else 0,
            "total_successful_users": total_successful_users,
            "user_success_rate": (total_successful_users / total_users) * 100 if total_users > 0 else 0,
            "total_test_time": total_time,
            "avg_batch_duration": avg_duration,
            "min_batch_duration": min_duration,
            "max_batch_duration": max_duration,
            "batches_per_second": total_batches / total_time if total_time > 0 else 0,
            "users_per_second": total_successful_users / total_time if total_time > 0 else 0,
            "errors": self.errors[:3]  # Show first 3 errors
        }
    
    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted test summary"""
        print(f"\n{'='*90}")
        print(f"📊 NOTIFICATION BATCHING LOAD TEST RESULTS")
        print(f"{'='*90}")
        
        # Overall Results
        print(f"\n📈 Test Results:")
        print(f"   Total Users: {summary['total_users']}")
        print(f"   Total Batches: {summary['total_batches']}")
        print(f"   Successful Batches: {summary['successful_batches']} ✅")
        print(f"   Failed Batches: {summary['failed_batches']} ❌")
        print(f"   Batch Success Rate: {summary['batch_success_rate']:.1f}%")
        print(f"   User Success Rate: {summary['user_success_rate']:.1f}%")
        
        # Performance Metrics
        print(f"\n⚡ Performance Metrics:")
        print(f"   Total Test Time: {summary['total_test_time']:.2f} seconds")
        print(f"   Batches/Second: {summary['batches_per_second']:.1f}")
        print(f"   Users/Second: {summary['users_per_second']:.1f}")
        print(f"   Users/Minute: {summary['users_per_second'] * 60:.0f}")
        print(f"   Avg Batch Duration: {summary['avg_batch_duration']:.3f} seconds")
        print(f"   Min Batch Duration: {summary['min_batch_duration']:.3f} seconds")
        print(f"   Max Batch Duration: {summary['max_batch_duration']:.3f} seconds")
        
        # Performance Assessment
        users_per_minute = summary['users_per_second'] * 60
        batch_success_rate = summary['batch_success_rate']
        
        print(f"\n🎯 Performance Assessment:")
        
        # Throughput assessment
        if users_per_minute >= 5000:
            throughput_status = "🟢 EXCELLENT"
        elif users_per_minute >= 2000:
            throughput_status = "🟡 GOOD"
        elif users_per_minute >= 1000:
            throughput_status = "🟠 MODERATE"
        else:
            throughput_status = "🔴 POOR"
        
        # Reliability assessment
        if batch_success_rate >= 98:
            reliability_status = "🟢 EXCELLENT"
        elif batch_success_rate >= 95:
            reliability_status = "🟡 GOOD"
        elif batch_success_rate >= 90:
            reliability_status = "🟠 MODERATE"
        else:
            reliability_status = "🔴 POOR"
        
        print(f"   Throughput: {throughput_status} ({users_per_minute:.0f} users/min)")
        print(f"   Reliability: {reliability_status} ({batch_success_rate:.1f}% success)")
        
        # Show errors if any
        if summary['errors']:
            print(f"\n❌ Sample Errors:")
            for i, error in enumerate(summary['errors'], 1):
                print(f"   {i}. {error.get('error_type', 'Unknown')}: {str(error.get('error', ''))[:80]}...")
        
        # Scaling projections
        print(f"\n📊 Scaling Projections:")
        if users_per_minute > 0:
            time_for_10k = (10000 / users_per_minute)
            time_for_50k = (50000 / users_per_minute)
            time_for_100k = (100000 / users_per_minute)
            
            print(f"   Time to notify 10,000 users: {time_for_10k:.1f} minutes")
            print(f"   Time to notify 50,000 users: {time_for_50k:.1f} minutes")  
            print(f"   Time to notify 100,000 users: {time_for_100k:.1f} minutes")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if batch_success_rate < 95:
            print("   - Check Redis and database connection stability")
            print("   - Monitor worker health and resource usage")
            print("   - Consider increasing retry mechanisms")
        
        if users_per_minute < 3000:
            print("   - Consider increasing batch worker concurrency")
            print("   - Scale up notification_batch_worker resources")
            print("   - Check for bottlenecks in Telegram workers")
        else:
            print("   - Notification batching system is ready for production!")
            print("   - Performance meets scaling requirements")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test notification batching system under load")
    parser.add_argument("--users", type=int, default=1000, help="Total number of users to test")
    parser.add_argument("--batch-size", type=int, default=100, help="Size of each notification batch")
    parser.add_argument("--workers", type=int, default=10, help="Max concurrent workers")
    parser.add_argument("--quick", action="store_true", help="Quick test with 500 users")
    parser.add_argument("--stress", action="store_true", help="Stress test with 5000 users")
    
    args = parser.parse_args()
    
    # Preset configurations
    if args.quick:
        args.users = 500
        args.workers = 5
    elif args.stress:
        args.users = 5000
        args.workers = 20
    
    print(f"🔧 Notification Batching Load Tester")
    print(f"📊 Test Configuration:")
    print(f"   Total Users: {args.users}")
    print(f"   Batch Size: {args.batch_size}")
    print(f"   Max Workers: {args.workers}")
    print(f"   Expected Batches: {(args.users + args.batch_size - 1) // args.batch_size}")
    
    if args.users > 2000:
        confirm = input(f"\n⚠️  This will create {args.users} test users. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Test cancelled.")
            return
    
    tester = NotificationBatchingLoadTest()
    summary = tester.run_concurrent_batch_test(args.users, args.batch_size, args.workers)
    tester.print_summary(summary)

if __name__ == "__main__":
    main() 