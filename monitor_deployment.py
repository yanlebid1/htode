#!/usr/bin/env python3
"""
Monitor deployment health and queue status during parser deployments.

Usage:
    python monitor_deployment.py [--interval SECONDS] [--duration MINUTES]
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta, timezone
import redis
import psutil
import docker
from typing import Dict
import json

# Add project root to path
sys.path.insert(0, ".")

from common.config import REDIS_URL
from common.db.session import db_session
from common.db.models import Ad
from sqlalchemy import func


class DeploymentMonitor:
    def __init__(self):
        self.redis_client = redis.from_url(REDIS_URL)
        self.docker_client = docker.from_env()
        self.start_time = datetime.now(timezone.utc)
        self.metrics = {
            "queue_lengths": [],
            "error_counts": [],
            "processing_rates": [],
            "service_health": [],
        }

    def get_queue_status(self) -> Dict[str, int]:
        """Get current queue lengths"""
        queues = {
            "scraper_queue": self.redis_client.llen("scraper_queue"),
            "priority_queue": self.redis_client.llen("priority_queue"),
            "phone_extraction_queue": self.redis_client.llen("phone_extraction_queue"),
            "notification_queue": self.redis_client.llen("notification_queue"),
            "telegram_queue": self.redis_client.llen("telegram_queue"),
            "maintenance_queue": self.redis_client.llen("maintenance_queue"),
            "celery.dead": self.redis_client.llen("celery.dead"),
            "celery.retry": self.redis_client.llen("celery.retry"),
        }
        return queues

    def get_queue_details(self) -> Dict[str, Dict]:
        """Get detailed queue information"""
        queues = {
            "scraper_queue": {
                "length": self.redis_client.llen("scraper_queue"),
                "purpose": "Ad fetching",
                "workers": 2,
            },
            "phone_extraction_queue": {
                "length": self.redis_client.llen("phone_extraction_queue"),
                "purpose": "Phone extraction",
                "workers": 8,
            },
            "notification_queue": {
                "length": self.redis_client.llen("notification_queue"),
                "purpose": "User notifications",
                "workers": 16,
            },
            "telegram_queue": {
                "length": self.redis_client.llen("telegram_queue"),
                "purpose": "Telegram messages",
                "workers": 8,
            },
            "priority_queue": {
                "length": self.redis_client.llen("priority_queue"),
                "purpose": "High-priority tasks",
                "workers": 4,
            },
            "maintenance_queue": {
                "length": self.redis_client.llen("maintenance_queue"),
                "purpose": "Maintenance tasks",
                "workers": 2,
            },
        }

        # Calculate processing rate per queue
        for queue_name, info in queues.items():
            rate_key = f"{queue_name}_processed"
            processed = self.redis_client.get(rate_key)
            info["rate"] = int(processed) / 60 if processed else 0.0  # per minute

        return queues

    def get_service_status(self) -> Dict[str, str]:
        """Get status of all services"""
        services = {}
        service_names = [
            "notifier_service",
            "phone_extraction_worker",
            "notification_batch_worker",
            "telegram_service",
            "telegram_worker",
            "scraper_worker_service",
            "webcrawler_service",
            "camoufox_service",
            "maintenance_worker",
        ]

        for container in self.docker_client.containers.list():
            if container.name in service_names:
                services[container.name] = container.status

        return services

    def get_error_rates(self) -> Dict[str, int]:
        """Get error counts from logs in last 5 minutes"""
        errors = {}

        try:
            # Get notifier service container
            container = self.docker_client.containers.get("notifier_service")

            # Get logs from last 5 minutes
            since = datetime.now(timezone.utc) - timedelta(minutes=5)
            logs = container.logs(since=since.timestamp(), timestamps=True).decode(
                "utf-8"
            )

            # Count different error types
            error_patterns = {
                "extraction_failed": "extraction_failed",
                "phone_parser_error": "Phone extraction failed",
                "http_error": "HTTP error",
                "timeout_error": "Timeout",
                "parser_error": "Parser error",
            }

            for error_type, pattern in error_patterns.items():
                errors[error_type] = logs.count(pattern)

        except Exception as e:
            print(f"Error getting logs: {e}")

        return errors

    def get_processing_rate(self) -> float:
        """Calculate ads processed per minute"""
        try:
            with db_session() as db:
                # Count ads created in last minute
                one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
                count = (
                    db.query(func.count(Ad.id))
                    .filter(Ad.created_at >= one_minute_ago)
                    .scalar()
                )
                return float(count)
        except Exception:
            return 0.0

    def print_dashboard(self):
        """Print monitoring dashboard"""
        # Clear screen
        print("\033[2J\033[H")

        # Header
        print("=" * 80)
        print(f"📊 DEPLOYMENT MONITOR - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Running for: {datetime.now(timezone.utc) - self.start_time}")
        print("=" * 80)

        # Queue Status
        queue_details = self.get_queue_details()
        queues = self.get_queue_status()

        print("\n📬 QUEUE STATUS:")
        for queue_name, details in queue_details.items():
            length = details["length"]
            purpose = details["purpose"]
            workers = details["workers"]
            rate = details["rate"]

            # Show priority with colors/symbols
            if "scraper" in queue_name:
                priority_symbol = "🔴"  # High priority
            elif "phone" in queue_name:
                priority_symbol = "🟡"  # Medium priority
            else:
                priority_symbol = "🟢"  # Low priority

            print(
                f"   {priority_symbol} {queue_name:<20} {length:>6} tasks | {purpose:<20} | {workers} workers | {rate:>4.1f}/min"
            )

        print(f"\n   🔧 Retry Queue:    {queues['celery.retry']:>6} tasks")
        print(f"   💀 Dead Letter:    {queues['celery.dead']:>6} tasks")

        # Queue trend for main queues
        if len(self.metrics["queue_lengths"]) > 1:
            total_now = sum(details["length"] for details in queue_details.values())
            total_prev = sum(
                self.metrics["queue_lengths"][-1].get(q, 0)
                for q in queue_details.keys()
            )
            trend = total_now - total_prev
            trend_symbol = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
            print(f"\n   Overall Trend: {trend_symbol} {abs(trend):+d} tasks")

        # Service Status
        services = self.get_service_status()
        print("\n🏃 SERVICE STATUS:")
        for service, status in services.items():
            status_symbol = "✅" if status == "running" else "❌"
            clean_name = service.replace("htode_", "").replace("_1", "")
            print(f"   {status_symbol} {clean_name:<20} {status}")

        # Error Rates
        errors = self.get_error_rates()
        total_errors = sum(errors.values())
        print(f"\n⚠️  ERROR RATES (last 5 min): {total_errors} total")
        if total_errors > 0:
            for error_type, count in errors.items():
                if count > 0:
                    print(f"   - {error_type}: {count}")

        # Processing Rate
        rate = self.get_processing_rate()
        print(f"\n⚡ PROCESSING RATE: {rate:.1f} ads/minute")

        # System Resources
        print("\n💻 SYSTEM RESOURCES:")
        print(f"   CPU Usage:    {psutil.cpu_percent():>5.1f}%")
        print(f"   Memory Usage: {psutil.virtual_memory().percent:>5.1f}%")

        # Alerts
        alerts = []
        if queues["celery.dead"] > 0:
            alerts.append(f"🚨 {queues['celery.dead']} tasks in dead letter queue!")
        if total_errors > 10:
            alerts.append(f"🚨 High error rate: {total_errors} errors in 5 minutes!")

        # Check for queue backlogs based on queue type
        if queue_details["scraper_queue"]["length"] > 100:
            alerts.append(
                f"⚠️  Scraper backlog: {queue_details['scraper_queue']['length']} tasks pending"
            )
        if queue_details["phone_extraction_queue"]["length"] > 500:
            alerts.append(
                f"⚠️  Phone extraction backlog: {queue_details['phone_extraction_queue']['length']} tasks pending"
            )
        if queue_details["notification_queue"]["length"] > 5000:
            alerts.append(
                f"⚠️  Notification backlog: {queue_details['notification_queue']['length']} tasks pending"
            )

        if alerts:
            print("\n🚨 ALERTS:")
            for alert in alerts:
                print(f"   {alert}")

        # Store metrics
        self.metrics["queue_lengths"].append(queues)
        self.metrics["error_counts"].append(total_errors)
        self.metrics["processing_rates"].append(rate)
        self.metrics["service_health"].append(
            len([s for s in services.values() if s == "running"])
        )

    def save_metrics(self):
        """Save metrics to file for analysis"""
        filename = (
            f"deployment_metrics_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(filename, "w") as f:
            json.dump(
                {
                    "start_time": self.start_time.isoformat(),
                    "end_time": datetime.now(timezone.utc).isoformat(),
                    "metrics": self.metrics,
                },
                f,
                indent=2,
            )

        print(f"\n📊 Metrics saved to {filename}")

    async def monitor(self, interval: int = 5, duration: int = None):
        """Run monitoring loop"""
        end_time = datetime.now(timezone.utc) + timedelta(minutes=duration) if duration else None

        try:
            while True:
                self.print_dashboard()

                if end_time and datetime.now(timezone.utc) >= end_time:
                    print("\n⏰ Monitoring duration reached")
                    break

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n👋 Monitoring stopped")
        finally:
            self.save_metrics()


def main():
    parser = argparse.ArgumentParser(description="Monitor deployment health")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Update interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Monitoring duration in minutes (default: unlimited)",
    )

    args = parser.parse_args()

    monitor = DeploymentMonitor()
    asyncio.run(monitor.monitor(args.interval, args.duration))


if __name__ == "__main__":
    main()
