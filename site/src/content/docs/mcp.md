---
title: MCP
description: Expose Genesis analysis to any MCP client as read-only tools.
---

Genesis exposes four read-only analysis tools. They take a `project_dir` and return JSON. They do not mutate files, auto-fix or use the network.

| Tool | Returns |
|---|---|
| `genesis_architecture_score` | 0 to 100 score with modularity, coupling, cohesion and layering |
| `genesis_anti_patterns` | Anti-pattern findings with severity |
| `genesis_recovery_report` | The recovery diagnosis |
| `genesis_gate` | The gate verdict for the project |

These are the tools Genesis exposes. They are separate from any external MCP tools an agent uses for research while Genesis runs as a skill; see [Research and evidence](../research-and-evidence/).

## Running the server

The tools are plain Python functions and work without any MCP SDK. To serve them over MCP, install the SDK and start the server from Python:

```bash
pip install mcp
python -c "from genesis_architect.pro.mcp_tools import build_mcp_server; build_mcp_server().run()"
```

There is no `genesis mcp` subcommand yet. See [Limitations](../limitations/).

## Client configuration

Point your client at that command. For a stdio client the shape is:

```json
{
  "mcpServers": {
    "genesis": {
      "command": "python",
      "args": ["-c", "from genesis_architect.pro.mcp_tools import build_mcp_server; build_mcp_server().run()"]
    }
  }
}
```

## Recommending servers for your project

`genesis advise` suggests MCP servers and skills for the project in front of it. It installs nothing.
