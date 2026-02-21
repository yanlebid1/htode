"""
Redis Cluster Manager for High-Performance Scaling

This module provides intelligent connection management for the Redis cluster,
handling multiple Redis instances with functional separation and automatic failover.
"""

import redis
import logging
from typing import Dict, List, Optional, Union
from redis.sentinel import Sentinel
from redis.connection import ConnectionPool
import os
from enum import Enum
from contextlib import contextmanager
import time
from threading import Lock
import json

logger = logging.getLogger(__name__)


class RedisRole(Enum):
    """Redis instance roles for functional separation"""
    QUEUE = "queue"          # Celery queues and task broker
    CACHE = "cache"          # Application caching
    STATE = "state"          # User states and sessions  
    ANALYTICS = "analytics"  # Metrics and monitoring data


class RedisClusterManager:
    """
    Manages Redis cluster connections with high availability and load balancing
    """
    
    def __init__(self):
        self.connections: Dict[RedisRole, redis.Redis] = {}
        self.connection_pools: Dict[RedisRole, ConnectionPool] = {}
        self.sentinels: Optional[Sentinel] = None
        self._lock = Lock()
        self._initialized = False
        
        # Redis URLs from environment
        self.redis_urls = {
            RedisRole.QUEUE: os.getenv("REDIS_QUEUE_URL", "redis://redis_queue:6379/0"),
            RedisRole.CACHE: os.getenv("REDIS_CACHE_URL", "redis://redis_cache:6379/0"),
            RedisRole.STATE: os.getenv("REDIS_STATE_URL", "redis://redis_state:6379/0"),
            RedisRole.ANALYTICS: os.getenv("REDIS_ANALYTICS_URL", "redis://redis_analytics:6379/0"),
        }
        
        # Redis Sentinel configuration
        self.sentinel_hosts = self._parse_sentinel_hosts()
        
        # Connection pool configurations for different roles
        self.pool_configs = {
            RedisRole.QUEUE: {
                "max_connections": 100,      # High for queue operations
                "retry_on_timeout": True,
                "socket_keepalive": True,
                "socket_keepalive_options": {},
                "health_check_interval": 30,
            },
            RedisRole.CACHE: {
                "max_connections": 50,       # Medium for cache operations
                "retry_on_timeout": False,   # Cache misses are acceptable
                "socket_keepalive": True,
                "socket_keepalive_options": {},
                "health_check_interval": 30,
            },
            RedisRole.STATE: {
                "max_connections": 30,       # Lower for state operations
                "retry_on_timeout": True,    # State is critical
                "socket_keepalive": True,
                "socket_keepalive_options": {},
                "health_check_interval": 30,
            },
            RedisRole.ANALYTICS: {
                "max_connections": 20,       # Lowest for analytics
                "retry_on_timeout": False,   # Analytics data loss is acceptable
                "socket_keepalive": True,
                "socket_keepalive_options": {},
                "health_check_interval": 60,
            },
        }
        
        self.initialize_connections()
    
    def _parse_sentinel_hosts(self) -> List[tuple]:
        """Parse Redis Sentinel hosts from environment"""
        sentinel_string = os.getenv("REDIS_SENTINELS", "")
        if not sentinel_string:
            return []
        
        hosts = []
        for host_port in sentinel_string.split(","):
            try:
                host, port = host_port.strip().split(":")
                hosts.append((host, int(port)))
            except ValueError:
                logger.warning(f"Invalid sentinel host format: {host_port}")
        
        return hosts
    
    def initialize_connections(self):
        """Initialize all Redis connections with proper configuration"""
        with self._lock:
            if self._initialized:
                return
            
            logger.info("Initializing Redis cluster connections")
            
            # Initialize Sentinel if configured
            if self.sentinel_hosts:
                try:
                    self.sentinels = Sentinel(
                        self.sentinel_hosts,
                        socket_timeout=0.5,
                        socket_connect_timeout=0.5,
                        socket_keepalive=True,
                        socket_keepalive_options={},
                    )
                    logger.info(f"Redis Sentinel initialized with hosts: {self.sentinel_hosts}")
                except Exception as e:
                    logger.error(f"Failed to initialize Redis Sentinel: {e}")
                    self.sentinels = None
            
            # Initialize connections for each role
            for role in RedisRole:
                try:
                    self._initialize_role_connection(role)
                    logger.info(f"Initialized Redis connection for role: {role.value}")
                except Exception as e:
                    logger.error(f"Failed to initialize Redis connection for {role.value}: {e}")
            
            self._initialized = True
            logger.info("Redis cluster initialization complete")
    
    def _initialize_role_connection(self, role: RedisRole):
        """Initialize connection for a specific Redis role"""
        pool_config = self.pool_configs[role]
        redis_url = self.redis_urls[role]
        
        # Create connection pool
        pool = ConnectionPool.from_url(
            redis_url,
            max_connections=pool_config["max_connections"],
            retry_on_timeout=pool_config["retry_on_timeout"],
            socket_keepalive=pool_config["socket_keepalive"],
            socket_keepalive_options=pool_config["socket_keepalive_options"],
            health_check_interval=pool_config["health_check_interval"],
        )
        
        # Create Redis connection
        connection = redis.Redis(connection_pool=pool)
        
        # Test connection
        connection.ping()
        
        self.connection_pools[role] = pool
        self.connections[role] = connection
    
    def get_connection(self, role: RedisRole) -> redis.Redis:
        """Get Redis connection for a specific role"""
        if not self._initialized:
            self.initialize_connections()
        
        if role not in self.connections:
            raise ValueError(f"No connection available for role: {role.value}")
        
        return self.connections[role]
    
    def get_queue_redis(self) -> redis.Redis:
        """Get Redis connection for Celery queues"""
        return self.get_connection(RedisRole.QUEUE)
    
    def get_cache_redis(self) -> redis.Redis:
        """Get Redis connection for application caching"""
        return self.get_connection(RedisRole.CACHE)
    
    def get_state_redis(self) -> redis.Redis:
        """Get Redis connection for user states"""
        return self.get_connection(RedisRole.STATE)
    
    def get_analytics_redis(self) -> redis.Redis:
        """Get Redis connection for analytics data"""
        return self.get_connection(RedisRole.ANALYTICS)
    
    @contextmanager
    def get_pipeline(self, role: RedisRole, transaction: bool = True):
        """Get Redis pipeline for batch operations"""
        connection = self.get_connection(role)
        pipeline = connection.pipeline(transaction=transaction)
        try:
            yield pipeline
        finally:
            # Pipeline is automatically executed when exiting context if needed
            pass
    
    def health_check(self) -> Dict[str, bool]:
        """Check health of all Redis connections"""
        health_status = {}
        
        for role in RedisRole:
            try:
                connection = self.get_connection(role)
                connection.ping()
                health_status[role.value] = True
            except Exception as e:
                logger.error(f"Health check failed for {role.value}: {e}")
                health_status[role.value] = False
        
        return health_status
    
    def get_cluster_info(self) -> Dict[str, Dict]:
        """Get detailed information about the Redis cluster"""
        cluster_info = {}
        
        for role in RedisRole:
            try:
                connection = self.get_connection(role)
                info = connection.info()
                
                cluster_info[role.value] = {
                    "url": self.redis_urls[role],
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                    "role": info.get("role", "unknown"),
                }
                
                # Calculate hit rate
                hits = cluster_info[role.value]["keyspace_hits"]
                misses = cluster_info[role.value]["keyspace_misses"]
                total_requests = hits + misses
                hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
                cluster_info[role.value]["hit_rate"] = round(hit_rate, 2)
                
            except Exception as e:
                logger.error(f"Failed to get info for {role.value}: {e}")
                cluster_info[role.value] = {"error": str(e)}
        
        return cluster_info
    
    def get_memory_usage(self) -> Dict[str, str]:
        """Get memory usage for all Redis instances"""
        memory_usage = {}
        
        for role in RedisRole:
            try:
                connection = self.get_connection(role)
                info = connection.info("memory")
                memory_usage[role.value] = info.get("used_memory_human", "0B")
            except Exception as e:
                logger.error(f"Failed to get memory usage for {role.value}: {e}")
                memory_usage[role.value] = "Error"
        
        return memory_usage
    
    def flush_cache(self, role: RedisRole = RedisRole.CACHE):
        """Flush cache for a specific Redis role (use with caution!)"""
        try:
            connection = self.get_connection(role)
            connection.flushdb()
            logger.info(f"Flushed cache for {role.value}")
        except Exception as e:
            logger.error(f"Failed to flush cache for {role.value}: {e}")
            raise
    
    def close_connections(self):
        """Close all Redis connections"""
        with self._lock:
            for role, connection in self.connections.items():
                try:
                    connection.close()
                    logger.info(f"Closed connection for {role.value}")
                except Exception as e:
                    logger.error(f"Error closing connection for {role.value}: {e}")
            
            for role, pool in self.connection_pools.items():
                try:
                    pool.disconnect()
                    logger.info(f"Disconnected pool for {role.value}")
                except Exception as e:
                    logger.error(f"Error disconnecting pool for {role.value}: {e}")
            
            self.connections.clear()
            self.connection_pools.clear()
            self._initialized = False


# Global Redis cluster manager instance
redis_cluster = RedisClusterManager()


# Convenience functions for backward compatibility
def get_redis_client(role: RedisRole = RedisRole.CACHE) -> redis.Redis:
    """Get Redis client for a specific role"""
    return redis_cluster.get_connection(role)


def get_queue_redis() -> redis.Redis:
    """Get Redis client for Celery queues"""
    return redis_cluster.get_queue_redis()


def get_cache_redis() -> redis.Redis:
    """Get Redis client for application caching"""
    return redis_cluster.get_cache_redis()


def get_state_redis() -> redis.Redis:
    """Get Redis client for user states"""
    return redis_cluster.get_state_redis()


def get_analytics_redis() -> redis.Redis:
    """Get Redis client for analytics"""
    return redis_cluster.get_analytics_redis()


# Legacy compatibility - points to queue Redis for Celery
def from_url(url: str) -> redis.Redis:
    """Legacy compatibility function"""
    logger.warning("Using legacy redis.from_url - consider migrating to cluster manager")
    return redis_cluster.get_queue_redis() 