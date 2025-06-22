#!/usr/bin/env python3
"""
Browser Pool Monitoring Script
Monitors browser pool performance across multiple Camoufox service instances.
"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class BrowserPoolMonitor:
    """Monitor browser pool performance across multiple services"""
    
    def __init__(self):
        self.camoufox_services = [
            {"name": "camoufox_service_1", "url": "http://localhost:8100"},
            {"name": "camoufox_service_2", "url": "http://localhost:8101"},
            {"name": "camoufox_service_3", "url": "http://localhost:8102"},
        ]
        self.session = None
        self.monitoring = False
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_service_stats(self, service: Dict) -> Optional[Dict]:
        """Get statistics from a single Camoufox service"""
        try:
            async with self.session.get(f"{service['url']}/stats") as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "name": service["name"],
                        "status": "healthy",
                        "stats": data.get("browser_pool", {}),
                        "timestamp": data.get("timestamp"),
                        "response_time": response.headers.get("X-Response-Time", "N/A")
                    }
                else:
                    return {
                        "name": service["name"],
                        "status": "unhealthy", 
                        "error": f"HTTP {response.status}",
                        "stats": {}
                    }
        except Exception as e:
            return {
                "name": service["name"],
                "status": "error",
                "error": str(e),
                "stats": {}
            }
    
    async def get_all_stats(self) -> List[Dict]:
        """Get statistics from all Camoufox services"""
        tasks = [self.get_service_stats(service) for service in self.camoufox_services]
        return await asyncio.gather(*tasks)
    
    def calculate_totals(self, all_stats: List[Dict]) -> Dict:
        """Calculate total statistics across all services"""
        totals = {
            "total_pool_size": 0,
            "total_available_browsers": 0,
            "total_active_sessions": 0,
            "total_requests": 0,
            "total_failed_requests": 0,
            "healthy_services": 0,
            "unhealthy_services": 0,
            "average_success_rate": 0,
        }
        
        success_rates = []
        
        for service_stats in all_stats:
            if service_stats["status"] == "healthy":
                totals["healthy_services"] += 1
                stats = service_stats["stats"]
                
                totals["total_pool_size"] += stats.get("pool_size", 0)
                totals["total_available_browsers"] += stats.get("available_browsers", 0)
                totals["total_active_sessions"] += stats.get("active_sessions", 0)
                totals["total_requests"] += stats.get("total_requests", 0)
                totals["total_failed_requests"] += stats.get("failed_requests", 0)
                
                success_rate = stats.get("success_rate", 0)
                if success_rate > 0:
                    success_rates.append(success_rate)
            else:
                totals["unhealthy_services"] += 1
        
        if success_rates:
            totals["average_success_rate"] = sum(success_rates) / len(success_rates)
        
        # Calculate utilization
        if totals["total_pool_size"] > 0:
            totals["utilization_rate"] = (totals["total_active_sessions"] / totals["total_pool_size"]) * 100
        else:
            totals["utilization_rate"] = 0
            
        return totals
    
    def print_stats(self, all_stats: List[Dict], totals: Dict):
        """Print formatted statistics"""
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("=" * 80)
        print(f"🚀 BROWSER POOL SCALING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Overall summary
        print(f"\n📊 OVERALL PERFORMANCE:")
        print(f"   Total Browser Pool Size: {totals['total_pool_size']}")
        print(f"   Available Browsers: {totals['total_available_browsers']}")
        print(f"   Active Sessions: {totals['total_active_sessions']}")
        print(f"   Pool Utilization: {totals['utilization_rate']:.1f}%")
        print(f"   Success Rate: {totals['average_success_rate']:.1f}%")
        print(f"   Total Requests: {totals['total_requests']}")
        print(f"   Failed Requests: {totals['total_failed_requests']}")
        
        # Service health
        print(f"\n🏥 SERVICE HEALTH:")
        print(f"   Healthy Services: {totals['healthy_services']}/3")
        print(f"   Unhealthy Services: {totals['unhealthy_services']}/3")
        
        # Individual service details
        print(f"\n🔍 SERVICE DETAILS:")
        print("-" * 80)
        
        for service_stats in all_stats:
            name = service_stats["name"]
            status = service_stats["status"]
            
            if status == "healthy":
                stats = service_stats["stats"]
                pool_size = stats.get("pool_size", 0)
                available = stats.get("available_browsers", 0)
                active = stats.get("active_sessions", 0)
                total_reqs = stats.get("total_requests", 0)
                failed_reqs = stats.get("failed_requests", 0)
                success_rate = stats.get("success_rate", 0)
                
                utilization = (active / pool_size * 100) if pool_size > 0 else 0
                
                print(f"✅ {name}:")
                print(f"   Pool Size: {pool_size} | Available: {available} | Active: {active}")
                print(f"   Utilization: {utilization:.1f}% | Success Rate: {success_rate:.1f}%")
                print(f"   Requests: {total_reqs} | Failed: {failed_reqs}")
                
            else:
                error = service_stats.get("error", "Unknown error")
                print(f"❌ {name}: {status.upper()} - {error}")
            
            print("")
        
        # Performance thresholds and warnings
        print(f"⚠️  PERFORMANCE ALERTS:")
        alerts = []
        
        if totals['utilization_rate'] > 80:
            alerts.append("🔥 HIGH UTILIZATION: Pool usage > 80%")
        if totals['average_success_rate'] < 95 and totals['total_requests'] > 10:
            alerts.append("⚠️  LOW SUCCESS RATE: < 95%")
        if totals['unhealthy_services'] > 0:
            alerts.append(f"🚫 SERVICE DOWN: {totals['unhealthy_services']} service(s) unhealthy")
        if totals['total_available_browsers'] < 10:
            alerts.append("⚡ LOW AVAILABILITY: < 10 browsers available")
        
        if alerts:
            for alert in alerts:
                print(f"   {alert}")
        else:
            print("   🟢 All systems operating normally")
        
        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop monitoring")
    
    async def monitor_continuous(self, interval: int = 5):
        """Continuously monitor browser pools"""
        self.monitoring = True
        print("Starting browser pool monitoring...")
        
        try:
            while self.monitoring:
                all_stats = await self.get_all_stats()
                totals = self.calculate_totals(all_stats)
                self.print_stats(all_stats, totals)
                
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
        except Exception as e:
            print(f"\nMonitoring error: {e}")
        finally:
            self.monitoring = False
    
    async def get_snapshot(self) -> Dict:
        """Get a single snapshot of browser pool statistics"""
        all_stats = await self.get_all_stats()
        totals = self.calculate_totals(all_stats)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "services": all_stats,
            "totals": totals
        }


async def main():
    """Main monitoring function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor browser pool performance")
    parser.add_argument("--interval", "-i", type=int, default=5, 
                       help="Monitoring interval in seconds (default: 5)")
    parser.add_argument("--snapshot", "-s", action="store_true",
                       help="Take a single snapshot instead of continuous monitoring")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output in JSON format")
    
    args = parser.parse_args()
    
    async with BrowserPoolMonitor() as monitor:
        if args.snapshot:
            snapshot = await monitor.get_snapshot()
            if args.json:
                print(json.dumps(snapshot, indent=2))
            else:
                monitor.print_stats(snapshot["services"], snapshot["totals"])
        else:
            await monitor.monitor_continuous(args.interval)


if __name__ == "__main__":
    asyncio.run(main()) 