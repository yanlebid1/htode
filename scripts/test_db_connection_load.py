#!/usr/bin/env python3
"""
Database Connection Pool Load Test

This script tests the database connection pool under high load
to verify our scaling improvements work correctly.
"""

import asyncio
import threading
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.db.session import db_session
from common.db.models.user import User
from sqlalchemy import text

class ConnectionPoolLoadTest:
    def __init__(self):
        self.results = []
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    def single_db_operation(self, operation_id: int) -> Dict[str, Any]:
        """Perform a single database operation"""
        start_time = time.time()
        try:
            with db_session() as db:
                # Simulate a real database operation
                # Get user count
                user_count = db.query(User).count()
                
                # Execute a sample query
                result = db.execute(text("SELECT NOW() as current_time, version() as pg_version")).fetchone()
                
                # Simulate some processing time
                time.sleep(0.1)  # 100ms processing
                
                end_time = time.time()
                
                return {
                    "operation_id": operation_id,
                    "success": True,
                    "duration": end_time - start_time,
                    "user_count": user_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "pg_version": result.pg_version[:50] if result else "Unknown"
                }
        
        except Exception as e:
            end_time = time.time()
            return {
                "operation_id": operation_id,
                "success": False,
                "duration": end_time - start_time,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def run_concurrent_test(self, num_connections: int = 30, max_workers: int = 20) -> Dict[str, Any]:
        """Run concurrent database operations to test connection pool"""
        print(f"🚀 Starting load test with {num_connections} concurrent operations...")
        print(f"⚙️  Max workers: {max_workers}")
        
        self.start_time = time.time()
        self.results = []
        self.errors = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_id = {
                executor.submit(self.single_db_operation, i): i 
                for i in range(num_connections)
            }
            
            # Collect results
            for future in as_completed(future_to_id):
                operation_id = future_to_id[future]
                try:
                    result = future.result()
                    if result["success"]:
                        self.results.append(result)
                    else:
                        self.errors.append(result)
                        print(f"❌ Operation {operation_id} failed: {result['error']}")
                except Exception as e:
                    error_result = {
                        "operation_id": operation_id,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    self.errors.append(error_result)
                    print(f"❌ Operation {operation_id} exception: {e}")
        
        self.end_time = time.time()
        return self.get_test_summary()
    
    def get_test_summary(self) -> Dict[str, Any]:
        """Generate test summary statistics"""
        total_operations = len(self.results) + len(self.errors)
        success_count = len(self.results)
        error_count = len(self.errors)
        
        if self.results:
            durations = [r["duration"] for r in self.results]
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
        else:
            avg_duration = min_duration = max_duration = 0
        
        total_time = self.end_time - self.start_time if self.start_time and self.end_time else 0
        
        return {
            "total_operations": total_operations,
            "successful_operations": success_count,
            "failed_operations": error_count,
            "success_rate": (success_count / total_operations) * 100 if total_operations > 0 else 0,
            "total_test_time": total_time,
            "avg_operation_duration": avg_duration,
            "min_operation_duration": min_duration,
            "max_operation_duration": max_duration,
            "operations_per_second": total_operations / total_time if total_time > 0 else 0,
            "errors": self.errors[:5]  # Show first 5 errors
        }
    
    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted test summary"""
        print(f"\n{'='*80}")
        print(f"📊 DATABASE CONNECTION POOL LOAD TEST RESULTS")
        print(f"{'='*80}")
        
        # Overall Results
        print(f"\n📈 Overall Results:")
        print(f"   Total Operations: {summary['total_operations']}")
        print(f"   Successful: {summary['successful_operations']} ✅")
        print(f"   Failed: {summary['failed_operations']} ❌")
        print(f"   Success Rate: {summary['success_rate']:.1f}%")
        
        # Performance Metrics
        print(f"\n⚡ Performance Metrics:")
        print(f"   Total Test Time: {summary['total_test_time']:.2f} seconds")
        print(f"   Operations/Second: {summary['operations_per_second']:.1f}")
        print(f"   Avg Duration: {summary['avg_operation_duration']:.3f} seconds")
        print(f"   Min Duration: {summary['min_operation_duration']:.3f} seconds")
        print(f"   Max Duration: {summary['max_operation_duration']:.3f} seconds")
        
        # Assessment
        success_rate = summary['success_rate']
        if success_rate >= 95:
            status = "🟢 EXCELLENT"
        elif success_rate >= 90:
            status = "🟡 GOOD"
        elif success_rate >= 80:
            status = "🟠 NEEDS IMPROVEMENT"
        else:
            status = "🔴 POOR"
        
        print(f"\n🎯 Assessment: {status}")
        
        # Show errors if any
        if summary['errors']:
            print(f"\n❌ Sample Errors:")
            for i, error in enumerate(summary['errors'][:3], 1):
                print(f"   {i}. {error['error_type']}: {error['error'][:100]}")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if success_rate < 95:
            print("   - Consider increasing database connection pool size")
            print("   - Monitor PostgreSQL max_connections setting")
            print("   - Check for connection leaks in application code")
        else:
            print("   - Connection pool configuration looks good!")
            print("   - Ready for production load")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test database connection pool under load")
    parser.add_argument("--connections", type=int, default=30, help="Number of concurrent connections")
    parser.add_argument("--workers", type=int, default=20, help="Max thread workers")
    parser.add_argument("--iterations", type=int, default=1, help="Number of test iterations")
    
    args = parser.parse_args()
    
    tester = ConnectionPoolLoadTest()
    
    print(f"🔧 Database Connection Pool Load Tester")
    print(f"📊 Test Configuration:")
    print(f"   Concurrent Connections: {args.connections}")
    print(f"   Max Workers: {args.workers}")
    print(f"   Iterations: {args.iterations}")
    
    all_results = []
    
    for iteration in range(args.iterations):
        if args.iterations > 1:
            print(f"\n🔄 Running iteration {iteration + 1}/{args.iterations}")
        
        summary = tester.run_concurrent_test(args.connections, args.workers)
        all_results.append(summary)
        
        if args.iterations == 1:
            tester.print_summary(summary)
        else:
            print(f"   Success Rate: {summary['success_rate']:.1f}%, Ops/sec: {summary['operations_per_second']:.1f}")
    
    # Print aggregate results for multiple iterations
    if args.iterations > 1:
        print(f"\n{'='*80}")
        print(f"📊 AGGREGATE RESULTS ({args.iterations} iterations)")
        print(f"{'='*80}")
        
        avg_success_rate = sum(r['success_rate'] for r in all_results) / len(all_results)
        avg_ops_per_sec = sum(r['operations_per_second'] for r in all_results) / len(all_results)
        total_operations = sum(r['total_operations'] for r in all_results)
        total_errors = sum(r['failed_operations'] for r in all_results)
        
        print(f"   Average Success Rate: {avg_success_rate:.1f}%")
        print(f"   Average Ops/Second: {avg_ops_per_sec:.1f}")
        print(f"   Total Operations: {total_operations}")
        print(f"   Total Errors: {total_errors}")
        
        status = "🟢 EXCELLENT" if avg_success_rate >= 95 else "🟡 GOOD" if avg_success_rate >= 90 else "🔴 NEEDS WORK"
        print(f"   Overall Assessment: {status}")

if __name__ == "__main__":
    main() 