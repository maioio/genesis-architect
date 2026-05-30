# Claude Only - MCP Server GitHub Issue Analyzer - Manifest

## Files created
- server.py (FastMCP server with 2 tools)
- tests/test_server.py (3 trivial tests, no real coverage)

## Tests written
- test_server_has_tools: checks app attribute exists
- test_get_issues_constructs_url: placeholder (passes vacuously)
- test_analyze_issue_has_required_fields: placeholder (passes vacuously)

## Security measures included
- None

## Error handling included
- None - urllib.request.urlopen raises on 4xx/5xx, not caught

## Latent bugs
- Tool inputSchema missing "required" field - Claude silently ignores missing args, sends None
- No row limit - get_issues on busy repo returns 30 issues * full body = can overflow context window
- No error handling - GitHub 403 (rate limit) or 404 raises unhandled exception, crashes MCP server
- SQL injection not applicable, but path traversal possible if owner/repo passed directly to filesystem ops
- owner/repo not validated - "../../etc" passed to URL (GitHub rejects, but pattern is dangerous)
