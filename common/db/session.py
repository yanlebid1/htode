# common/db/session.py
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from common.config import DB_CONFIG
from common.utils.logging_config import log_operation, log_context

# Import the common db logger
from . import logger

# Create the database URL from config
DATABASE_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"

# Create an engine and session factory with connection pooling settings
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@log_operation("get_db")
def get_db() -> Session:
    """Get a database session"""
    db = SessionLocal()
    logger.debug("Created database session", extra={"session_id": id(db)})
    try:
        return db
    except Exception as e:
        db.close()
        logger.error(
            "Error creating database session",
            exc_info=True,
            extra={"error_type": type(e).__name__},
        )
        raise


@contextmanager
@log_operation("db_session")
def db_session() -> Generator[Session, None, None]:
    """Session context manager to ensure proper closing"""
    db = get_db()
    try:
        with log_context(logger, session_id=id(db)):
            yield db
            db.commit()
            logger.debug("Database session committed")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(
            "Database error - rolling back",
            exc_info=True,
            extra={"error_type": type(e).__name__, "session_id": id(db)},
        )
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            "Unexpected error - rolling back",
            exc_info=True,
            extra={"error_type": type(e).__name__, "session_id": id(db)},
        )
        raise
    finally:
        db.close()
        logger.debug("Database session closed", extra={"session_id": id(db)})


@log_operation("get_db_dependency")
def get_db_dependency():
    """Get a database session for dependency injection"""
    db = SessionLocal()
    logger.debug("Created dependency injection session", extra={"session_id": id(db)})
    try:
        yield db
    finally:
        db.close()
        logger.debug(
            "Dependency injection session closed", extra={"session_id": id(db)}
        )
