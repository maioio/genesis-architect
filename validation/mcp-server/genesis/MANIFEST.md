# Genesis - MCP Server GitHub Issue Analyzer - Manifest

## Files created
- PITFALLS.md (3 pitfalls with Implementation + Validate blocks)
- src/server.py (required[] in every schema, all HTTP via github_client)
- src/github_client.py (fetch_json with 403/429/404/URLError handling)
- src/limits.py (truncate_result: cap at 20, body at 500 chars)
- tests/test_schema.py (4 schema validation tests)
- tests/test_limits.py (5 result size tests)
- tests/test_github_client.py (5 HTTP error handling tests)

## Tests written (14 total)
- test_all_tools_have_required_field: each tool has "required" key
- test_required_field_is_non_empty: required has at least 1 entry
- test_get_issues_requires_owner_and_repo: specific required fields
- test_analyze_issue_requires_issue_number: specific required field
- test_caps_at_max_issues: 100 issues -> 20 returned
- test_truncated_flag_true_when_capped: truncated=true when capped
- test_truncated_flag_false_when_not_capped: truncated=false when not
- test_body_truncated_to_preview_chars: body <= 500+margin chars
- test_hard_cap_at_50_regardless_of_limit_param: limit=200 still caps at 50
- test_403_returns_rate_limit_message: isError=true, rate limit message
- test_429_returns_retry_after: isError=true, retry-after time in message
- test_404_returns_not_found: isError=true, not found message
- test_network_error_returns_is_error: URLError -> isError=true
- test_successful_response_parsed: happy path returns parsed list

## What Genesis added vs Claude Only
- required[] in every tool schema (Claude Only: missing -> silent None args)
- src/github_client.py (Claude Only: direct urlopen, crashes on 403)
- src/limits.py (Claude Only: returns full response, overflows context)
- 14 tests vs 3 placeholder tests that all pass vacuously
