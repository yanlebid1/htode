# tests/test_db_session.py

import sys
from unittest.mock import patch, MagicMock

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest
from sqlalchemy.exc import SQLAlchemyError


# ── Test using the conftest fixtures that provide in-memory SQLite ────────


class TestDbSessionContextManager:
    """Test the db_session() context manager using the conftest fixtures."""

    def test_yields_session_and_commits(self, db_session):
        """The conftest db_session fixture provides a working session."""
        from common.db.models.user import User

        user = User(telegram_id="test_session_user_1")
        db_session.add(user)
        db_session.flush()
        assert user.id is not None

    def test_session_rollback_on_error(self, db_session):
        """Session should rollback on error and not persist bad data."""
        from common.db.models.user import User

        user = User(telegram_id="rollback_test_user")
        db_session.add(user)
        db_session.flush()
        user_id = user.id

        # Simulate a rollback
        db_session.rollback()

        # After rollback, the user should not be found
        found = db_session.query(User).get(user_id)
        assert found is None

    def test_session_query_works(self, db_session):
        """Basic session queries work correctly."""
        from common.db.models.user import User

        user = User(telegram_id="query_test_user")
        db_session.add(user)
        db_session.flush()

        result = db_session.query(User).filter_by(telegram_id="query_test_user").first()
        assert result is not None
        assert result.telegram_id == "query_test_user"


class TestDbSessionModule:
    """Test the db_session module-level functions with mocked SessionLocal."""

    @patch("common.db.session.SessionLocal")
    def test_get_db_returns_session(self, mock_session_local):
        from common.db.session import get_db

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        result = get_db()
        assert result is mock_session

    @patch("common.db.session.SessionLocal")
    def test_db_session_yields_and_commits(self, mock_session_local):
        from common.db.session import db_session as db_session_ctx

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        with db_session_ctx() as session:
            assert session is mock_session
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("common.db.session.SessionLocal")
    def test_db_session_rolls_back_on_sqlalchemy_error(self, mock_session_local):
        from common.db.session import db_session as db_session_ctx

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        with pytest.raises(SQLAlchemyError):
            with db_session_ctx() as session:
                raise SQLAlchemyError("db error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("common.db.session.SessionLocal")
    def test_db_session_rolls_back_on_generic_exception(self, mock_session_local):
        from common.db.session import db_session as db_session_ctx

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        with pytest.raises(RuntimeError):
            with db_session_ctx() as session:
                raise RuntimeError("unexpected error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("common.db.session.SessionLocal")
    def test_db_session_always_closes(self, mock_session_local):
        from common.db.session import db_session as db_session_ctx

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        # Normal exit
        with db_session_ctx() as session:
            pass
        assert mock_session.close.call_count == 1

    @patch("common.db.session.SessionLocal")
    def test_get_db_dependency_yields_and_closes(self, mock_session_local):
        from common.db.session import get_db_dependency

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        gen = get_db_dependency()
        session = next(gen)
        assert session is mock_session

        # Exhaust the generator
        try:
            next(gen)
        except StopIteration:
            pass

        mock_session.close.assert_called_once()
