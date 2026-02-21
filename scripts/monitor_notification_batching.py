#!/usr/bin/env python3
"""
Notification Batching System Monitor

This script monitors the performance and throughput of the notification batching system
to ensure it can handle tens of thousands of users efficiently.
"""

import time
import redis
import sys
import os
import signal
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from collections import defaultdict, deque

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.config import REDIS_URL
from common.db.session import db_session
from common.db.models.user import User
from sqlalchemy import text

class NotificationBatchingMonitor:
    def __init__(self):
        self.running = True
        self.redis_client = redis.from_url(REDIS_URL)
        self.metrics_history = deque(maxlen=60)  # Keep last 60 data points
        self.notification_throughput = deque(maxlen=20)  # Track throughput
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print("\n🛑 Received interrupt signal. Shutting down gracefully...")
        self.running = False
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get detailed queue statistics for notification system"""
        queues = {
            "notification_queue": "Batch notifications",
            "telegram_queue": "Individual telegram messages",
            "priority_queue": "High priority notifications",
            "scraper_queue": "Ad scraping tasks"
        }
        
        stats = {}
        for queue_name, description in queues.items():
            try:
                length = self.redis_client.llen(queue_name)
                stats[queue_name] = {
                    "length": length,
                    "description": description,
                    "status": "🟢" if length < 100 else "🟡" if length < 500 else "🔴"
                }
            except Exception as e:
                stats[queue_name] = {
                    "length": -1,
                    "description": description,
                    "status": "❌",
                    "error": str(e)
                }
        
        return stats
    
    def get_celery_worker_stats(self) -> Dict[str, Any]:
        """Get Celery worker statistics"""
        try:
            # Get active workers
            from common.celery_app import celery_app
            inspect = celery_app.control.inspect()
            
            active_tasks = inspect.active() or {}
            stats_info = inspect.stats() or {}
            
            worker_stats = {}
            for worker_name, tasks in active_tasks.items():
                stats = stats_info.get(worker_name, {})
                worker_stats[worker_name] = {
                    "active_tasks": len(tasks),
                    "processed_tasks": stats.get("total", {}).get("tasks.processed", 0),
                    "pool_size": stats.get("pool", {}).get("max-concurrency", 0),
                    "status": "🟢" if len(tasks) < 10 else "🟡" if len(tasks) < 50 else "🔴"
                }
            
            return worker_stats
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_notification_throughput(self) -> Dict[str, float]:
        """Calculate notification throughput metrics"""
        try:
            with db_session() as db:
                # Get notification counts from the last hour
                result = db.execute(text("""
                    WITH notification_stats AS (
                        SELECT 
                            COUNT(*) as users_with_active_subscriptions,
                            COUNT(*) FILTER (WHERE subscription_until > NOW()) as premium_users,
                            COUNT(*) FILTER (WHERE free_until > NOW()) as free_users
                        FROM users 
                        WHERE (subscription_until > NOW() OR free_until > NOW())
                    )
                    SELECT * FROM notification_stats
                """)).fetchone()
                
                return {
                    "total_active_users": result.users_with_active_subscriptions,
                    "premium_users": result.premium_users,
                    "free_users": result.free_users,
                    "potential_notifications_per_ad": result.users_with_active_subscriptions
                }
        except Exception as e:
            return {"error": str(e)}
    
    def get_batching_efficiency_metrics(self) -> Dict[str, Any]:
        """Calculate batching system efficiency"""
        queue_stats = self.get_queue_statistics()
        
        notification_queue_length = queue_stats.get("notification_queue", {}).get("length", 0)
        telegram_queue_length = queue_stats.get("telegram_queue", {}).get("length", 0)
        
        # Estimate users being processed
        # Each notification batch handles ~100 users
        # Each telegram message is 1 user
        estimated_users_in_batch_queue = notification_queue_length * 100
        estimated_users_in_telegram_queue = telegram_queue_length
        
        total_estimated_users = estimated_users_in_batch_queue + estimated_users_in_telegram_queue
        
        # Calculate efficiency metrics
        batch_efficiency = 0
        if total_estimated_users > 0:
            batch_efficiency = (estimated_users_in_batch_queue / total_estimated_users) * 100
        
        return {
            "notification_batches_pending": notification_queue_length,
            "individual_messages_pending": telegram_queue_length,
            "estimated_users_in_batch_queue": estimated_users_in_batch_queue,
            "estimated_users_in_telegram_queue": estimated_users_in_telegram_queue,
            "total_estimated_users": total_estimated_users,
            "batch_efficiency_percent": batch_efficiency,
            "estimated_processing_time_minutes": total_estimated_users / 100  # ~100 users per minute capacity
        }
    
    def get_rate_limiting_status(self) -> Dict[str, Any]:
        """Check rate limiting configuration and effectiveness"""
        # These are the configured rate limits from celery_app.py
        configured_limits = {
            "batch_notifications": "60/m (6000 users/min)",
            "individual_notifications": "30/m",
            "telegram_messages": "30/s (1800/min)",
            "ad_processing": "20/m"
        }
        
        # Calculate theoretical throughput
        batch_throughput = 60 * 100  # 60 batches/min * 100 users/batch = 6000 users/min
        telegram_throughput = 30 * 60  # 30 messages/sec * 60 sec = 1800 users/min
        
        return {
            "configured_limits": configured_limits,
            "theoretical_batch_throughput": f"{batch_throughput} users/min",
            "theoretical_telegram_throughput": f"{telegram_throughput} users/min",
            "bottleneck": "Telegram API" if telegram_throughput < batch_throughput else "Batch processing",
            "max_users_per_minute": min(batch_throughput, telegram_throughput)
        }
    
    def print_dashboard(self):
        """Print comprehensive notification system dashboard"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*90}")
        print(f"📊 NOTIFICATION BATCHING SYSTEM DASHBOARD - {timestamp}")
        print(f"{'='*90}")
        
        # Queue Statistics
        queue_stats = self.get_queue_statistics()
        print(f"\n📋 Queue Statistics:")
        for queue_name, stats in queue_stats.items():
            if "error" in stats:
                print(f"   {queue_name}: ❌ Error - {stats['error']}")
            else:
                print(f"   {stats['status']} {queue_name}: {stats['length']} tasks - {stats['description']}")
        
        # Batching Efficiency
        efficiency = self.get_batching_efficiency_metrics()
        print(f"\n⚡ Batching Efficiency:")
        print(f"   Notification Batches: {efficiency['notification_batches_pending']}")
        print(f"   Individual Messages: {efficiency['individual_messages_pending']}")
        print(f"   Users in Batch Queue: {efficiency['estimated_users_in_batch_queue']}")
        print(f"   Users in Telegram Queue: {efficiency['estimated_users_in_telegram_queue']}")
        print(f"   Total Users Pending: {efficiency['total_estimated_users']}")
        print(f"   Batch Efficiency: {efficiency['batch_efficiency_percent']:.1f}%")
        
        efficiency_status = "🟢" if efficiency['batch_efficiency_percent'] > 80 else "🟡" if efficiency['batch_efficiency_percent'] > 50 else "🔴"
        print(f"   Status: {efficiency_status}")
        
        if efficiency['total_estimated_users'] > 0:
            print(f"   Est. Processing Time: {efficiency['estimated_processing_time_minutes']:.1f} minutes")
        
        # Worker Statistics
        worker_stats = self.get_celery_worker_stats()
        print(f"\n👷 Worker Statistics:")
        if "error" in worker_stats:
            print(f"   ❌ Error getting worker stats: {worker_stats['error']}")
        else:
            for worker_name, stats in worker_stats.items():
                print(f"   {stats['status']} {worker_name}: {stats['active_tasks']}/{stats['pool_size']} active tasks")
        
        # Throughput Analysis
        throughput = self.calculate_notification_throughput()
        print(f"\n📈 User Base Analytics:")
        if "error" in throughput:
            print(f"   ❌ Error: {throughput['error']}")
        else:
            print(f"   Total Active Users: {throughput['total_active_users']}")
            print(f"   Premium Users: {throughput['premium_users']}")
            print(f"   Free Trial Users: {throughput['free_users']}")
            print(f"   Notifications per New Ad: {throughput['potential_notifications_per_ad']}")
        
        # Rate Limiting Status
        rate_limits = self.get_rate_limiting_status()
        print(f"\n🚦 Rate Limiting & Capacity:")
        print(f"   Max Throughput: {rate_limits['max_users_per_minute']} users/minute")
        print(f"   Bottleneck: {rate_limits['bottleneck']}")
        print(f"   Batch System: {rate_limits['theoretical_batch_throughput']}")
        print(f"   Telegram API: {rate_limits['theoretical_telegram_throughput']}")
        
        # Performance Assessment
        print(f"\n🎯 Performance Assessment:")
        total_users = throughput.get('total_active_users', 0)
        max_throughput = rate_limits['max_users_per_minute']
        
        if total_users == 0:
            assessment = "🟢 READY - No users to notify"
        elif total_users < max_throughput:
            assessment = "🟢 EXCELLENT - Can notify all users in <1 minute"
        elif total_users < max_throughput * 5:
            assessment = "🟡 GOOD - Can notify all users in <5 minutes"
        elif total_users < max_throughput * 15:
            assessment = "🟠 MODERATE - Can notify all users in <15 minutes"
        else:
            assessment = "🔴 NEEDS SCALING - Will take >15 minutes to notify all users"
        
        print(f"   {assessment}")
        
        if total_users > 0:
            notification_time = total_users / max_throughput
            print(f"   Time to notify all users: {notification_time:.1f} minutes")
    
    def run_continuous_monitoring(self, interval: int = 10):
        """Run continuous monitoring with specified interval"""
        print("🚀 Starting Notification Batching System Monitor")
        print(f"⏱️  Monitoring interval: {interval} seconds")
        print("Press Ctrl+C to stop")
        
        while self.running:
            try:
                self.print_dashboard()
                time.sleep(interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error during monitoring: {e}")
                time.sleep(interval)
        
        print("\n✅ Monitoring stopped gracefully")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor notification batching system")
    parser.add_argument("--interval", type=int, default=15, help="Monitoring interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    
    args = parser.parse_args()
    
    monitor = NotificationBatchingMonitor()
    
    if args.once:
        monitor.print_dashboard()
    else:
        monitor.run_continuous_monitoring(args.interval)

if __name__ == "__main__":
    main() 