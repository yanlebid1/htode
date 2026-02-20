# system/maintenance/statistics.py

from ._common import (
    celery_app,
    db_session,
    or_,
    func,
    time,
    datetime,
    logger,
    log_operation,
    log_context,
    LogAggregator,
    User,
    UserFilter,
    CacheTTL,
    GEO_ID_MAPPING,
    BaseCacheManager,
    Dict,
    Any,
)


@celery_app.task(name="system.maintenance.check_subscription_statistics")
@log_operation("check_subscription_statistics")
def check_subscription_statistics() -> Dict[str, Any]:
    """
    Generate and save subscription statistics

    Returns:
        Dictionary with subscriber counts and statistics
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "check_subscription_statistics")

    with log_context(logger, task="check_subscription_statistics"):
        try:
            with db_session() as db:
                # Count active subscribers
                active_subscribers = (
                    db.query(func.count(User.id))
                    .filter(
                        or_(
                            User.subscription_until > datetime.now(),
                            User.free_until > datetime.now(),
                        )
                    )
                    .scalar()
                )

                # Count paid subscribers
                paid_subscribers = (
                    db.query(func.count(User.id))
                    .filter(User.subscription_until > datetime.now())
                    .scalar()
                )

                # Count free trial subscribers
                free_trial_subscribers = (
                    db.query(func.count(User.id))
                    .filter(
                        User.free_until > datetime.now(),
                        or_(
                            User.subscription_until.is_(None),
                            User.subscription_until < datetime.now(),
                        ),
                    )
                    .scalar()
                )

                # Count subscribers by platform
                telegram_subscribers = (
                    db.query(func.count(User.id))
                    .filter(
                        User.telegram_id.isnot(None),
                        or_(
                            User.subscription_until > datetime.now(),
                            User.free_until > datetime.now(),
                        ),
                    )
                    .scalar()
                )

                # Count by subscription filter
                subscription_counts = {}

                # Count by city
                city_counts = (
                    db.query(
                        UserFilter.city, func.count(UserFilter.city).label("count")
                    )
                    .join(User, UserFilter.user_id == User.id)
                    .filter(
                        or_(
                            User.subscription_until > datetime.now(),
                            User.free_until > datetime.now(),
                        ),
                        UserFilter.city.isnot(None),
                    )
                    .group_by(UserFilter.city)
                    .all()
                )

                city_stats = {
                    GEO_ID_MAPPING.get(city_id, f"Unknown ({city_id})"): count
                    for city_id, count in city_counts
                }

                subscription_counts["by_city"] = city_stats

                # Count by property type
                property_type_counts = (
                    db.query(
                        UserFilter.property_type,
                        func.count(UserFilter.property_type).label("count"),
                    )
                    .join(User, UserFilter.user_id == User.id)
                    .filter(
                        or_(
                            User.subscription_until > datetime.now(),
                            User.free_until > datetime.now(),
                        ),
                        UserFilter.property_type.isnot(None),
                    )
                    .group_by(UserFilter.property_type)
                    .all()
                )

                property_stats = {
                    property_type: count
                    for property_type, count in property_type_counts
                }

                subscription_counts["by_property_type"] = property_stats

                # Store statistics in Redis for later access
                statistics = {
                    "timestamp": datetime.now().isoformat(),
                    "active_subscribers": active_subscribers,
                    "paid_subscribers": paid_subscribers,
                    "free_trial_subscribers": free_trial_subscribers,
                    "platform_breakdown": {
                        "telegram": telegram_subscribers,
                    },
                    "subscription_counts": subscription_counts,
                }

                BaseCacheManager.set(
                    "subscription_statistics", statistics, CacheTTL.LONG
                )

                execution_time = time.time() - start_time

                logger.info(
                    "Generated subscription statistics",
                    extra={
                        "active_subscribers": active_subscribers,
                        "paid_subscribers": paid_subscribers,
                        "free_trial_subscribers": free_trial_subscribers,
                        "execution_time": execution_time,
                    },
                )

                aggregator.add_item({"statistics": "generated"}, success=True)
                aggregator.log_summary()

                return {
                    "status": "success",
                    "statistics": statistics,
                    "execution_time_seconds": execution_time,
                }
        except Exception as e:
            logger.error(
                "Error generating subscription statistics",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )
            aggregator.add_error(str(e), {})
            aggregator.log_summary()
            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time,
            }


@celery_app.task(name="system.maintenance.update_currency_rate")
@log_operation("update_currency_rate")
def update_currency_rate() -> Dict[str, Any]:
    """
    Update the USD to UAH currency exchange rate in the cache.

    This task is scheduled to run twice daily to ensure we have
    updated currency rates for price conversions.

    Returns:
        Dictionary with operation status and the new rate
    """
    start_time = time.time()

    with log_context(logger, task="update_currency_rate"):
        try:
            from common.utils.currency_manager import CurrencyRateManager

            # Update the rate in cache
            rate = CurrencyRateManager.update_rate()

            execution_time = time.time() - start_time

            logger.info(
                "Updated currency rate",
                extra={"rate": str(rate), "execution_time": execution_time},
            )

            return {
                "status": "success",
                "rate": str(rate),
                "execution_time_seconds": execution_time,
            }
        except Exception as e:
            logger.error(
                "Error updating currency rate",
                exc_info=True,
                extra={"error_type": type(e).__name__},
            )

            return {
                "status": "error",
                "error": str(e),
                "execution_time_seconds": time.time() - start_time,
            }
