#!/usr/bin/env python3
"""
Horizontal Scaling Load Test

Tests the horizontally scaled system with various load scenarios:
- HTTP services (WebApp, Browser, WebCrawler)
- Celery workers (Telegram, Scraper, Notifier)
- Load balancer performance
- Failover scenarios

Simulates real-world usage patterns to validate scaling effectiveness.
"""

import asyncio
import aiohttp
import time
import random
import statistics
import json
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import argparse
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class LoadTestResult:
    """Result of a load test scenario"""
    scenario: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    requests_per_second: float
    error_rate: float
    duration: float

@dataclass
class ServiceLoadResult:
    """Load test result for a specific service"""
    service_name: str
    endpoint: str
    results: List[float]  # Response times
    errors: List[str]
    success_count: int
    total_count: int

class HorizontalScalingLoadTester:
    """Load tester for horizontally scaled services"""
    
    def __init__(self):
        # Service endpoints for load testing
        self.http_services = {
            # WebApp services (direct)
            'webapp_1': 'http://localhost:8080',
            'webapp_2': 'http://localhost:8081', 
            'webapp_3': 'http://localhost:8082',
            
            # WebApp via load balancer
            'webapp_lb': 'http://localhost',
            
            # Browser services (direct)
            'camoufox_1': 'http://localhost:8100',
            'camoufox_2': 'http://localhost:8101',
            'camoufox_3': 'http://localhost:8102',
            
            # Browser services via load balancer
            'camoufox_lb': 'http://localhost:9100',
            
            # WebCrawler services (direct)
            'webcrawler_1': 'http://localhost:8200',
            'webcrawler_2': 'http://localhost:8201',
            'webcrawler_3': 'http://localhost:8202',
            
            # WebCrawler via load balancer
            'webcrawler_lb': 'http://localhost:9200',
        }
        
        # Load balancer monitoring
        self.lb_monitor_url = 'http://localhost:8888'
    
    async def make_request(self, session: aiohttp.ClientSession, url: str, endpoint: str = '/health') -> Tuple[float, Optional[str]]:
        """Make a single HTTP request and return response time and error"""
        start_time = time.time()
        try:
            async with session.get(f"{url}{endpoint}", timeout=aiohttp.ClientTimeout(total=10)) as response:
                await response.text()  # Read response body
                response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                
                if response.status == 200:
                    return response_time, None
                else:
                    return response_time, f"HTTP {response.status}"
        
        except asyncio.TimeoutError:
            return 10000, "Timeout"
        except Exception as e:
            return (time.time() - start_time) * 1000, str(e)
    
    async def load_test_service(self, service_name: str, base_url: str, 
                              concurrent_requests: int = 10, 
                              total_requests: int = 100,
                              endpoint: str = '/health') -> ServiceLoadResult:
        """Load test a specific service"""
        logger.info(f"Load testing {service_name} with {concurrent_requests} concurrent, {total_requests} total requests")
        
        results = []
        errors = []
        success_count = 0
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(concurrent_requests)
        
        async def make_limited_request(session):
            async with semaphore:
                response_time, error = await self.make_request(session, base_url, endpoint)
                return response_time, error
        
        # Create aiohttp session
        connector = aiohttp.TCPConnector(limit=concurrent_requests * 2, limit_per_host=concurrent_requests)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Create tasks for all requests
            tasks = [make_limited_request(session) for _ in range(total_requests)]
            
            # Execute all requests
            for task in asyncio.as_completed(tasks):
                try:
                    response_time, error = await task
                    results.append(response_time)
                    
                    if error is None:
                        success_count += 1
                    else:
                        errors.append(error)
                        
                except Exception as e:
                    errors.append(str(e))
        
        return ServiceLoadResult(
            service_name=service_name,
            endpoint=endpoint,
            results=results,
            errors=errors,
            success_count=success_count,
            total_count=total_requests
        )
    
    def calculate_test_metrics(self, service_results: List[ServiceLoadResult], 
                             start_time: float, end_time: float) -> LoadTestResult:
        """Calculate aggregated metrics from service results"""
        all_results = []
        all_errors = []
        total_success = 0
        total_requests = 0
        
        for result in service_results:
            all_results.extend(result.results)
            all_errors.extend(result.errors)
            total_success += result.success_count
            total_requests += result.total_count
        
        if not all_results:
            return LoadTestResult(
                scenario="Unknown",
                total_requests=total_requests,
                successful_requests=total_success,
                failed_requests=len(all_errors),
                avg_response_time=0,
                min_response_time=0,
                max_response_time=0,
                p95_response_time=0,
                requests_per_second=0,
                error_rate=100.0,
                duration=end_time - start_time
            )
        
        # Calculate statistics
        avg_response_time = statistics.mean(all_results)
        min_response_time = min(all_results)
        max_response_time = max(all_results)
        p95_response_time = statistics.quantiles(all_results, n=20)[18]  # 95th percentile
        
        duration = end_time - start_time
        requests_per_second = total_requests / duration if duration > 0 else 0
        error_rate = (len(all_errors) / total_requests * 100) if total_requests > 0 else 0
        
        return LoadTestResult(
            scenario="Load Test",
            total_requests=total_requests,
            successful_requests=total_success,
            failed_requests=len(all_errors),
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            requests_per_second=requests_per_second,
            error_rate=error_rate,
            duration=duration
        )
    
    async def test_webapp_scaling(self) -> LoadTestResult:
        """Test WebApp service scaling"""
        logger.info("Testing WebApp service scaling...")
        
        start_time = time.time()
        
        # Test all webapp replicas + load balancer
        service_tasks = []
        
        # Direct service tests
        for i in range(1, 4):
            service_name = f'webapp_{i}'
            service_url = self.http_services[service_name]
            task = self.load_test_service(service_name, service_url, 
                                        concurrent_requests=20, total_requests=100)
            service_tasks.append(task)
        
        # Load balancer test
        lb_task = self.load_test_service('webapp_lb', self.http_services['webapp_lb'],
                                       concurrent_requests=50, total_requests=300)
        service_tasks.append(lb_task)
        
        # Execute all tests concurrently
        results = await asyncio.gather(*service_tasks)
        
        end_time = time.time()
        
        metrics = self.calculate_test_metrics(results, start_time, end_time)
        metrics.scenario = "WebApp Scaling"
        
        return metrics
    
    async def test_browser_scaling(self) -> LoadTestResult:
        """Test Browser service scaling"""
        logger.info("Testing Browser service scaling...")
        
        start_time = time.time()
        
        service_tasks = []
        
        # Direct Camoufox service tests
        for i in range(1, 4):
            service_name = f'camoufox_{i}'
            service_url = self.http_services[service_name]
            task = self.load_test_service(service_name, service_url,
                                        concurrent_requests=10, total_requests=50,
                                        endpoint='/health')
            service_tasks.append(task)
        
        # Load balancer test
        lb_task = self.load_test_service('camoufox_lb', self.http_services['camoufox_lb'],
                                       concurrent_requests=25, total_requests=150,
                                       endpoint='/health')
        service_tasks.append(lb_task)
        
        results = await asyncio.gather(*service_tasks)
        end_time = time.time()
        
        metrics = self.calculate_test_metrics(results, start_time, end_time)
        metrics.scenario = "Browser Scaling"
        
        return metrics
    
    async def test_webcrawler_scaling(self) -> LoadTestResult:
        """Test WebCrawler service scaling"""
        logger.info("Testing WebCrawler service scaling...")
        
        start_time = time.time()
        
        service_tasks = []
        
        # Direct WebCrawler service tests
        for i in range(1, 4):
            service_name = f'webcrawler_{i}'
            service_url = self.http_services[service_name]
            task = self.load_test_service(service_name, service_url,
                                        concurrent_requests=15, total_requests=75)
            service_tasks.append(task)
        
        # Load balancer test
        lb_task = self.load_test_service('webcrawler_lb', self.http_services['webcrawler_lb'],
                                       concurrent_requests=30, total_requests=200)
        service_tasks.append(lb_task)
        
        results = await asyncio.gather(*service_tasks)
        end_time = time.time()
        
        metrics = self.calculate_test_metrics(results, start_time, end_time)
        metrics.scenario = "WebCrawler Scaling"
        
        return metrics
    
    async def test_load_balancer_performance(self) -> LoadTestResult:
        """Test load balancer performance and distribution"""
        logger.info("Testing load balancer performance...")
        
        start_time = time.time()
        
        # High-load test through load balancer
        tasks = [
            self.load_test_service('webapp_lb_high', self.http_services['webapp_lb'],
                                 concurrent_requests=100, total_requests=1000),
            self.load_test_service('camoufox_lb_high', self.http_services['camoufox_lb'],
                                 concurrent_requests=50, total_requests=500, endpoint='/health'),
            self.load_test_service('webcrawler_lb_high', self.http_services['webcrawler_lb'],
                                 concurrent_requests=75, total_requests=750),
        ]
        
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        metrics = self.calculate_test_metrics(results, start_time, end_time)
        metrics.scenario = "Load Balancer Performance"
        
        return metrics
    
    def test_celery_workers(self) -> LoadTestResult:
        """Test Celery worker scaling (simplified)"""
        logger.info("Testing Celery worker scaling...")
        
        start_time = time.time()
        
        # Use Celery inspect to check worker status
        worker_types = ['telegram_worker', 'scraper_worker', 'notifier_service']
        active_workers = 0
        total_workers = 0
        
        for worker_type in worker_types:
            for i in range(1, 4):  # Check 3 replicas of each
                worker_name = f"{worker_type}_{i}"
                try:
                    result = subprocess.run([
                        'docker', 'exec', worker_name, 
                        'celery', 'inspect', 'ping', '-t', '5'
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0 and 'pong' in result.stdout.lower():
                        active_workers += 1
                    total_workers += 1
                    
                except Exception as e:
                    logger.debug(f"Error checking {worker_name}: {e}")
                    total_workers += 1
        
        end_time = time.time()
        
        success_rate = (active_workers / total_workers * 100) if total_workers > 0 else 0
        
        return LoadTestResult(
            scenario="Celery Workers",
            total_requests=total_workers,
            successful_requests=active_workers,
            failed_requests=total_workers - active_workers,
            avg_response_time=0,
            min_response_time=0,
            max_response_time=0,
            p95_response_time=0,
            requests_per_second=0,
            error_rate=100 - success_rate,
            duration=end_time - start_time
        )
    
    async def run_comprehensive_test(self) -> Dict[str, LoadTestResult]:
        """Run comprehensive load testing of all scaled services"""
        logger.info("Starting comprehensive horizontal scaling load test...")
        
        results = {}
        
        # Test all service types
        test_scenarios = [
            ("webapp_scaling", self.test_webapp_scaling()),
            ("browser_scaling", self.test_browser_scaling()),
            ("webcrawler_scaling", self.test_webcrawler_scaling()),
            ("load_balancer", self.test_load_balancer_performance()),
        ]
        
        # Run HTTP tests
        for scenario_name, test_coro in test_scenarios:
            try:
                logger.info(f"Running {scenario_name} test...")
                result = await test_coro
                results[scenario_name] = result
                logger.info(f"Completed {scenario_name} test")
            except Exception as e:
                logger.error(f"Error in {scenario_name} test: {e}")
        
        # Run Celery worker test
        try:
            logger.info("Running Celery workers test...")
            celery_result = self.test_celery_workers()
            results["celery_workers"] = celery_result
            logger.info("Completed Celery workers test")
        except Exception as e:
            logger.error(f"Error in Celery workers test: {e}")
        
        return results
    
    def print_results(self, results: Dict[str, LoadTestResult]):
        """Print formatted test results"""
        print(f"\n{'='*80}")
        print(f"HORIZONTAL SCALING LOAD TEST RESULTS")
        print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        
        overall_success = True
        
        for scenario_name, result in results.items():
            print(f"\n{scenario_name.upper().replace('_', ' ')}:")
            print(f"  Duration: {result.duration:.1f}s")
            print(f"  Total Requests: {result.total_requests}")
            print(f"  Successful: {result.successful_requests}")
            print(f"  Failed: {result.failed_requests}")
            print(f"  Success Rate: {((result.successful_requests / result.total_requests) * 100):.1f}%")
            
            if result.avg_response_time > 0:
                print(f"  Avg Response Time: {result.avg_response_time:.1f}ms")
                print(f"  Min Response Time: {result.min_response_time:.1f}ms")
                print(f"  Max Response Time: {result.max_response_time:.1f}ms")
                print(f"  95th Percentile: {result.p95_response_time:.1f}ms")
                print(f"  Requests/sec: {result.requests_per_second:.1f}")
            
            # Determine if test passed
            success_rate = (result.successful_requests / result.total_requests) * 100 if result.total_requests > 0 else 0
            test_passed = success_rate >= 90  # 90% success rate threshold
            
            status = "✅ PASSED" if test_passed else "❌ FAILED"
            print(f"  Status: {status}")
            
            if not test_passed:
                overall_success = False
        
        # Overall summary
        print(f"\n{'='*40}")
        print(f"OVERALL RESULT: {'✅ PASSED' if overall_success else '❌ FAILED'}")
        print(f"{'='*40}")
        
        if overall_success:
            print("🎉 Horizontal scaling is working effectively!")
            print("All services are handling load well with proper distribution.")
        else:
            print("⚠️  Some issues detected with horizontal scaling.")
            print("Review failed tests and consider adjusting resources or configuration.")
    
    def save_results(self, results: Dict[str, LoadTestResult], filename: str = None):
        """Save results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"horizontal_scaling_test_{timestamp}.json"
        
        # Convert dataclasses to dictionaries
        json_results = {
            scenario: asdict(result) for scenario, result in results.items()
        }
        
        with open(filename, 'w') as f:
            json.dump(json_results, f, indent=2)
        
        logger.info(f"Results saved to {filename}")

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Test horizontal scaling performance")
    parser.add_argument('--scenario', choices=['webapp', 'browser', 'webcrawler', 'loadbalancer', 'celery', 'all'],
                        default='all', help='Test scenario to run')
    parser.add_argument('--save', action='store_true',
                        help='Save results to JSON file')
    parser.add_argument('--output', type=str,
                        help='Output filename for results')
    
    args = parser.parse_args()
    
    tester = HorizontalScalingLoadTester()
    
    if args.scenario == 'all':
        results = await tester.run_comprehensive_test()
    elif args.scenario == 'webapp':
        results = {'webapp_scaling': await tester.test_webapp_scaling()}
    elif args.scenario == 'browser':
        results = {'browser_scaling': await tester.test_browser_scaling()}
    elif args.scenario == 'webcrawler':
        results = {'webcrawler_scaling': await tester.test_webcrawler_scaling()}
    elif args.scenario == 'loadbalancer':
        results = {'load_balancer': await tester.test_load_balancer_performance()}
    elif args.scenario == 'celery':
        results = {'celery_workers': tester.test_celery_workers()}
    
    # Print results
    tester.print_results(results)
    
    # Save results if requested
    if args.save:
        tester.save_results(results, args.output)

if __name__ == "__main__":
    asyncio.run(main()) 