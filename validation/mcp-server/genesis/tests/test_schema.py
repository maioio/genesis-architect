# Tests from PITFALLS.md Pitfall 1 - required field in every tool schema
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import asyncio


def get_tools():
    from server import list_tools
    return asyncio.run(list_tools())


def test_all_tools_have_required_field():
    tools = get_tools()
    for tool in tools:
        assert "required" in tool.inputSchema, (
            f"Tool '{tool.name}' missing 'required' in inputSchema. "
            "Claude will silently pass None for missing args."
        )


def test_required_field_is_non_empty():
    tools = get_tools()
    for tool in tools:
        required = tool.inputSchema.get("required", [])
        assert len(required) >= 1, (
            f"Tool '{tool.name}' has empty 'required' array - defeats the purpose"
        )


def test_get_issues_requires_owner_and_repo():
    tools = get_tools()
    get_issues = next(t for t in tools if t.name == "get_issues")
    assert "owner" in get_issues.inputSchema["required"]
    assert "repo" in get_issues.inputSchema["required"]


def test_analyze_issue_requires_issue_number():
    tools = get_tools()
    analyze = next(t for t in tools if t.name == "analyze_issue")
    assert "issue_number" in analyze.inputSchema["required"]
