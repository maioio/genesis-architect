"""genesis mcp — expose Genesis's read-only analysis tools over MCP.

Three actions, deliberately split by dependency:

- ``serve``  runs the FastMCP stdio server so any MCP client (Claude Code,
  Cursor, …) can call the four read-only Genesis tools. Needs the ``mcp`` SDK.
- ``list``   prints the exposed tools. SDK-independent.
- ``call``   invokes one tool locally and prints its JSON. SDK-independent.

Keeping ``list``/``call`` working without the SDK means the command is
inspectable and verifiable even where ``mcp`` is not installed, and mirrors the
read-only, no-network, no-mutation contract of ``mcp_tools`` itself.
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_mcp(args: argparse.Namespace) -> int:
    from genesis_architect_pro import mcp_tools

    action = getattr(args, "mcp_action", None)

    # Bare `genesis mcp` behaves like `genesis mcp list` — a harmless, read-only
    # default that shows what's on offer rather than printing raw help.
    if action in (None, "list"):
        tools = mcp_tools.list_tools()
        if getattr(args, "json_output", False):
            print(json.dumps({"tools": tools}, indent=2))
        else:
            print("\nGenesis MCP tools (read-only, no network, no mutation):\n")
            for t in tools:
                print(f"  {t['name']}\n      {t['description']}")
            print("\nServe them to an MCP client with:  genesis mcp serve")
        return 0

    if action == "call":
        name = args.tool
        try:
            result = mcp_tools.call_tool(name, getattr(args, "dir", "."))
        except KeyError:
            print(f"Unknown tool '{name}'. Run `genesis mcp list` to see them.",
                  file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
        return 0

    if action == "serve":
        if not mcp_tools.mcp_available():
            print(
                "MCP SDK not installed. Install it with:  pip install mcp\n"
                "The tools themselves still work via `genesis mcp list` / "
                "`genesis mcp call`.",
                file=sys.stderr,
            )
            return 2
        server = mcp_tools.build_mcp_server()
        # FastMCP.run() blocks, serving over stdio until the client disconnects.
        server.run()
        return 0

    print(f"Unknown mcp action '{action}'. Use: serve | list | call.",
          file=sys.stderr)
    return 1
