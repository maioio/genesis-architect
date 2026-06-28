# MCP Tools

**Pro.** Genesis exposes its core analysis as MCP tools, so any MCP client can
call them. The customer never starts a server by hand — the adapter does.

## Available tools

| Tool | What it returns |
|------|-----------------|
| `genesis_architecture_score` | 0–100 score with dimension breakdown |
| `genesis_anti_patterns` | Detected anti-patterns + severity counts |
| `genesis_recovery_report` | Full recovery / project-intelligence report |
| `genesis_gate` | The `genesis gate` result (pass/fail + reasons) |

## Usage

```python
from genesis_architect_pro.mcp_tools import list_tools, call_tool

list_tools()                                  # tool schemas
call_tool("genesis_architecture_score", {"project_path": "."})
```

## Server (SDK-optional)

```python
from genesis_architect_pro.mcp_tools import build_mcp_server
server = build_mcp_server()      # built only if the MCP SDK is installed
```

If the MCP SDK is absent, the tool functions still work directly (no server) —
nothing forces an extra dependency on the customer. This is part of the
[no-setup promise](50_install_license.md).
