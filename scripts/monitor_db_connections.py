#!/usr/bin/env python3
"""
Database Connection Pool Monitor

This script monitors the health and usage of our database connection pools
to ensure our scaling improvements are working correctly.
"""

import time
import psutil
import os
import sys
import signal
from datetime import datetime, timezone
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.db.session import engine
from common.db import database as db_module
from common.db.session import db_session
from sqlalchemy import text

class DatabaseConnectionMonitor:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print("\n🛑 Received interrupt signal. Shutting down gracefully...")
        self.running = False
    
    def get_sqlalchemy_pool_stats(self) -> Dict[str, Any]:
        """Get SQLAlchemy connection pool statistics"""
        pool = engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid(),
            "total_connections": pool.checkedout() + pool.checkedin(),
            "max_possible": pool.size() + (getattr(pool, '_max_overflow', 0) or 0)
        }
    
    def get_psycopg2_pool_stats(self) -> Dict[str, Any]:
        """Get psycopg2 connection pool statistics"""
        # Initialize pool if not already done
        if db_module.pool is None:
            db_module.initialize_pool()
        
        pool = db_module.pool
        if pool is None:
            return {"error": "Pool not initialized"}
        
        return {
            "min_connections": pool.minconn,
            "max_connections": pool.maxconn,
            "used_connections": len(pool._used) if hasattr(pool, '_used') else 0,
            "available_connections": len(pool._pool) if hasattr(pool, '_pool') else 0
        }
    
    def get_postgresql_stats(self) -> Dict[str, Any]:
        """Get PostgreSQL server statistics"""
        try:
            with db_session() as db:
                # Get active connections
                result = db.execute(text("""
                    SELECT 
                        count(*) as total_connections,
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections,
                        count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
                    FROM pg_stat_activity 
                    WHERE pid <> pg_backend_pid()
                """)).fetchone()
                
                # Get max connections setting
                max_conn_result = db.execute(text("SHOW max_connections")).fetchone()
                max_connections = int(max_conn_result[0])
                
                # Get database size
                db_size_result = db.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """)).fetchone()
                
                return {
                    "max_connections": max_connections,
                    "total_connections": result.total_connections,
                    "active_connections": result.active_connections,
                    "idle_connections": result.idle_connections,
                    "idle_in_transaction": result.idle_in_transaction,
                    "connection_usage_percent": (result.total_connections / max_connections) * 100,
                    "database_size": db_size_result[0]
                }
        except Exception as e:
            return {"error": str(e)}
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system resource statistics"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_gb": psutil.virtual_memory().available / (1024**3),
            "disk_usage_percent": psutil.disk_usage('/').percent
        }
    
    def print_stats(self):
        """Print formatted statistics"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*80}")
        print(f"📊 Database Connection Pool Monitor - {timestamp}")
        print(f"{'='*80}")
        
        # SQLAlchemy Pool Stats
        sqlalchemy_stats = self.get_sqlalchemy_pool_stats()
        print(f"\n🔗 SQLAlchemy Connection Pool:")
        print(f"   Pool Size: {sqlalchemy_stats['pool_size']}")
        print(f"   Checked Out: {sqlalchemy_stats['checked_out']}")
        print(f"   Checked In: {sqlalchemy_stats['checked_in']}")
        print(f"   Overflow: {sqlalchemy_stats['overflow']}")
        print(f"   Total Active: {sqlalchemy_stats['total_connections']}")
        print(f"   Max Possible: {sqlalchemy_stats['max_possible']}")
        
        usage_percent = (sqlalchemy_stats['total_connections'] / sqlalchemy_stats['max_possible']) * 100
        status = "🟢" if usage_percent < 70 else "🟡" if usage_percent < 90 else "🔴"
        print(f"   Usage: {usage_percent:.1f}% {status}")
        
        # psycopg2 Pool Stats
        psycopg2_stats = self.get_psycopg2_pool_stats()
        print(f"\n🔗 psycopg2 Connection Pool:")
        if "error" not in psycopg2_stats:
            print(f"   Min Connections: {psycopg2_stats['min_connections']}")
            print(f"   Max Connections: {psycopg2_stats['max_connections']}")
            print(f"   Used: {psycopg2_stats['used_connections']}")
            print(f"   Available: {psycopg2_stats['available_connections']}")
            
            usage_percent = (psycopg2_stats['used_connections'] / psycopg2_stats['max_connections']) * 100
            status = "🟢" if usage_percent < 70 else "🟡" if usage_percent < 90 else "🔴"
            print(f"   Usage: {usage_percent:.1f}% {status}")
        else:
            print(f"   Error: {psycopg2_stats['error']}")
        
        # PostgreSQL Stats
        pg_stats = self.get_postgresql_stats()
        print(f"\n🐘 PostgreSQL Server:")
        if "error" not in pg_stats:
            print(f"   Max Connections: {pg_stats['max_connections']}")
            print(f"   Total Connections: {pg_stats['total_connections']}")
            print(f"   Active: {pg_stats['active_connections']}")
            print(f"   Idle: {pg_stats['idle_connections']}")
            print(f"   Idle in Transaction: {pg_stats['idle_in_transaction']}")
            print(f"   Database Size: {pg_stats['database_size']}")
            
            usage_percent = pg_stats['connection_usage_percent']
            status = "🟢" if usage_percent < 70 else "🟡" if usage_percent < 90 else "🔴"
            print(f"   Connection Usage: {usage_percent:.1f}% {status}")
        else:
            print(f"   Error: {pg_stats['error']}")
        
        # System Stats
        system_stats = self.get_system_stats()
        print(f"\n💻 System Resources:")
        print(f"   CPU Usage: {system_stats['cpu_percent']:.1f}%")
        print(f"   Memory Usage: {system_stats['memory_percent']:.1f}%")
        print(f"   Memory Available: {system_stats['memory_available_gb']:.1f} GB")
        print(f"   Disk Usage: {system_stats['disk_usage_percent']:.1f}%")
    
    def run_continuous_monitoring(self, interval: int = 10):
        """Run continuous monitoring with specified interval"""
        print("🚀 Starting Database Connection Pool Monitor")
        print(f"⏱️  Monitoring interval: {interval} seconds")
        print("Press Ctrl+C to stop")
        
        while self.running:
            try:
                self.print_stats()
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
    
    parser = argparse.ArgumentParser(description="Monitor database connection pools")
    parser.add_argument("--interval", type=int, default=10, help="Monitoring interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    
    args = parser.parse_args()
    
    monitor = DatabaseConnectionMonitor()
    
    if args.once:
        monitor.print_stats()
    else:
        monitor.run_continuous_monitoring(args.interval)

if __name__ == "__main__":
    main() 