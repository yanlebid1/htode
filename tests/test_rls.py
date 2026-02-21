# tests/test_rls.py
"""
Tests for Row-Level Security (RLS) session helper.

These tests verify that:
1. rls_session() issues SET LOCAL with the correct user_id
2. db_session() (no RLS) does NOT set the variable
3. The rls_session context manager properly yields a usable session
"""

import sys
from unittest.mock import patch, MagicMock, call

# Pre-mock adspower_manager to avoid selenium import chain
sys.modules.setdefault(
    "common.utils.phone_utils.adspower_manager", MagicMock()
)

import pytest


class TestRlsSession:
    """Tests for the rls_session() context manager."""

    @patch("common.db.session.db_session")
    def test_sets_local_user_id(self, mock_db_session_ctx):
        """rls_session should execute SET LOCAL app.current_user_id."""
        from common.db.session import rls_session

        mock_db = MagicMock()
        mock_db_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with rls_session(user_id=42) as db:
            pass

        # Verify SET LOCAL was called with the correct user_id
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "SET LOCAL app.current_user_id" in sql_text
        # The params dict is passed as 2nd positional arg
        assert call_args[0][1]["uid"] == "42"

    @patch("common.db.session.db_session")
    def test_yields_usable_session(self, mock_db_session_ctx):
        """rls_session should yield the underlying db session for queries."""
        from common.db.session import rls_session

        mock_db = MagicMock()
        mock_db_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with rls_session(user_id=1) as db:
            # Should be able to use the session for queries
            db.query("something")

        # SET LOCAL + the query call
        assert mock_db.execute.call_count == 1
        assert mock_db.query.call_count == 1

    @patch("common.db.session.db_session")
    def test_different_user_ids(self, mock_db_session_ctx):
        """rls_session should pass the correct user_id each time."""
        from common.db.session import rls_session

        mock_db = MagicMock()
        mock_db_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with rls_session(user_id=100) as db:
            pass

        call_args = mock_db.execute.call_args
        assert call_args[0][1]["uid"] == "100"

    @patch("common.db.session.db_session")
    def test_user_id_converted_to_string(self, mock_db_session_ctx):
        """user_id should be converted to string for the SQL parameter."""
        from common.db.session import rls_session

        mock_db = MagicMock()
        mock_db_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        with rls_session(user_id=999) as db:
            pass

        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][1]["uid"], str)


class TestDbSessionNoRls:
    """Verify that plain db_session does NOT set app.current_user_id."""

    @patch("common.db.session.SessionLocal")
    def test_db_session_does_not_set_rls_variable(self, mock_session_local):
        """db_session should not issue any SET LOCAL statement."""
        from common.db.session import db_session

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        with db_session() as db:
            pass

        # Check that no SET LOCAL was executed
        for c in mock_db.execute.call_args_list:
            sql = str(c[0][0]) if c[0] else ""
            assert "app.current_user_id" not in sql


class TestMigrateRlsScript:
    """Tests for the RLS migration script."""

    def test_rls_tables_list_complete(self):
        """Migration script should cover all 6 user-owned tables."""
        from scripts.migrate_rls import RLS_TABLES

        expected = {
            "user_filters",
            "favorite_ads",
            "subscriptions",
            "payment_orders",
            "payment_history",
            "verification_codes",
        }
        assert set(RLS_TABLES) == expected

    def test_policy_template_has_both_policies(self):
        """Template should generate both user and system policies."""
        from scripts.migrate_rls import POLICY_TEMPLATE

        rendered = POLICY_TEMPLATE.format(table="user_filters")
        assert "user_filters_user_policy" in rendered
        assert "user_filters_system_policy" in rendered
        assert "current_setting('app.current_user_id'" in rendered
