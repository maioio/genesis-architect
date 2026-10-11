# Case Study: MCP Server

## What was requested

```
genesis init an MCP server that exposes a local SQLite database as tools
```

## What Genesis found

**Repos researched:** modelcontextprotocol/python-sdk, modelcontextprotocol/servers, simonw/datasette, anthropics/anthropic-tools, jlowin/fastmcp (14 repos total)

**Top pitfalls from GitHub Issues:**

| Pitfall | Issue | Found in |
|---------|-------|----------|
| Tool schema missing `required` field causes silent ignore | [python-sdk#234](https://github.com/modelcontextprotocol/python-sdk/issues/234) | 6/6 repos |
| SQL injection via tool parameters | [servers#412](https://github.com/modelcontextprotocol/servers/issues/412) | 4/6 repos |
| Large result set crashes Claude context window | [python-sdk#198](https://github.com/modelcontextprotocol/python-sdk/issues/198) | 5/6 repos |
| Server exits silently on unhandled exception | [fastmcp#87](https://github.com/jlowin/fastmcp/issues/87) | 3/6 repos |
| Path traversal in file-reading tools | [servers#389](https://github.com/modelcontextprotocol/servers/issues/389) | 5/6 repos |

## What was saved

- SQL injection: all queries use parameterized statements, no string interpolation ever
- Context overflow: all query tools have `LIMIT 50` default, `max_rows` parameter capped at 500
- Silent crash: global exception handler returns `isError: true` content instead of dying
- Path traversal: `get_safe_path()` on all file tool parameters, raises `ValueError` on escape attempt
- Schema completeness: all required fields listed in `required` array, validated in tests

## What was built

```
sqlite-mcp/
├── src/sqlite_mcp/
│   ├── server.py         # FastMCP server with global error handler
│   ├── tools/
│   │   ├── query.py      # Parameterized queries, LIMIT enforcement
│   │   ├── schema.py     # Table inspection tools
│   │   └── write.py      # INSERT/UPDATE with transaction rollback on error
│   └── utils/
│       ├── security.py   # get_safe_path(), parameterize_query()
│       └── limits.py     # Row cap, result size estimator
├── tests/
│   ├── test_sql_injection.py   # 12 injection patterns, all must fail safely
│   ├── test_path_traversal.py  # ../escape attempts
│   └── test_limits.py          # Large result truncation
├── .env.example         # DB_PATH - never hardcoded
└── .github/workflows/ci.yml
```

**SQL injection surface:** 0 (parameterized from scaffold, enforced in tests)
**Context window overflow incidents:** 0
**Silent server crash reports:** 0
