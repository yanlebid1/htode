#!/usr/bin/env python3
"""
Redis Cluster Monitoring Script
Monitors performance and health of the Redis cluster with functional separation.
"""

import asyncio
import time
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from collections import deque
import signal

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from common.utils.redis_cluster_manager import redis_cluster, RedisRole
    CLUSTER_AVAILABLE = True
except ImportError:
    print("⚠️  Redis cluster manager not available, using basic monitoring")
    CLUSTER_AVAILABLE = False
    import redis
    from common.config import REDIS_URL


class RedisClusterMonitor:
    """Monitor Redis cluster performance and health"""
    
    def __init__(self):
        self.running = True
        self.metrics_history = deque(maxlen=60)  # Keep last 60 data points
        self.start_time = datetime.now(timezone.utc)
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        if CLUSTER_AVAILABLE:
            self.roles = list(RedisRole)
        else:
            self.roles = ["legacy"]
    
    def _signal_handler(self, signum, frame):
        print("\n🛑 Received interrupt signal. Shutting down gracefully...")
        self.running = False
    
    def get_redis_metrics(self) -> Dict[str, Dict]:
        """Get comprehensive metrics from all Redis instances"""
        metrics = {}
        
        if CLUSTER_AVAILABLE:
            # Use cluster manager
            for role in RedisRole:
                try:
                    connection = redis_cluster.get_connection(role)
                    info = connection.info()
                    
                    metrics[role.value] = {
                        "connected_clients": info.get("connected_clients", 0),
                        "used_memory": info.get("used_memory", 0),
                        "used_memory_human": info.get("used_memory_human", "0B"),
                        "used_memory_peak": info.get("used_memory_peak", 0),
                        "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                        "keyspace_hits": info.get("keyspace_hits", 0),
                        "keyspace_misses": info.get("keyspace_misses", 0),
                        "total_commands_processed": info.get("total_commands_processed", 0),
                        "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                        "used_cpu_sys": info.get("used_cpu_sys", 0),
                        "used_cpu_user": info.get("used_cpu_user", 0),
                        "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                        "role": info.get("role", "unknown"),
                        "connected": True,
                        "latency_ms": self._measure_latency(connection),
                    }
                    
                    # Calculate hit rate
                    hits = metrics[role.value]["keyspace_hits"]
                    misses = metrics[role.value]["keyspace_misses"]
                    total_requests = hits + misses
                    hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
                    metrics[role.value]["hit_rate"] = round(hit_rate, 2)
                    
                    # Calculate memory usage percentage (assuming 1GB default limit)
                    used_memory_mb = metrics[role.value]["used_memory"] / (1024 * 1024)
                    memory_limit_mb = 1024  # Default limit, could be made configurable
                    memory_usage_percent = (used_memory_mb / memory_limit_mb) * 100
                    metrics[role.value]["memory_usage_percent"] = round(memory_usage_percent, 1)
                    
                except Exception as e:
                    metrics[role.value] = {
                        "connected": False,
                        "error": str(e),
                        "connected_clients": 0,
                        "used_memory": 0,
                        "hit_rate": 0,
                        "instantaneous_ops_per_sec": 0,
                    }
        else:
            # Fallback to legacy Redis monitoring
            try:
                connection = redis.from_url(REDIS_URL)
                info = connection.info()
                
                metrics["legacy"] = {
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                    "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                    "connected": True,
                    "latency_ms": self._measure_latency(connection),
                }
                
                hits = metrics["legacy"]["keyspace_hits"]
                misses = metrics["legacy"]["keyspace_misses"]
                total_requests = hits + misses
                hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
                metrics["legacy"]["hit_rate"] = round(hit_rate, 2)
                
            except Exception as e:
                metrics["legacy"] = {
                    "connected": False,
                    "error": str(e),
                }
        
        return metrics
    
    def _measure_latency(self, connection) -> float:
        """Measure Redis connection latency"""
        try:
            start_time = time.time()
            connection.ping()
            latency = (time.time() - start_time) * 1000  # Convert to milliseconds
            return round(latency, 2)
        except Exception:
            return -1
    
    def calculate_cluster_totals(self, metrics: Dict) -> Dict:
        """Calculate aggregate metrics across the cluster"""
        totals = {
            "total_instances": len(metrics),
            "healthy_instances": 0,
            "unhealthy_instances": 0,
            "total_connected_clients": 0,
            "total_used_memory": 0,
            "total_commands_processed": 0,
            "average_hit_rate": 0,
            "total_ops_per_sec": 0,
            "average_latency": 0,
            "max_latency": 0,
            "min_latency": float('inf'),
        }
        
        hit_rates = []
        latencies = []
        
        for instance, data in metrics.items():
            if data.get("connected", False):
                totals["healthy_instances"] += 1
                totals["total_connected_clients"] += data.get("connected_clients", 0)
                totals["total_used_memory"] += data.get("used_memory", 0)
                totals["total_commands_processed"] += data.get("total_commands_processed", 0)
                totals["total_ops_per_sec"] += data.get("instantaneous_ops_per_sec", 0)
                
                hit_rate = data.get("hit_rate", 0)
                if hit_rate > 0:
                    hit_rates.append(hit_rate)
                
                latency = data.get("latency_ms", -1)
                if latency > 0:
                    latencies.append(latency)
                    totals["max_latency"] = max(totals["max_latency"], latency)
                    totals["min_latency"] = min(totals["min_latency"], latency)
            else:
                totals["unhealthy_instances"] += 1
        
        # Calculate averages
        if hit_rates:
            totals["average_hit_rate"] = round(sum(hit_rates) / len(hit_rates), 2)
        
        if latencies:
            totals["average_latency"] = round(sum(latencies) / len(latencies), 2)
        else:
            totals["min_latency"] = 0
        
        # Convert total memory to human readable
        total_memory_mb = totals["total_used_memory"] / (1024 * 1024)
        totals["total_used_memory_human"] = f"{total_memory_mb:.1f}MB"
        
        return totals
    
    def print_metrics(self, metrics: Dict, totals: Dict):
        """Print formatted Redis cluster metrics"""
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("=" * 80)
        print(f"🔴 REDIS CLUSTER SCALING MONITOR - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Cluster overview
        print(f"\n📊 CLUSTER OVERVIEW:")
        print(f"   Total Instances: {totals['total_instances']}")
        print(f"   Healthy: {totals['healthy_instances']} | Unhealthy: {totals['unhealthy_instances']}")
        print(f"   Total Memory Usage: {totals['total_used_memory_human']}")
        print(f"   Total Connected Clients: {totals['total_connected_clients']}")
        print(f"   Total Ops/sec: {totals['total_ops_per_sec']}")
        print(f"   Average Hit Rate: {totals['average_hit_rate']}%")
        print(f"   Average Latency: {totals['average_latency']}ms")
        
        # Individual instance details
        print(f"\n🔍 INSTANCE DETAILS:")
        print("-" * 80)
        
        for instance, data in metrics.items():
            if data.get("connected", False):
                memory_usage = data.get("memory_usage_percent", 0)
                memory_icon = "🟢" if memory_usage < 70 else "🟡" if memory_usage < 90 else "🔴"
                
                latency = data.get("latency_ms", 0)
                latency_icon = "🟢" if latency < 5 else "🟡" if latency < 20 else "🔴"
                
                hit_rate = data.get("hit_rate", 0)
                hit_rate_icon = "🟢" if hit_rate > 90 else "🟡" if hit_rate > 70 else "🔴"
                
                print(f"✅ {instance.upper()}:")
                print(f"   Memory: {memory_icon} {data.get('used_memory_human', 'N/A')} ({memory_usage:.1f}%)")
                print(f"   Clients: {data.get('connected_clients', 0)} | Ops/sec: {data.get('instantaneous_ops_per_sec', 0)}")
                print(f"   Hit Rate: {hit_rate_icon} {hit_rate}% | Latency: {latency_icon} {latency}ms")
                print(f"   Commands: {data.get('total_commands_processed', 0)} | Uptime: {self._format_uptime(data.get('uptime_in_seconds', 0))}")
            else:
                error = data.get("error", "Unknown error")
                print(f"❌ {instance.upper()}: DISCONNECTED - {error}")
            
            print("")
        
        # Performance alerts
        print(f"⚠️  PERFORMANCE ALERTS:")
        alerts = []
        
        # Check cluster health
        if totals['unhealthy_instances'] > 0:
            alerts.append(f"🚫 CLUSTER UNHEALTHY: {totals['unhealthy_instances']} instance(s) down")
        
        # Check memory usage
        for instance, data in metrics.items():
            if data.get("connected", False):
                memory_usage = data.get("memory_usage_percent", 0)
                if memory_usage > 90:
                    alerts.append(f"🔥 HIGH MEMORY: {instance} using {memory_usage:.1f}%")
                elif memory_usage > 70:
                    alerts.append(f"⚠️  MEMORY WARNING: {instance} using {memory_usage:.1f}%")
        
        # Check hit rates
        if totals['average_hit_rate'] < 80 and totals['total_commands_processed'] > 1000:
            alerts.append(f"📉 LOW HIT RATE: Cluster average {totals['average_hit_rate']}%")
        
        # Check latency
        if totals['average_latency'] > 20:
            alerts.append(f"🐌 HIGH LATENCY: Average {totals['average_latency']}ms")
        
        # Check connection overload
        if totals['total_connected_clients'] > 500:
            alerts.append(f"🔌 HIGH CONNECTIONS: {totals['total_connected_clients']} total clients")
        
        if alerts:
            for alert in alerts:
                print(f"   {alert}")
        else:
            print("   🟢 All systems operating normally")
        
        # Runtime information
        runtime = datetime.now(timezone.utc) - self.start_time
        print(f"\n📈 MONITORING INFO:")
        print(f"   Monitor Runtime: {self._format_uptime(int(runtime.total_seconds()))}")
        print(f"   Data Points Collected: {len(self.metrics_history)}")
        
        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop monitoring")
    
    def _format_uptime(self, seconds: int) -> str:
        """Format uptime in human readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}d {hours}h"
    
    async def monitor_continuous(self, interval: int = 5):
        """Continuously monitor Redis cluster"""
        print("Starting Redis cluster monitoring...")
        
        try:
            while self.running:
                metrics = self.get_redis_metrics()
                totals = self.calculate_cluster_totals(metrics)
                
                # Store metrics for history
                self.metrics_history.append({
                    "timestamp": datetime.now(timezone.utc),
                    "metrics": metrics,
                    "totals": totals
                })
                
                self.print_metrics(metrics, totals)
                
                # Wait for next iteration
                for _ in range(interval):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
        except Exception as e:
            print(f"\nMonitoring error: {e}")
        finally:
            self.running = False
    
    def get_snapshot(self) -> Dict:
        """Get a single snapshot of cluster metrics"""
        metrics = self.get_redis_metrics()
        totals = self.calculate_cluster_totals(metrics)
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cluster_overview": totals,
            "instances": metrics,
            "cluster_available": CLUSTER_AVAILABLE,
        }


async def main():
    """Main monitoring function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor Redis cluster performance")
    parser.add_argument("--interval", "-i", type=int, default=5,
                       help="Monitoring interval in seconds (default: 5)")
    parser.add_argument("--snapshot", "-s", action="store_true",
                       help="Take a single snapshot instead of continuous monitoring")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output in JSON format")
    
    args = parser.parse_args()
    
    monitor = RedisClusterMonitor()
    
    if args.snapshot:
        snapshot = monitor.get_snapshot()
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            totals = snapshot["cluster_overview"]
            metrics = snapshot["instances"]
            monitor.print_metrics(metrics, totals)
    else:
        await monitor.monitor_continuous(args.interval)


if __name__ == "__main__":
    asyncio.run(main()) 