# Tests from PITFALLS.md Pitfall 1 - session closes before response, not in middleware
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock, patch
import pytest

def test_get_db_commits_on_success():
    """Session commits when no exception raised."""
    from deps import get_db
    mock_session = MagicMock()
    with patch("deps.SessionLocal", return_value=mock_session):
        gen = get_db()
        next(gen)
        try:
            next(gen)
        except StopIteration:
            pass
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()

def test_get_db_rollback_on_exception():
    """Session rolls back when route handler raises, before response returns."""
    from deps import get_db
    mock_session = MagicMock()
    with patch("deps.SessionLocal", return_value=mock_session):
        gen = get_db()
        next(gen)
        try:
            gen.throw(RuntimeError("DB write failed mid-transaction"))
        except RuntimeError:
            pass
    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()

def test_get_db_closes_even_after_rollback():
    """Session always closes - no leaked connections."""
    from deps import get_db
    mock_session = MagicMock()
    mock_session.rollback.side_effect = Exception("rollback failed")
    with patch("deps.SessionLocal", return_value=mock_session):
        gen = get_db()
        next(gen)
        try:
            gen.throw(RuntimeError("original error"))
        except Exception:
            pass
    mock_session.close.assert_called_once()
