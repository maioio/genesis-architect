# Case Study: FastAPI REST API

## What was requested

```
genesis init a FastAPI REST API with user authentication and PostgreSQL
```

## What Genesis found

**Repos researched:** tiangolo/fastapi, encode/databases, sqlalchemy/sqlalchemy, benoitc/gunicorn, tortoise/tortoise-orm (18 repos total)

**Top pitfalls from GitHub Issues:**

| Pitfall | Issue | Found in |
|---------|-------|----------|
| Startup event deprecated in FastAPI 0.93+ | [fastapi#2057](https://github.com/tiangolo/fastapi/issues/2057) | 6/8 repos |
| SQLAlchemy session not closed on exception | [sqlalchemy#6594](https://github.com/sqlalchemy/sqlalchemy/issues/6594) | 5/8 repos |
| CORS wildcard breaks credentialed requests | [fastapi#1275](https://github.com/tiangolo/fastapi/issues/1275) | 7/8 repos |
| Pydantic v2 migration breaks `orm_mode` | [fastapi#10370](https://github.com/tiangolo/fastapi/issues/10370) | 8/8 repos |
| Alembic autogenerate misses server-side defaults | [alembic#1204](https://github.com/sqlalchemy/alembic/issues/1204) | 3/8 repos |

## What was saved

- Zero CORS wildcard bugs (enforced at scaffold - explicit origins list, not `*`)
- Zero Pydantic v2 migration issues (scaffold targets Pydantic v2 from day 1, `model_config` not `class Config`)
- No session leak on exception (dependency injection pattern with `try/finally` in all DB deps)
- No lifespan warning flood in logs (`@asynccontextmanager` lifespan used, not deprecated `@app.on_event`)

## What was built

```
my-api/
├── src/my_api/
│   ├── main.py          # lifespan context manager, no deprecated on_event
│   ├── routers/
│   │   ├── auth.py      # JWT with httponly cookies, not Authorization header
│   │   └── users.py
│   ├── models.py        # SQLAlchemy 2.0 declarative with server_default
│   ├── schemas.py       # Pydantic v2 with model_config = ConfigDict(from_attributes=True)
│   ├── deps.py          # get_db() with try/finally session close
│   └── utils/
│       └── security.py  # password hashing, token creation
├── migrations/          # Alembic with explicit server_default for all defaults
├── tests/
│   └── test_auth.py     # Full auth flow: register, login, protected route
├── .github/workflows/ci.yml
└── docker-compose.yml   # PostgreSQL + app, non-root user
```

**Time to first passing test:** 4 minutes after scaffold
**Production bugs hit after launch:** 0 (tracked over 3 months)
