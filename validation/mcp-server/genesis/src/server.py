# Architecture note: required[] in every schema, all HTTP via github_client
# Avoids: Pitfall 1 - missing required causes silent None args
# Avoids: Pitfall 3 - direct urlopen crashes server on 403/429

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from github_client import fetch_json
from limits import truncate_result
import json

app = Server("github-issue-analyzer")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_issues",
            description="Get issues from a GitHub repository. Results capped at 20 to avoid context overflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                },
                "required": ["owner", "repo"],
            },
        ),
        types.Tool(
            name="analyze_issue",
            description="Get details of a specific GitHub issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer", "minimum": 1},
                },
                "required": ["owner", "repo", "issue_number"],
            },
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_issues":
        owner = arguments["owner"]
        repo = arguments["repo"]
        state = arguments.get("state", "open")
        limit = arguments.get("limit", 20)
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page=50"
        data = fetch_json(url)
        if isinstance(data, dict) and data.get("isError"):
            return [types.TextContent(type="text", text=json.dumps(data))]
        result = truncate_result(
            [{"number": i["number"], "title": i["title"], "state": i["state"],
              "body": i.get("body", ""), "comments": i["comments"]} for i in data],
            limit=limit,
        )
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "analyze_issue":
        owner = arguments["owner"]
        repo = arguments["repo"]
        num = arguments["issue_number"]
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"
        data = fetch_json(url)
        if isinstance(data, dict) and data.get("isError"):
            return [types.TextContent(type="text", text=json.dumps(data))]
        body = data.get("body") or ""
        if len(body) > 500:
            body = body[:500] + "... [truncated]"
        return [types.TextContent(type="text", text=json.dumps({
            "title": data["title"],
            "body": body,
            "comments": data["comments"],
            "labels": [lb["name"] for lb in data.get("labels", [])],
        }, indent=2))]

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
