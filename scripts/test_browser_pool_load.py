#!/usr/bin/env python3
"""
Browser Pool Load Testing Script
Tests the browser pool scaling under heavy concurrent load.
"""

import asyncio
import aiohttp
import time
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import sys
from dataclasses import dataclass, asdict

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    concurrent_requests: int = 50
    total_requests: int = 200
    request_delay_range: tuple = (0.1, 2.0)  # Random delay between requests
    timeout: int = 30
    test_duration_minutes: int = 5
    ramp_up_time: int = 30  # Seconds to gradually increase load


@dataclass 
class RequestResult:
    """Result of a single browser request"""
    service_url: str
    start_time: float
    end_time: float
    duration: float
    status: str
    error: Optional[str] = None
    final_url: Optional[str] = None
    content_length: int = 0


class BrowserPoolLoadTester:
    """Load tester for browser pool scaling"""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.camoufox_services = [
            "http://localhost:8100",
            "http://localhost:8101", 
            "http://localhost:8102",
        ]
        self.session = None
        self.results: List[RequestResult] = []
        self.test_urls = [
            "https://httpbin.org/delay/1",
            "https://httpbin.org/html",
            "https://httpbin.org/json",
            "https://httpbin.org/robots.txt",
            "https://httpbin.org/user-agent",
            "https://example.com",
            "https://httpbin.org/status/200",
            "https://httpbin.org/headers",
        ]
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_browser_request(self, service_url: str, test_url: str) -> RequestResult:
        """Make a single browser automation request"""
        start_time = time.time()
        
        request_payload = {
            "url": test_url,
            "wait_after_load": random.randint(1000, 3000),
            "timeout": self.config.timeout
        }
        
        try:
            async with self.session.post(
                f"{service_url}/browse",
                json=request_payload
            ) as response:
                end_time = time.time()
                duration = end_time - start_time
                
                if response.status == 200:
                    data = await response.json()
                    return RequestResult(
                        service_url=service_url,
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        status=data.get("status", "unknown"),
                        final_url=data.get("final_url"),
                        content_length=len(data.get("content", ""))
                    )
                else:
                    return RequestResult(
                        service_url=service_url,
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        status="error",
                        error=f"HTTP {response.status}"
                    )
                    
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            return RequestResult(
                service_url=service_url,
                start_time=start_time,
                end_time=end_time, 
                duration=duration,
                status="error",
                error=str(e)
            )
    
    async def run_burst_test(self) -> List[RequestResult]:
        """Run a burst of concurrent requests"""
        print(f"🚀 Starting burst test: {self.config.concurrent_requests} concurrent requests")
        
        tasks = []
        for i in range(self.config.concurrent_requests):
            # Distribute requests across services
            service_url = random.choice(self.camoufox_services)
            test_url = random.choice(self.test_urls)
            
            # Add random delay for realistic load pattern
            delay = random.uniform(*self.config.request_delay_range)
            
            task = asyncio.create_task(self.make_delayed_request(service_url, test_url, delay))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and convert to RequestResult objects
        valid_results = []
        for result in results:
            if isinstance(result, RequestResult):
                valid_results.append(result)
            elif isinstance(result, Exception):
                print(f"Task exception: {result}")
        
        return valid_results
    
    async def make_delayed_request(self, service_url: str, test_url: str, delay: float) -> RequestResult:
        """Make a request after a delay"""
        await asyncio.sleep(delay)
        return await self.make_browser_request(service_url, test_url)
    
    async def run_sustained_test(self) -> List[RequestResult]:
        """Run sustained load test over time"""
        print(f"⏱️  Starting sustained test: {self.config.test_duration_minutes} minutes")
        
        test_start = time.time()
        test_end = test_start + (self.config.test_duration_minutes * 60)
        all_results = []
        
        request_count = 0
        while time.time() < test_end:
            # Calculate current load level (ramp up)
            elapsed = time.time() - test_start
            ramp_factor = min(1.0, elapsed / self.config.ramp_up_time)
            current_concurrency = int(self.config.concurrent_requests * ramp_factor)
            
            if current_concurrency == 0:
                current_concurrency = 1
            
            print(f"🔄 Wave {request_count + 1}: {current_concurrency} concurrent requests")
            
            # Create batch of requests
            tasks = []
            for i in range(current_concurrency):
                service_url = random.choice(self.camoufox_services)
                test_url = random.choice(self.test_urls)
                delay = random.uniform(0, 1)  # Short delays within batch
                
                task = asyncio.create_task(self.make_delayed_request(service_url, test_url, delay))
                tasks.append(task)
            
            # Execute batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                if isinstance(result, RequestResult):
                    all_results.append(result)
            
            request_count += current_concurrency
            
            # Wait before next wave
            await asyncio.sleep(random.uniform(5, 15))
        
        return all_results
    
    def analyze_results(self, results: List[RequestResult]) -> Dict:
        """Analyze load test results"""
        if not results:
            return {"error": "No results to analyze"}
        
        # Basic statistics
        total_requests = len(results)
        successful_requests = len([r for r in results if r.status == "success"])
        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests) * 100
        
        # Performance statistics
        durations = [r.duration for r in results]
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        
        # Percentiles
        sorted_durations = sorted(durations)
        p50 = sorted_durations[int(len(sorted_durations) * 0.5)]
        p95 = sorted_durations[int(len(sorted_durations) * 0.95)]
        p99 = sorted_durations[int(len(sorted_durations) * 0.99)]
        
        # Service distribution
        service_counts = {}
        service_success_rates = {}
        
        for result in results:
            service = result.service_url
            if service not in service_counts:
                service_counts[service] = {"total": 0, "successful": 0}
            
            service_counts[service]["total"] += 1
            if result.status == "success":
                service_counts[service]["successful"] += 1
        
        for service, counts in service_counts.items():
            service_success_rates[service] = (counts["successful"] / counts["total"]) * 100
        
        # Error analysis
        error_types = {}
        for result in results:
            if result.status == "error" and result.error:
                error_type = result.error.split(":")[0]  # Get first part of error
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Timeline analysis
        test_start = min(r.start_time for r in results)
        test_end = max(r.end_time for r in results)
        total_test_time = test_end - test_start
        requests_per_second = total_requests / total_test_time if total_test_time > 0 else 0
        
        return {
            "summary": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "success_rate": round(success_rate, 2),
                "total_test_time": round(total_test_time, 2),
                "requests_per_second": round(requests_per_second, 2),
            },
            "performance": {
                "avg_duration": round(avg_duration, 3),
                "min_duration": round(min_duration, 3),
                "max_duration": round(max_duration, 3),
                "p50_duration": round(p50, 3),
                "p95_duration": round(p95, 3),
                "p99_duration": round(p99, 3),
            },
            "service_distribution": {
                service: {
                    "total_requests": counts["total"],
                    "successful_requests": counts["successful"],
                    "success_rate": round(service_success_rates[service], 2)
                }
                for service, counts in service_counts.items()
            },
            "error_analysis": error_types,
            "test_config": asdict(self.config)
        }
    
    def print_results(self, analysis: Dict):
        """Print formatted test results"""
        print("\n" + "=" * 80)
        print("🎯 BROWSER POOL LOAD TEST RESULTS")
        print("=" * 80)
        
        # Summary
        summary = analysis["summary"]
        print(f"\n📊 SUMMARY:")
        print(f"   Total Requests: {summary['total_requests']}")
        print(f"   Successful: {summary['successful_requests']}")
        print(f"   Failed: {summary['failed_requests']}")
        print(f"   Success Rate: {summary['success_rate']}%")
        print(f"   Test Duration: {summary['total_test_time']:.2f}s")
        print(f"   Throughput: {summary['requests_per_second']:.2f} req/s")
        
        # Performance
        perf = analysis["performance"]
        print(f"\n⚡ PERFORMANCE:")
        print(f"   Average Response Time: {perf['avg_duration']:.3f}s")
        print(f"   Min Response Time: {perf['min_duration']:.3f}s")
        print(f"   Max Response Time: {perf['max_duration']:.3f}s")
        print(f"   50th Percentile: {perf['p50_duration']:.3f}s")
        print(f"   95th Percentile: {perf['p95_duration']:.3f}s")
        print(f"   99th Percentile: {perf['p99_duration']:.3f}s")
        
        # Service distribution
        print(f"\n🎯 SERVICE DISTRIBUTION:")
        for service, stats in analysis["service_distribution"].items():
            service_name = service.split(":")[-1]  # Get port number
            print(f"   {service_name}: {stats['total_requests']} requests, "
                  f"{stats['success_rate']}% success rate")
        
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
        
        if perf["p95_duration"] <= 5.0:
            assessments.append("🟢 Excellent response times (p95 ≤5s)")
        elif perf["p95_duration"] <= 10.0:
            assessments.append("🟡 Acceptable response times (p95 ≤10s)")
        else:
            assessments.append("🔴 Slow response times (p95 >10s)")
        
        if summary["requests_per_second"] >= 10:
            assessments.append("🟢 High throughput (≥10 req/s)")
        elif summary["requests_per_second"] >= 5:
            assessments.append("🟡 Moderate throughput (≥5 req/s)")
        else:
            assessments.append("🔴 Low throughput (<5 req/s)")
        
        for assessment in assessments:
            print(f"   {assessment}")
        
        print("\n" + "=" * 80)


