"""MCP server that analyzes GitHub issues - Claude Only version."""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import urllib.request
import json

app = Server("github-issue-analyzer")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_issues",
            description="Get issues from a GitHub repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "default": "open"},
                },
            },
        ),
        types.Tool(
            name="analyze_issue",
            description="Analyze a specific issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                },
            },
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_issues":
        owner = arguments["owner"]
        repo = arguments["repo"]
        state = arguments.get("state", "open")
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page=30"
        with urllib.request.urlopen(url) as r:
            issues = json.loads(r.read())
        result = [{"number": i["number"], "title": i["title"], "state": i["state"]} for i in issues]
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "analyze_issue":
        owner = arguments["owner"]
        repo = arguments["repo"]
        num = arguments["issue_number"]
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"
        with urllib.request.urlopen(url) as r:
            issue = json.loads(r.read())
        return [types.TextContent(type="text", text=json.dumps({
            "title": issue["title"],
            "body": issue.get("body", ""),
            "comments": issue["comments"],
            "labels": [l["name"] for l in issue.get("labels", [])],
        }, indent=2))]

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
