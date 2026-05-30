# Tests from PITFALLS.md Pitfall 2 - pool config explicitly set, not defaults
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_engine_pool_size_above_default():
    """pool_size must be > 5 (SQLAlchemy default) to survive concurrent load."""
    from database import engine
    assert engine.pool.size() >= 20, (
        f"pool_size={engine.pool.size()} - default of 5 exhausts under 50+ concurrent requests"
    )

def test_engine_pool_pre_ping_enabled():
    """pool_pre_ping must be True to detect stale connections before reuse."""
    from database import engine
    assert engine.pool._pre_ping is True, (
        "pool_pre_ping=False causes asyncpg.InterfaceError when stale connections reused"
    )

def test_engine_pool_recycle_set():
    """pool_recycle must be set to prevent using connections older than Postgres idle timeout."""
    from database import engine
    assert engine.pool._recycle > 0, (
        "No pool_recycle means connections older than Postgres timeout (default 10min) cause errors"
    )

def test_database_url_from_env():
    """DATABASE_URL must come from environment, not be hardcoded."""
    import database
    import inspect
    src = inspect.getsource(database)
    assert "os.environ" in src, "DATABASE_URL must be read from environment variable"
    assert 'DATABASE_URL = "' not in src, "DATABASE_URL must not be hardcoded"
