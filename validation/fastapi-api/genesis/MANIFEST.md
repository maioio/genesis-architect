# Genesis - FastAPI Task API - Manifest

## Files created
- src/main.py (lifespan with alembic upgrade, all routes)
- src/models.py (SQLAlchemy ORM + Pydantic v2 schemas)
- src/deps.py (get_db with commit/rollback inside dependency)
- src/database.py (engine with explicit pool config)
- tests/test_deps.py
- tests/test_database.py
- tests/test_canary.py
- pyproject.toml (asyncio_mode=auto, pytest-asyncio>=0.23)

## Tests written
- test_get_db_commits_on_success: session commits when no exception
- test_get_db_rollback_on_exception: rollback before response on error
- test_get_db_closes_even_after_rollback: no leaked connections
- test_engine_pool_size_above_default: pool_size >= 20 (not default 5)
- test_engine_pool_pre_ping_enabled: pre_ping=True for stale detection
- test_engine_pool_recycle_set: recycle > 0 prevents idle timeout errors
- test_database_url_from_env: DATABASE_URL from env, never hardcoded
- test_create_and_retrieve_exactly_one_task: canary - catches silent async fixture failure

## Security measures included
- DATABASE_URL from environment variable
- No hardcoded connection strings

## Error handling included
- Transaction rollback on any route exception
- Session always closed (finally block)
- Alembic failure aborts startup
- Pool pre_ping detects stale connections

## What Genesis added vs Claude Only
- Explicit pool configuration (pool_size=20, pre_ping, recycle)
- DB session lifecycle guarded against FastAPI 0.106+ middleware teardown order
- Alembic migration guard in lifespan
- asyncio_mode=auto in pyproject.toml (prevents silent test skip)
- 7 additional tests covering infrastructure not just CRUD
