# system/maintenance/statistics.py

from ._common import (
    celery_app,
    db_session,
    or_,
    func,
    text,
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

# Materialized views to refresh before reading
_MV_NAMES = (
    "mv_subscription_stats",
    "mv_subscription_by_city",
    "mv_subscription_by_property",
)


@celery_app.task(name="system.maintenance.check_subscription_statistics")
@log_operation("check_subscription_statistics")
def check_subscription_statistics() -> Dict[str, Any]:
    """
    Refresh materialized views and read pre-computed subscription statistics.

    Returns:
        Dictionary with subscriber counts and statistics
    """
    start_time = time.time()
    aggregator = LogAggregator(logger, "check_subscription_statistics")

    with log_context(logger, task="check_subscription_statistics"):
        try:
            with db_session() as db:
                # Refresh materialized views concurrently (non-blocking reads)
                for mv in _MV_NAMES:
                    logger.info("Refreshing materialized view", extra={"view": mv})
                    db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}"))
                    aggregator.add_item({"refresh": mv}, success=True)

                db.commit()

                # Read pre-computed stats from the materialized view
                row = db.execute(text("SELECT * FROM mv_subscription_stats")).fetchone()
                active_subscribers = row[0] if row else 0
                paid_subscribers = row[1] if row else 0
                free_trial_subscribers = row[2] if row else 0
                telegram_subscribers = row[3] if row else 0

                # Read city breakdown
                city_rows = db.execute(
                    text("SELECT city, subscriber_count FROM mv_subscription_by_city")
                ).fetchall()
                city_stats = {
                    GEO_ID_MAPPING.get(int(city_id), f"Unknown ({city_id})"): count
                    for city_id, count in city_rows
                }

                # Read property type breakdown
                prop_rows = db.execute(
                    text("SELECT property_type, subscriber_count FROM mv_subscription_by_property")
                ).fetchall()
                property_stats = {
                    property_type: count
                    for property_type, count in prop_rows
                }

                subscription_counts = {
                    "by_city": city_stats,
                    "by_property_type": property_stats,
                }

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
