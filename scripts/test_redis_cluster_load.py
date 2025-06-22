#!/usr/bin/env python3
"""
Redis Cluster Load Testing Script
Tests the Redis cluster scaling under heavy concurrent loads across all functional roles.
"""

import asyncio
import time
import json
import random
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from common.utils.redis_cluster_manager import redis_cluster, RedisRole
    CLUSTER_AVAILABLE = True
except ImportError:
    print("⚠️  Redis cluster manager not available, using basic testing")
    CLUSTER_AVAILABLE = False
    import redis
    from common.config import REDIS_URL


@dataclass
class LoadTestConfig:
    """Configuration for Redis cluster load testing"""
    concurrent_operations: int = 100
    total_operations: int = 1000
    test_duration_minutes: int = 5
    operation_types: List[str] = None
    key_pattern: str = "loadtest:{role}:{thread}:{key}"
    value_size_kb: int = 1
    
    def __post_init__(self):
        if self.operation_types is None:
            self.operation_types = ["set", "get", "delete", "exists", "incr"]


@dataclass
class OperationResult:
    """Result of a single Redis operation"""
    role: str
    operation: str
    success: bool
    latency_ms: float
    error: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class RedisClusterLoadTester:
    """Load tester for Redis cluster with functional separation"""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results: List[OperationResult] = []
        self.results_lock = threading.Lock()
        self.test_data = {}
        
        # Generate test data
        self._generate_test_data()
        
        if CLUSTER_AVAILABLE:
            self.roles = list(RedisRole)
        else:
            self.roles = ["legacy"]
    
    def _generate_test_data(self):
        """Generate test data of specified size"""
        # Create test values of different sizes
        kb_data = "x" * (self.config.value_size_kb * 1024)
        
        self.test_data = {
            "small": "test_value",
            "medium": kb_data[:100],
            "large": kb_data,
            "json": json.dumps({
                "id": 12345,
                "name": "Test Object",
                "data": [1, 2, 3, 4, 5],
                "metadata": {"created": datetime.now().isoformat()}
            }),
            "list": [f"item_{i}" for i in range(10)],
            "number": 42
        }
    
    def get_redis_connection(self, role: str):
        """Get Redis connection for a specific role"""
        if CLUSTER_AVAILABLE:
            if role == "queue":
                return redis_cluster.get_queue_redis()
            elif role == "cache":
                return redis_cluster.get_cache_redis()
            elif role == "state":
                return redis_cluster.get_state_redis()
            elif role == "analytics":
                return redis_cluster.get_analytics_redis()
            else:
                return redis_cluster.get_cache_redis()  # Default
        else:
            return redis.from_url(REDIS_URL)
    
    def generate_key(self, role: str, thread_id: int, key_suffix: str = None) -> str:
        """Generate a test key for the given role and thread"""
        if key_suffix is None:
            key_suffix = str(uuid.uuid4())[:8]
        
        return self.config.key_pattern.format(
            role=role,
            thread=thread_id,
            key=key_suffix
        )
    
    def execute_operation(self, role: str, operation: str, thread_id: int) -> OperationResult:
        """Execute a single Redis operation"""
        start_time = time.time()
        
        try:
            connection = self.get_redis_connection(role)
            
            if operation == "set":
                key = self.generate_key(role, thread_id)
                value = random.choice(list(self.test_data.values()))
                connection.set(key, value, ex=300)  # 5 minute expiry
                
            elif operation == "get":
                # Try to get existing keys first, fallback to new key
                key = self.generate_key(role, thread_id, "existing")
                result = connection.get(key)
                if result is None:
                    # Set and get a new key
                    value = self.test_data["small"]
                    connection.set(key, value, ex=300)
                    connection.get(key)
                
            elif operation == "delete":
                key = self.generate_key(role, thread_id)
                connection.set(key, "temp_value")  # Set first, then delete
                connection.delete(key)
                
            elif operation == "exists":
                key = self.generate_key(role, thread_id)
                connection.exists(key)
                
            elif operation == "incr":
                key = self.generate_key(role, thread_id, "counter")
                connection.incr(key)
                connection.expire(key, 300)
                
            elif operation == "pipeline":
                # Test pipeline operations
                with connection.pipeline() as pipe:
                    for i in range(5):
                        key = self.generate_key(role, thread_id, f"pipe_{i}")
                        pipe.set(key, f"pipeline_value_{i}", ex=300)
                    pipe.execute()
                
            elif operation == "list_ops":
                # Test list operations
                key = self.generate_key(role, thread_id, "list")
                connection.lpush(key, *self.test_data["list"])
                connection.lrange(key, 0, -1)
                connection.expire(key, 300)
                
            elif operation == "hash_ops":
                # Test hash operations
                key = self.generate_key(role, thread_id, "hash")
                hash_data = {"field1": "value1", "field2": "value2", "field3": "value3"}
                connection.hset(key, mapping=hash_data)
                connection.hgetall(key)
                connection.expire(key, 300)
            
            else:
                raise ValueError(f"Unknown operation: {operation}")
            
            latency = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            return OperationResult(
                role=role,
                operation=operation,
                success=True,
                latency_ms=round(latency, 2)
            )
            
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return OperationResult(
                role=role,
                operation=operation,
                success=False,
                latency_ms=round(latency, 2),
                error=str(e)
            )
    
    def worker_thread(self, thread_id: int, operations_per_thread: int):
        """Worker thread that executes Redis operations"""
        for _ in range(operations_per_thread):
            # Randomly select role and operation
            if CLUSTER_AVAILABLE:
                role = random.choice([r.value for r in RedisRole])
            else:
                role = "legacy"
            
            operation = random.choice(self.config.operation_types)
            
            # Execute operation
            result = self.execute_operation(role, operation, thread_id)
            
            # Store result
            with self.results_lock:
                self.results.append(result)
            
            # Small random delay to simulate realistic usage
            time.sleep(random.uniform(0.001, 0.01))
    
    def run_concurrent_test(self) -> List[OperationResult]:
        """Run concurrent load test"""
        print(f"🚀 Starting concurrent test: {self.config.concurrent_operations} threads")
        
        operations_per_thread = self.config.total_operations // self.config.concurrent_operations
        
        start_time = time.time()
        
        # Create and start threads
        threads = []
        for thread_id in range(self.config.concurrent_operations):
            thread = threading.Thread(
                target=self.worker_thread,
                args=(thread_id, operations_per_thread)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        
        print(f"✅ Concurrent test completed in {end_time - start_time:.2f} seconds")
        print(f"Total operations executed: {len(self.results)}")
        
        return self.results.copy()
    
    def run_sustained_test(self) -> List[OperationResult]:
        """Run sustained load test over time"""
        print(f"⏱️  Starting sustained test: {self.config.test_duration_minutes} minutes")
        
        test_start = time.time()
        test_end = test_start + (self.config.test_duration_minutes * 60)
        
        wave_count = 0
        while time.time() < test_end:
            wave_count += 1
            wave_start = time.time()
            
            print(f"🔄 Wave {wave_count}: {self.config.concurrent_operations} concurrent operations")
            
            # Create threads for this wave
            threads = []
            operations_per_thread = 10  # Smaller batches for sustained testing
            
            for thread_id in range(self.config.concurrent_operations):
                thread = threading.Thread(
                    target=self.worker_thread,
                    args=(thread_id + (wave_count * 1000), operations_per_thread)
                )
                threads.append(thread)
                thread.start()
            
            # Wait for wave to complete
            for thread in threads:
                thread.join()
            
            wave_duration = time.time() - wave_start
            print(f"   Wave {wave_count} completed in {wave_duration:.2f}s")
            
            # Brief pause between waves
            time.sleep(random.uniform(2, 5))
        
        total_duration = time.time() - test_start
        print(f"✅ Sustained test completed in {total_duration:.2f} seconds")
        print(f"Total operations executed: {len(self.results)}")
        
        return self.results.copy()
    
    def analyze_results(self, results: List[OperationResult]) -> Dict[str, Any]:
        """Analyze load test results"""
        if not results:
            return {"error": "No results to analyze"}
        
        # Basic statistics
        total_operations = len(results)
        successful_operations = len([r for r in results if r.success])
        failed_operations = total_operations - successful_operations
        success_rate = (successful_operations / total_operations) * 100
        
        # Performance statistics
        latencies = [r.latency_ms for r in results if r.success]
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            
            # Percentiles
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        else:
            avg_latency = min_latency = max_latency = p50 = p95 = p99 = 0
        
        # Role-based analysis
        role_stats = {}
        for result in results:
            role = result.role
            if role not in role_stats:
                role_stats[role] = {"total": 0, "successful": 0, "latencies": []}
            
            role_stats[role]["total"] += 1
            if result.success:
                role_stats[role]["successful"] += 1
                role_stats[role]["latencies"].append(result.latency_ms)
        
        # Calculate role success rates and average latencies
        for role, stats in role_stats.items():
            stats["success_rate"] = (stats["successful"] / stats["total"]) * 100
            if stats["latencies"]:
                stats["avg_latency"] = sum(stats["latencies"]) / len(stats["latencies"])
            else:
                stats["avg_latency"] = 0
        
        # Operation-based analysis
        operation_stats = {}
        for result in results:
            operation = result.operation
            if operation not in operation_stats:
                operation_stats[operation] = {"total": 0, "successful": 0, "latencies": []}
            
            operation_stats[operation]["total"] += 1
            if result.success:
                operation_stats[operation]["successful"] += 1
                operation_stats[operation]["latencies"].append(result.latency_ms)
        
        # Calculate operation success rates and average latencies
        for operation, stats in operation_stats.items():
            stats["success_rate"] = (stats["successful"] / stats["total"]) * 100
            if stats["latencies"]:
                stats["avg_latency"] = sum(stats["latencies"]) / len(stats["latencies"])
            else:
                stats["avg_latency"] = 0
        
        # Error analysis
        error_types = {}
        for result in results:
            if not result.success and result.error:
                error_type = result.error.split(":")[0]  # Get first part of error
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Timeline analysis
        if results:
            test_start = min(r.timestamp for r in results)
            test_end = max(r.timestamp for r in results)
            total_test_time = test_end - test_start
            operations_per_second = total_operations / total_test_time if total_test_time > 0 else 0
        else:
            total_test_time = operations_per_second = 0
        
        return {
            "summary": {
                "total_operations": total_operations,
                "successful_operations": successful_operations,
                "failed_operations": failed_operations,
                "success_rate": round(success_rate, 2),
                "total_test_time": round(total_test_time, 2),
                "operations_per_second": round(operations_per_second, 2),
            },
            "performance": {
                "avg_latency": round(avg_latency, 3),
                "min_latency": round(min_latency, 3),
                "max_latency": round(max_latency, 3),
                "p50_latency": round(p50, 3),
                "p95_latency": round(p95, 3),
                "p99_latency": round(p99, 3),
            },
            "role_analysis": {
                role: {
                    "total_operations": stats["total"],
                    "successful_operations": stats["successful"],
                    "success_rate": round(stats["success_rate"], 2),
                    "avg_latency": round(stats["avg_latency"], 3)
                }
                for role, stats in role_stats.items()
            },
            "operation_analysis": {
                operation: {
                    "total_operations": stats["total"],
                    "successful_operations": stats["successful"],
                    "success_rate": round(stats["success_rate"], 2),
                    "avg_latency": round(stats["avg_latency"], 3)
                }
                for operation, stats in operation_stats.items()
            },
            "error_analysis": error_types,
            "test_config": asdict(self.config)
        }
    
    def print_results(self, analysis: Dict):
        """Print formatted test results"""
        print("\n" + "=" * 80)
        print("🔴 REDIS CLUSTER LOAD TEST RESULTS")
        print("=" * 80)
        
        # Summary
        summary = analysis["summary"]
        print(f"\n📊 SUMMARY:")
        print(f"   Total Operations: {summary['total_operations']}")
        print(f"   Successful: {summary['successful_operations']}")
        print(f"   Failed: {summary['failed_operations']}")
        print(f"   Success Rate: {summary['success_rate']}%")
        print(f"   Test Duration: {summary['total_test_time']:.2f}s")
        print(f"   Throughput: {summary['operations_per_second']:.2f} ops/s")
        
        # Performance
        perf = analysis["performance"]
        print(f"\n⚡ PERFORMANCE:")
        print(f"   Average Latency: {perf['avg_latency']:.3f}ms")
        print(f"   Min Latency: {perf['min_latency']:.3f}ms")
        print(f"   Max Latency: {perf['max_latency']:.3f}ms")
        print(f"   50th Percentile: {perf['p50_latency']:.3f}ms")
        print(f"   95th Percentile: {perf['p95_latency']:.3f}ms")
        print(f"   99th Percentile: {perf['p99_latency']:.3f}ms")
        
        # Role analysis
        print(f"\n🎯 ROLE ANALYSIS:")
        for role, stats in analysis["role_analysis"].items():
            print(f"   {role.upper()}: {stats['total_operations']} ops, "
                  f"{stats['success_rate']}% success, {stats['avg_latency']:.3f}ms avg")
        
        # Operation analysis
        print(f"\n🔧 OPERATION ANALYSIS:")
        for operation, stats in analysis["operation_analysis"].items():
            print(f"   {operation.upper()}: {stats['total_operations']} ops, "
                  f"{stats['success_rate']}% success, {stats['avg_latency']:.3f}ms avg")
        
        # Errors
        if analysis["error_analysis"]:
            print(f"\n❌ ERROR ANALYSIS:")
            for error_type, count in analysis["error_analysis"].items():
                print(f"   {error_type}: {count} occurrences")
        
        # Performance assessment
        print(f"\n🏆 PERFORMANCE ASSESSMENT:")
        assessments = []
        
        if summary["success_rate"] >= 99:
            assessments.append("🟢 Excellent success rate (≥99%)")
        elif summary["success_rate"] >= 95:
            assessments.append("🟡 Good success rate (≥95%)")
        else:
            assessments.append("🔴 Poor success rate (<95%)")
        
        if perf["p95_latency"] <= 10.0:
            assessments.append("🟢 Excellent latency (p95 ≤10ms)")
        elif perf["p95_latency"] <= 50.0:
            assessments.append("🟡 Acceptable latency (p95 ≤50ms)")
        else:
            assessments.append("🔴 High latency (p95 >50ms)")
        
        if summary["operations_per_second"] >= 1000:
            assessments.append("🟢 High throughput (≥1000 ops/s)")
        elif summary["operations_per_second"] >= 500:
            assessments.append("🟡 Moderate throughput (≥500 ops/s)")
        else:
            assessments.append("🔴 Low throughput (<500 ops/s)")
        
        for assessment in assessments:
            print(f"   {assessment}")
        
        print("\n" + "=" * 80)


def main():
    """Main load testing function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load test Redis cluster scaling")
    parser.add_argument("--concurrent", "-c", type=int, default=50,
                       help="Number of concurrent threads (default: 50)")
    parser.add_argument("--total", "-t", type=int, default=1000,
                       help="Total number of operations for concurrent test (default: 1000)")
    parser.add_argument("--duration", "-d", type=int, default=5,
                       help="Test duration in minutes for sustained test (default: 5)")
    parser.add_argument("--test-type", choices=["concurrent", "sustained"], default="concurrent",
                       help="Type of load test to run (default: concurrent)")
    parser.add_argument("--operations", nargs="+", 
                       choices=["set", "get", "delete", "exists", "incr", "pipeline", "list_ops", "hash_ops"],
                       default=["set", "get", "delete", "exists", "incr"],
                       help="Redis operations to test (default: set get delete exists incr)")
    parser.add_argument("--value-size", type=int, default=1,
                       help="Size of test values in KB (default: 1)")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output results in JSON format")
    
    args = parser.parse_args()
    
    config = LoadTestConfig(
        concurrent_operations=args.concurrent,
        total_operations=args.total,
        test_duration_minutes=args.duration,
        operation_types=args.operations,
        value_size_kb=args.value_size
    )
    
    tester = RedisClusterLoadTester(config)
    
    print(f"🧪 Starting {args.test_type} load test...")
    print(f"Configuration: {args.concurrent} concurrent, {args.value_size}KB values")
    if CLUSTER_AVAILABLE:
        print(f"Redis cluster roles: {[r.value for r in RedisRole]}")
    else:
        print("Using legacy Redis connection")
    
    start_time = time.time()
    
    if args.test_type == "concurrent":
        results = tester.run_concurrent_test()
    else:
        results = tester.run_sustained_test()
    
    end_time = time.time()
    
    print(f"\n✅ Load test completed in {end_time - start_time:.2f} seconds")
    
    # Analyze and display results
    analysis = tester.analyze_results(results)
    
    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        tester.print_results(analysis)


if __name__ == "__main__":
    main() 