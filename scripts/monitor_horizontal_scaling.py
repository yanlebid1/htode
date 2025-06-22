#!/usr/bin/env python3
"""
Horizontal Service Scaling Monitor

Monitors all scaled service replicas including:
- Telegram services (3 main + 3 workers)
- Scraper workers (3 replicas)
- Notifier services (3 replicas)
- WebApp services (3 replicas)
- WebCrawler services (3 replicas)
- Browser services (3 Camoufox)
- Load balancer (nginx)

Provides real-time metrics and health status for all replicas.
"""

import time
import requests
import subprocess
import json
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ServiceStatus:
    """Status information for a service replica"""
    name: str
    replica: int
    is_healthy: bool
    response_time: Optional[float]
    error_message: Optional[str]
    cpu_usage: Optional[float]
    memory_usage: Optional[float]
    
@dataclass
class ServiceMetrics:
    """Aggregated metrics for a service type"""
    service_type: str
    total_replicas: int
    healthy_replicas: int
    avg_response_time: Optional[float]
    total_cpu: Optional[float]
    total_memory: Optional[float]

class HorizontalScalingMonitor:
    """Monitor for horizontally scaled services"""
    
    def __init__(self):
        self.running = True
        
        # Service definitions
        self.services = {
            'telegram_services': [
                {'name': 'telegram_service_1', 'replica': 1, 'type': 'celery_worker', 'health_check': None},
                {'name': 'telegram_service_2', 'replica': 2, 'type': 'celery_worker', 'health_check': None},
                {'name': 'telegram_service_3', 'replica': 3, 'type': 'celery_worker', 'health_check': None},
            ],
            'telegram_workers': [
                {'name': 'telegram_worker_1', 'replica': 1, 'type': 'celery_worker', 'health_check': None},
                {'name': 'telegram_worker_2', 'replica': 2, 'type': 'celery_worker', 'health_check': None},
                {'name': 'telegram_worker_3', 'replica': 3, 'type': 'celery_worker', 'health_check': None},
            ],
            'scraper_workers': [
                {'name': 'scraper_worker_1', 'replica': 1, 'type': 'celery_worker', 'health_check': None},
                {'name': 'scraper_worker_2', 'replica': 2, 'type': 'celery_worker', 'health_check': None},
                {'name': 'scraper_worker_3', 'replica': 3, 'type': 'celery_worker', 'health_check': None},
            ],
            'notifier_services': [
                {'name': 'notifier_service_1', 'replica': 1, 'type': 'celery_worker', 'health_check': None},
                {'name': 'notifier_service_2', 'replica': 2, 'type': 'celery_worker', 'health_check': None},
                {'name': 'notifier_service_3', 'replica': 3, 'type': 'celery_worker', 'health_check': None},
            ],
            'webapp_services': [
                {'name': 'mini_webapp_1', 'replica': 1, 'type': 'http', 'health_check': 'http://localhost:8080/health'},
                {'name': 'mini_webapp_2', 'replica': 2, 'type': 'http', 'health_check': 'http://localhost:8081/health'},
                {'name': 'mini_webapp_3', 'replica': 3, 'type': 'http', 'health_check': 'http://localhost:8082/health'},
            ],
            'webcrawler_services': [
                {'name': 'webcrawler_service_1', 'replica': 1, 'type': 'http', 'health_check': 'http://localhost:8200/health'},
                {'name': 'webcrawler_service_2', 'replica': 2, 'type': 'http', 'health_check': 'http://localhost:8201/health'},
                {'name': 'webcrawler_service_3', 'replica': 3, 'type': 'http', 'health_check': 'http://localhost:8202/health'},
            ],
            'camoufox_services': [
                {'name': 'camoufox_service_1', 'replica': 1, 'type': 'http', 'health_check': 'http://localhost:8100/health'},
                {'name': 'camoufox_service_2', 'replica': 2, 'type': 'http', 'health_check': 'http://localhost:8101/health'},
                {'name': 'camoufox_service_3', 'replica': 3, 'type': 'http', 'health_check': 'http://localhost:8102/health'},
            ],
            'load_balancer': [
                {'name': 'nginx_loadbalancer', 'replica': 1, 'type': 'http', 'health_check': 'http://localhost/nginx-health'},
            ]
        }
        
        # Load balancer backend checks
        self.load_balancer_backends = {
            'webapp_backend': 'http://localhost/health',
            'camoufox_backend': 'http://localhost:9100/health',
            'webcrawler_backend': 'http://localhost:9200/health',
        }
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal. Stopping monitor...")
        self.running = False
        sys.exit(0)
    
    def check_docker_container_stats(self, container_name: str) -> Tuple[Optional[float], Optional[float]]:
        """Get CPU and memory usage for a Docker container"""
        try:
            # Get container stats
            result = subprocess.run([
                'docker', 'stats', container_name, 
                '--no-stream', '--format', 
                'table {{.CPUPerc}}\t{{.MemUsage}}'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:  # Header + data
                    stats_line = lines[1].split('\t')
                    if len(stats_line) >= 2:
                        # Parse CPU percentage
                        cpu_str = stats_line[0].replace('%', '')
                        cpu_usage = float(cpu_str) if cpu_str else None
                        
                        # Parse memory usage (format: "used / limit")
                        mem_parts = stats_line[1].split(' / ')
                        if len(mem_parts) >= 1:
                            mem_used = mem_parts[0].strip()
                            # Convert to MB if needed
                            if 'GiB' in mem_used:
                                memory_usage = float(mem_used.replace('GiB', '')) * 1024
                            elif 'MiB' in mem_used:
                                memory_usage = float(mem_used.replace('MiB', ''))
                            else:
                                memory_usage = None
                        else:
                            memory_usage = None
                        
                        return cpu_usage, memory_usage
        except Exception as e:
            logger.debug(f"Error getting stats for {container_name}: {e}")
        
        return None, None
    
    def check_http_service(self, service_config: dict) -> ServiceStatus:
        """Check health status of an HTTP service"""
        name = service_config['name']
        replica = service_config['replica']
        health_url = service_config['health_check']
        
        start_time = time.time()
        
        try:
            response = requests.get(health_url, timeout=5)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            is_healthy = response.status_code == 200
            error_message = None if is_healthy else f"HTTP {response.status_code}"
            
        except requests.exceptions.Timeout:
            response_time = 5000  # Timeout time
            is_healthy = False
            error_message = "Timeout"
        except requests.exceptions.ConnectionError:
            response_time = None
            is_healthy = False
            error_message = "Connection failed"
        except Exception as e:
            response_time = None
            is_healthy = False
            error_message = str(e)
        
        # Get container stats
        cpu_usage, memory_usage = self.check_docker_container_stats(name)
        
        return ServiceStatus(
            name=name,
            replica=replica,
            is_healthy=is_healthy,
            response_time=response_time,
            error_message=error_message,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage
        )
    
    def check_celery_worker(self, service_config: dict) -> ServiceStatus:
        """Check health status of a Celery worker"""
        name = service_config['name']
        replica = service_config['replica']
        
        try:
            # Use docker exec to check celery worker status
            result = subprocess.run([
                'docker', 'exec', name, 
                'celery', 'inspect', 'ping'
            ], capture_output=True, text=True, timeout=10)
            
            is_healthy = result.returncode == 0 and 'pong' in result.stdout.lower()
            error_message = None if is_healthy else "Worker not responding"
            
        except subprocess.TimeoutExpired:
            is_healthy = False
            error_message = "Health check timeout"
        except Exception as e:
            is_healthy = False
            error_message = str(e)
        
        # Get container stats
        cpu_usage, memory_usage = self.check_docker_container_stats(name)
        
        return ServiceStatus(
            name=name,
            replica=replica,
            is_healthy=is_healthy,
            response_time=None,
            error_message=error_message,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage
        )
    
    def check_service(self, service_config: dict) -> ServiceStatus:
        """Check health status of a service based on its type"""
        service_type = service_config['type']
        
        if service_type == 'http':
            return self.check_http_service(service_config)
        elif service_type == 'celery_worker':
            return self.check_celery_worker(service_config)
        else:
            # Unknown service type
            return ServiceStatus(
                name=service_config['name'],
                replica=service_config['replica'],
                is_healthy=False,
                response_time=None,
                error_message="Unknown service type",
                cpu_usage=None,
                memory_usage=None
            )
    
    def check_load_balancer_backends(self) -> Dict[str, bool]:
        """Check the health of load balancer backends"""
        backend_status = {}
        
        for backend_name, health_url in self.load_balancer_backends.items():
            try:
                response = requests.get(health_url, timeout=5)
                backend_status[backend_name] = response.status_code == 200
            except Exception:
                backend_status[backend_name] = False
        
        return backend_status
    
    def get_nginx_stats(self) -> Dict[str, any]:
        """Get nginx statistics if available"""
        try:
            response = requests.get('http://localhost:8888/nginx_status', timeout=5)
            if response.status_code == 200:
                # Parse nginx status
                lines = response.text.strip().split('\n')
                stats = {}
                for line in lines:
                    if 'Active connections:' in line:
                        stats['active_connections'] = int(line.split(':')[1].strip())
                    elif line.strip() and ' ' in line and line.strip().split()[0].isdigit():
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            stats['accepts'] = int(parts[0])
                            stats['handled'] = int(parts[1])
                            stats['requests'] = int(parts[2])
                return stats
        except Exception as e:
            logger.debug(f"Error getting nginx stats: {e}")
        
        return {}
    
    def calculate_service_metrics(self, service_statuses: List[ServiceStatus]) -> ServiceMetrics:
        """Calculate aggregated metrics for service statuses"""
        if not service_statuses:
            return ServiceMetrics("unknown", 0, 0, None, None, None)
        
        total_replicas = len(service_statuses)
        healthy_replicas = sum(1 for status in service_statuses if status.is_healthy)
        
        # Calculate average response time (for HTTP services)
        response_times = [s.response_time for s in service_statuses if s.response_time is not None]
        avg_response_time = sum(response_times) / len(response_times) if response_times else None
        
        # Calculate total CPU and memory
        cpu_usages = [s.cpu_usage for s in service_statuses if s.cpu_usage is not None]
        memory_usages = [s.memory_usage for s in service_statuses if s.memory_usage is not None]
        
        total_cpu = sum(cpu_usages) if cpu_usages else None
        total_memory = sum(memory_usages) if memory_usages else None
        
        return ServiceMetrics(
            service_type=service_statuses[0].name.split('_')[0],
            total_replicas=total_replicas,
            healthy_replicas=healthy_replicas,
            avg_response_time=avg_response_time,
            total_cpu=total_cpu,
            total_memory=total_memory
        )
    
    def monitor_cycle(self):
        """Perform one monitoring cycle"""
        print(f"\n{'='*80}")
        print(f"HORIZONTAL SCALING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        
        all_service_statuses = {}
        
        # Check all services in parallel
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_service = {}
            
            for service_type, service_configs in self.services.items():
                for service_config in service_configs:
                    future = executor.submit(self.check_service, service_config)
                    future_to_service[future] = (service_type, service_config)
            
            # Collect results
            for future in as_completed(future_to_service):
                service_type, service_config = future_to_service[future]
                try:
                    status = future.result()
                    if service_type not in all_service_statuses:
                        all_service_statuses[service_type] = []
                    all_service_statuses[service_type].append(status)
                except Exception as e:
                    logger.error(f"Error checking {service_config['name']}: {e}")
        
        # Display results by service type
        total_healthy = 0
        total_services = 0
        
        for service_type, statuses in all_service_statuses.items():
            metrics = self.calculate_service_metrics(statuses)
            total_healthy += metrics.healthy_replicas
            total_services += metrics.total_replicas
            
            print(f"\n{service_type.upper().replace('_', ' ')}:")
            print(f"  Health: {metrics.healthy_replicas}/{metrics.total_replicas} replicas healthy")
            
            if metrics.avg_response_time is not None:
                print(f"  Avg Response Time: {metrics.avg_response_time:.1f}ms")
            
            if metrics.total_cpu is not None:
                print(f"  Total CPU Usage: {metrics.total_cpu:.1f}%")
            
            if metrics.total_memory is not None:
                print(f"  Total Memory Usage: {metrics.total_memory:.1f}MB")
            
            # Show individual replica status
            for status in statuses:
                health_indicator = "✅" if status.is_healthy else "❌"
                line = f"    {health_indicator} {status.name} (replica {status.replica})"
                
                if status.response_time is not None:
                    line += f" - {status.response_time:.1f}ms"
                
                if status.cpu_usage is not None and status.memory_usage is not None:
                    line += f" - CPU: {status.cpu_usage:.1f}%, RAM: {status.memory_usage:.1f}MB"
                
                if status.error_message:
                    line += f" - ERROR: {status.error_message}"
                
                print(line)
        
        # Load balancer status
        print(f"\nLOAD BALANCER:")
        backend_status = self.check_load_balancer_backends()
        nginx_stats = self.get_nginx_stats()
        
        lb_healthy = all(status for status in backend_status.values())
        lb_indicator = "✅" if lb_healthy else "❌"
        print(f"  {lb_indicator} Nginx Load Balancer")
        
        for backend, is_healthy in backend_status.items():
            indicator = "✅" if is_healthy else "❌"
            print(f"    {indicator} {backend}")
        
        if nginx_stats:
            print(f"  Active Connections: {nginx_stats.get('active_connections', 'N/A')}")
            print(f"  Total Requests: {nginx_stats.get('requests', 'N/A')}")
        
        # Summary
        print(f"\nSUMMARY:")
        overall_health = (total_healthy / total_services * 100) if total_services > 0 else 0
        health_indicator = "✅" if overall_health >= 80 else "⚠️" if overall_health >= 60 else "❌"
        print(f"  {health_indicator} Overall System Health: {overall_health:.1f}% ({total_healthy}/{total_services} services healthy)")
        
        # Performance recommendations
        if overall_health < 100:
            print(f"\nRECOMMENDATIONS:")
            for service_type, statuses in all_service_statuses.items():
                unhealthy_count = sum(1 for s in statuses if not s.is_healthy)
                if unhealthy_count > 0:
                    print(f"  • Check {unhealthy_count} unhealthy {service_type.replace('_', ' ')} replica(s)")
        
        return overall_health >= 80
    
    def run(self, interval: int = 30):
        """Run the monitoring loop"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("Starting Horizontal Scaling Monitor...")
        logger.info(f"Monitoring interval: {interval} seconds")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while self.running:
                try:
                    self.monitor_cycle()
                    time.sleep(interval)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Error in monitoring cycle: {e}")
                    time.sleep(5)  # Short delay before retrying
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Monitoring stopped")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor horizontally scaled services")
    parser.add_argument('--interval', '-i', type=int, default=30,
                        help='Monitoring interval in seconds (default: 30)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit (no continuous monitoring)')
    
    args = parser.parse_args()
    
    monitor = HorizontalScalingMonitor()
    
    if args.once:
        monitor.monitor_cycle()
    else:
        monitor.run(args.interval)

if __name__ == "__main__":
    main() 