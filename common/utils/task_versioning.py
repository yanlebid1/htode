"""
Task versioning utilities for zero-downtime deployments.

This module provides decorators and utilities to version Celery tasks,
allowing old and new versions to coexist during deployments.
"""

import functools
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timedelta
from common.celery_app import celery_app
from common.utils import logger


class TaskVersionManager:
    """Manages task versions and routing during deployments"""

    def __init__(self):
        self.versions = {}
        self.rollout_config = {}

    def register_version(self, task_name: str, version: str, handler: Callable):
        """Register a task version"""
        if task_name not in self.versions:
            self.versions[task_name] = {}
        self.versions[task_name][version] = handler

    def set_rollout(self, task_name: str, config: Dict[str, Any]):
        """Set rollout configuration for a task"""
        self.rollout_config[task_name] = config

    def get_handler(self, task_name: str, version: Optional[str] = None) -> Callable:
        """Get the appropriate handler based on version and rollout config"""
        if version:
            return self.versions[task_name].get(version)

        # Check rollout configuration
        config = self.rollout_config.get(task_name, {})
        if config.get("canary_enabled"):
            import random

            percentage = config.get("canary_percentage", 10)
            if random.randint(1, 100) <= percentage:
                return self.versions[task_name].get(config.get("canary_version"))

        # Return default version
        default_version = config.get("default_version", "v1")
        return self.versions[task_name].get(default_version)


# Global version manager
version_manager = TaskVersionManager()


def versioned_task(name: str, version: str = "v1"):
    """
    Decorator for creating versioned tasks.

    Usage:
        @versioned_task('process_ad', version='v2')
        def process_ad_v2(ad_data):
            # New implementation
            pass
    """

    def decorator(func):
        # Create versioned task name
        versioned_name = f"{name}.{version}"

        # Register with Celery
        task = celery_app.task(name=versioned_name)(func)

        # Register with version manager
        version_manager.register_version(name, version, task)

        # Create a compatibility wrapper
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Log version usage
            logger.info("Executing task", extra={"task_name": name, "version": version})
            return func(*args, **kwargs)

        return task

    return decorator


def forward_compatible_task(name: str):
    """
    Decorator for creating forward-compatible task routers.

    This creates a task that routes to the appropriate version
    based on deployment configuration.
    """

    def decorator(func):
        @celery_app.task(name=name)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get the appropriate handler
            handler = version_manager.get_handler(name)
            if handler:
                return handler.apply_async(args=args, kwargs=kwargs)
            else:
                # Fallback to the decorated function
                return func(*args, **kwargs)

        return wrapper

    return decorator


# Example: Versioned notification task
@versioned_task("notifier.process_ad", version="v1")
def process_ad_v1(ad_data: Dict[str, Any]):
    """Original ad processing logic"""
    logger.info("Processing ad (v1)", extra={"ad_id": ad_data.get("id")})
    # Original implementation
    return {"status": "processed", "version": "v1"}


@versioned_task("notifier.process_ad", version="v2")
def process_ad_v2(ad_data: Dict[str, Any]):
    """Enhanced ad processing with phone extraction"""
    logger.info("Processing ad (v2)", extra={"ad_id": ad_data.get("id")})

    # New implementation with phone extraction
    phone_numbers = []
    if ad_data.get("resource_url"):
        # Extract phone numbers using new parser
        from common.utils.phone_utils.parsers.phone_parser import (
            extract_phone_numbers_from_resource,
        )

        result = extract_phone_numbers_from_resource(ad_data["resource_url"])
        phone_numbers = result.phone_numbers

    return {"status": "processed", "version": "v2", "phone_numbers": phone_numbers}


@forward_compatible_task("notifier.process_ad")
def process_ad_router(ad_data: Dict[str, Any]):
    """Router that forwards to appropriate version"""
    # This is the fallback if no versions are registered
    logger.warning("No versioned handler found, using fallback")
    return process_ad_v1(ad_data)


class DeploymentConfig:
    """Manages deployment configuration for gradual rollouts"""

    @staticmethod
    def enable_canary(task_name: str, new_version: str, percentage: int = 10):
        """Enable canary deployment for a task"""
        version_manager.set_rollout(
            task_name,
            {
                "canary_enabled": True,
                "canary_version": new_version,
                "canary_percentage": percentage,
                "default_version": "v1",
            },
        )
        logger.info("Enabled canary", extra={"task_name": task_name, "percentage": percentage, "new_version": new_version})

    @staticmethod
    def increase_canary(task_name: str, percentage: int):
        """Increase canary percentage"""
        config = version_manager.rollout_config.get(task_name, {})
        config["canary_percentage"] = percentage
        version_manager.set_rollout(task_name, config)
        logger.info("Increased canary", extra={"task_name": task_name, "percentage": percentage})

    @staticmethod
    def promote_version(task_name: str, new_version: str):
        """Promote a version to be the default"""
        version_manager.set_rollout(
            task_name, {"default_version": new_version, "canary_enabled": False}
        )
        logger.info("Promoted task version", extra={"task_name": task_name, "version": new_version})

    @staticmethod
    def rollback(task_name: str, version: str = "v1"):
        """Rollback to a specific version"""
        version_manager.set_rollout(
            task_name, {"default_version": version, "canary_enabled": False}
        )
        logger.info("Rolled back task version", extra={"task_name": task_name, "version": version})


# Migration helpers
def migrate_task_data(
    data: Dict[str, Any], from_version: str, to_version: str
) -> Dict[str, Any]:
    """
    Migrate task data between versions.

    This is useful when task signatures change between versions.
    """
    migrations = {
        ("v1", "v2"): lambda d: {**d, "extraction_enabled": True},
        ("v2", "v1"): lambda d: {
            k: v for k, v in d.items() if k != "extraction_enabled"
        },
    }

    migration_key = (from_version, to_version)
    if migration_key in migrations:
        return migrations[migration_key](data)

    return data


# Deployment script helpers
def get_deployment_status() -> Dict[str, Any]:
    """Get current deployment status for all versioned tasks"""
    status = {}

    for task_name, config in version_manager.rollout_config.items():
        versions = list(version_manager.versions.get(task_name, {}).keys())
        status[task_name] = {
            "available_versions": versions,
            "default_version": config.get("default_version", "v1"),
            "canary_enabled": config.get("canary_enabled", False),
            "canary_version": config.get("canary_version"),
            "canary_percentage": config.get("canary_percentage", 0),
        }

    return status


def safe_task_transition(
    task_name: str,
    new_version: str,
    canary_duration: timedelta = timedelta(hours=1),
    canary_steps: list = None,
):
    """
    Safely transition a task to a new version with gradual rollout.

    Args:
        task_name: Name of the task
        new_version: New version to deploy
        canary_duration: How long to run each canary step
        canary_steps: List of percentages for canary rollout (default: [10, 25, 50, 100])
    """
    if canary_steps is None:
        canary_steps = [10, 25, 50, 100]

    logger.info("Starting safe transition", extra={"task_name": task_name, "new_version": new_version})

    # Enable canary with first step
    DeploymentConfig.enable_canary(task_name, new_version, canary_steps[0])

    # Log the deployment plan
    logger.info("Deployment plan", extra={"steps": canary_steps, "duration": str(canary_duration)})

    return {
        "task_name": task_name,
        "new_version": new_version,
        "steps": canary_steps,
        "duration": canary_duration,
        "started_at": datetime.now(),
    }
