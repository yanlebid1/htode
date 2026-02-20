# system/maintenance/database.py

from ._common import (
    celery_app,
    db_session,
    text,
    time,
    logger,
    log_operation,
    log_context,
    LogAggregator,
    Dict,
    Any,
)


@celery_app.task(name="system.maintenance.optimize_database")
@log_operation("optimize_database")
def optimize_database() -> Dict[str, Any]:
    """
    Perform database maintenance tasks like VACUUM and ANALYZE to optimize performance

    Returns:
        Dictionary with operation status
    """
    start_time = time.time()
    operations = []
    aggregator = LogAggregator(logger, "optimize_database")

    with log_context(logger, task="optimize_database"):
        try:
            # Allowlisted tables — only these can be passed to VACUUM/ANALYZE
            ALLOWED_TABLES = frozenset({
                "ads",
                "ad_images",
                "ad_phones",
                "users",
                "user_filters",
                "favorite_ads",
                "verification_codes",
                "email_verification_tokens",
                "payment_orders",
                "payment_history",
            })

            # Materialized views to refresh during maintenance
            MATERIALIZED_VIEWS = (
                "mv_subscription_stats",
                "mv_subscription_by_city",
                "mv_subscription_by_property",
            )

            tables = list(ALLOWED_TABLES)

            with db_session() as db:
                # For database operations like VACUUM, we need to use raw SQL
                # and manage the connection manually since these operations
                # can't run inside a transaction

                # Get the raw connection from the SQLAlchemy session
                connection = db.connection()

                # These operations need to run outside a transaction
                old_isolation_level = connection.connection.isolation_level
                connection.connection.set_isolation_level(0)  # AUTOCOMMIT mode

                try:
                    # VACUUM ANALYZE on each table
                    for table in tables:
                        if table not in ALLOWED_TABLES:
                            logger.warning("Skipping non-allowlisted table", extra={"table": table})
                            continue
                        logger.info("Running VACUUM ANALYZE", extra={"table": table})
                        # Use text() for proper SQLAlchemy execution; table name
                        # is validated against the allowlist above, not user input.
                        db.execute(text(f"VACUUM ANALYZE {table}"))
                        operations.append(f"VACUUM ANALYZE {table}")
                        aggregator.add_item(
                            {"operation": f"VACUUM ANALYZE {table}"}, success=True
                        )

                    # Update table statistics
                    for table in tables:
                        if table not in ALLOWED_TABLES:
                            continue
                        logger.info("Running ANALYZE", extra={"table": table})
                        db.execute(text(f"ANALYZE {table}"))
                        operations.append(f"ANALYZE {table}")
                        aggregator.add_item(
                            {"operation": f"ANALYZE {table}"}, success=True
                        )

                    # Refresh materialized views
                    for mv in MATERIALIZED_VIEWS:
                        logger.info("Refreshing materialized view", extra={"view": mv})
                        db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}"))
                        operations.append(f"REFRESH MATERIALIZED VIEW {mv}")
                        aggregator.add_item(
                            {"operation": f"REFRESH MATERIALIZED VIEW {mv}"}, success=True
                        )

                    # Optimize indexes
                    logger.info("Reindexing database")
                    db.execute(text("REINDEX DATABASE current_database()"))
                    operations.append("REINDEX DATABASE")
                    aggregator.add_item({"operation": "REINDEX DATABASE"}, success=True)
                finally:
                    # Restore previous isolation level
                    connection.connection.set_isolation_level(old_isolation_level)

        except Exception as e:
            logger.error(
                "Error during database optimization",
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

        execution_time = time.time() - start_time
        aggregator.log_summary()

        logger.info(
            "Database optimization completed",
            extra={
                "execution_time": execution_time,
                "operations_count": len(operations),
            },
        )

        return {
            "status": "success",
            "operations": operations,
            "execution_time_seconds": execution_time,
        }


@celery_app.task(name="system.maintenance.check_database_connections")
@log_operation("check_database_connections")
def check_database_connections() -> Dict[str, Any]:
    """
    Check database connection pool health and reset if necessary

    Returns:
        Dictionary with pool statistics
    """
    # Import the database module here to always reference the current pool instance
    from common.db import database as db_module

    with log_context(logger, task="check_database_connections"):
        # Ensure the pool is initialized
        if db_module.pool is None:
            logger.warning("Database connection pool not initialized, initializing now")
            db_module.initialize_pool()

        # Refresh local reference after a possible initialization
        pool = db_module.pool

        # If initialization still failed, log and exit early
        if pool is None:
            logger.error(
                "Database connection pool is still uninitialized after attempting to initialize."
            )
            return {
                "status": "uninitialized",
                "min_connections": None,
                "max_connections": None,
                "used_connections": None,
            }

        # Get pool statistics
        min_conn = pool.minconn
        max_conn = pool.maxconn
        used_conn = len(pool._used)

        logger.info(
            "Database connection pool status",
            extra={
                "used_connections": used_conn,
                "max_connections": max_conn,
                "usage_percent": (used_conn / max_conn) * 100 if max_conn > 0 else 0,
            },
        )

        # Check if pool is near capacity and should be reset
        if used_conn > max_conn * 0.8:
            logger.warning(
                "Database connection pool is at high capacity",
                extra={"usage_percent": (used_conn / max_conn) * 100},
            )

        # Check for leaked connections (connections used for very long periods)
        if hasattr(pool, "_used") and pool._used:
            import time as time_mod
            old_connections = []
            current_time = time_mod.time()

            for conn_id, (conn, timestamp) in pool._used.items():
                # Check if connection has been held for more than 10 minutes
                if current_time - timestamp > 600:
                    old_connections.append((conn_id, current_time - timestamp))

            if old_connections:
                logger.warning(
                    "Found potentially leaked database connections",
                    extra={"leaked_count": len(old_connections)},
                )
                for conn_id, age in old_connections:
                    logger.warning(
                        "Connection has been active for long time",
                        extra={"connection_id": conn_id, "age_seconds": age},
                    )

        return {
            "status": "checked",
            "min_connections": min_conn,
            "max_connections": max_conn,
            "used_connections": used_conn,
        }
