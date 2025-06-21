# common/messaging/task_registry.py
from common.celery_app import celery_app
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger

# Dictionary to store registered task mappings
task_mappings = {}


@log_operation("register_platform_tasks")
def register_platform_tasks(platform_name: str, task_module_path: str):
    """
    Register common messaging tasks for a specific platform.

    Args:
        platform_name: Name of the platform (telegram,)
        task_module_path: Base module path for the platform's tasks (e.g., 'telegram_service.app.tasks')
    """
    with log_context(
        logger, platform_name=platform_name, task_module_path=task_module_path
    ):
        try:
            from common.messaging.tasks import (
                send_ad_with_extra_buttons as unified_send_ad,
                send_subscription_notification as unified_send_notification,
            )

            # Register send_ad_with_extra_buttons
            @celery_app.task(name=f"{task_module_path}.send_ad_with_extra_buttons")
            def platform_send_ad_with_extra_buttons(
                user_id, text, s3_image_url, resource_url, ad_id, ad_external_id
            ):
                return unified_send_ad.delay(
                    user_id=user_id,
                    text=text,
                    s3_image_url=s3_image_url,
                    resource_url=resource_url,
                    ad_id=ad_id,
                    ad_external_id=ad_external_id,
                    platform=platform_name,
                )

            # Register send_subscription_notification
            @celery_app.task(name=f"{task_module_path}.send_subscription_notification")
            def platform_send_subscription_notification(
                user_id, notification_type, data
            ):
                return unified_send_notification.delay(
                    user_id=user_id, notification_type=notification_type, data=data
                )

            # Store mappings for future reference
            task_mappings[f"{task_module_path}.send_ad_with_extra_buttons"] = (
                platform_send_ad_with_extra_buttons
            )
            task_mappings[f"{task_module_path}.send_subscription_notification"] = (
                platform_send_subscription_notification
            )

            logger.info(
                "Platform tasks registered successfully",
                extra={
                    "platform_name": platform_name,
                    "task_module_path": task_module_path,
                    "tasks_registered": 2,
                },
            )

            # Return the registered tasks for reference
            return {
                "send_ad_with_extra_buttons": platform_send_ad_with_extra_buttons,
                "send_subscription_notification": platform_send_subscription_notification,
            }
        except ImportError as e:
            logger.error(
                "Failed to import common messaging tasks",
                exc_info=True,
                extra={"platform_name": platform_name, "error_type": type(e).__name__},
            )
            return {}
        except Exception as e:
            logger.error(
                "Failed to register tasks for platform",
                exc_info=True,
                extra={"platform_name": platform_name, "error_type": type(e).__name__},
            )
            return {}