async def main():
    """Main load testing function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load test browser pool scaling")
    parser.add_argument("--concurrent", "-c", type=int, default=50,
                       help="Number of concurrent requests (default: 50)")
    parser.add_argument("--total", "-t", type=int, default=200,
                       help="Total number of requests for burst test (default: 200)")
    parser.add_argument("--duration", "-d", type=int, default=5,
                       help="Test duration in minutes for sustained test (default: 5)")
    parser.add_argument("--timeout", type=int, default=30,
                       help="Request timeout in seconds (default: 30)")
    parser.add_argument("--test-type", choices=["burst", "sustained"], default="burst",
                       help="Type of load test to run (default: burst)")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output results in JSON format")
    
    args = parser.parse_args()
    
    config = LoadTestConfig(
        concurrent_requests=args.concurrent,
        total_requests=args.total,
        test_duration_minutes=args.duration,
        timeout=args.timeout
    )
    
    async with BrowserPoolLoadTester(config) as tester:
        print(f"🧪 Starting {args.test_type} load test...")
        print(f"Configuration: {args.concurrent} concurrent, timeout: {args.timeout}s")
        
        start_time = time.time()
        
        if args.test_type == "burst":
            results = await tester.run_burst_test()
        else:
            results = await tester.run_sustained_test()
        
        end_time = time.time()
        
        print(f"\n✅ Load test completed in {end_time - start_time:.2f} seconds")
        print(f"Total results collected: {len(results)}")
        
        # Analyze and display results
        analysis = tester.analyze_results(results)
        
        if args.json:
            print(json.dumps(analysis, indent=2))
        else:
            tester.print_results(analysis)


if __name__ == "__main__":
    asyncio.run(main()) 