# common/db/database.py

from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from common.config import DB_CONFIG
from common.utils.logging_config import log_operation, log_context

# Import the common db logger
from . import logger

# Create a global connection pool
pool = None


@log_operation("initialize_pool")
def initialize_pool(min_conn=1, max_conn=10):
    global pool
    try:
        with log_context(logger, min_conn=min_conn, max_conn=max_conn):
            pool = ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                dbname=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"]
            )
            logger.info("DB connection pool initialized", extra={
                'min_connections': min_conn,
                'max_connections': max_conn,
                'host': DB_CONFIG["host"],
                'database': DB_CONFIG["dbname"]
            })
    except Exception as e:
        logger.error("Failed to initialize connection pool", exc_info=True, extra={
            'error_type': type(e).__name__,
            'host': DB_CONFIG["host"],
            'database': DB_CONFIG["dbname"]
        })
        raise


@contextmanager
@log_operation("get_db_connection")
def get_db_connection():
    """
    Context manager for database connections.
    Ensures connections are always returned to the pool, even if an exception occurs.
    """
    global pool
    if pool is None:
        initialize_pool()

    conn = None
    try:
        with log_context(logger, pool_size=pool.maxconn):
            conn = pool.getconn()
            logger.debug("Got connection from pool", extra={
                'connection_id': id(conn)
            })
            yield conn
    finally:
        if conn is not None:
            pool.putconn(conn)
            logger.debug("Returned connection to pool", extra={
                'connection_id': id(conn)
            })


@log_operation("return_connection")
def return_connection(conn):
    """Return a connection to the pool"""
    global pool
    if pool is not None and conn is not None:
        with log_context(logger, connection_id=id(conn)):
            pool.putconn(conn)
            logger.debug("Connection returned to pool")


@contextmanager
@log_operation("get_db_cursor")
def get_db_cursor(commit=True):
    """
    Context manager for database cursors.
    Handles committing or rolling back transactions and ensures proper connection release.
    """
    with log_context(logger, auto_commit=commit):
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                logger.debug("Created database cursor", extra={
                    'cursor_id': id(cursor),
                    'connection_id': id(conn)
                })
                yield cursor
                if commit:
                    conn.commit()
                    logger.debug("Transaction committed")
            except Exception as e:
                conn.rollback()
                logger.warning("Transaction rolled back", extra={
                    'error_type': type(e).__name__,
                    'error': str(e)
                })
                raise
            finally:
                cursor.close()
                logger.debug("Cursor closed", extra={
                    'cursor_id': id(cursor)
                })


@log_operation("execute_query")
def execute_query(sql, params=None, fetch=False, fetchone=False, commit=True):
    """
    Execute a SQL query with proper transaction handling.
    Uses context managers to ensure connections are always returned to the pool.
    """
    with log_context(logger, sql=sql[:100], params_count=len(params) if params else 0, fetch=fetch, fetchone=fetchone):
        try:
            with get_db_cursor(commit=commit) as cur:
                cur.execute(sql, params)

                if fetchone:
                    result = cur.fetchone()
                    logger.debug("Fetched one row")
                elif fetch:
                    result = cur.fetchall()
                    logger.debug("Fetched all rows", extra={
                        'row_count': len(result) if result else 0
                    })
                else:
                    result = cur
                    logger.debug("Returning cursor")

                return result
        except Exception as e:
            logger.error("Database error", exc_info=True, extra={
                'error_type': type(e).__name__,
                'sql': sql[:200],
                'params': str(params)[:200] if params else None
            })
            raise