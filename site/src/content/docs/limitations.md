---
title: Limitations
description: What Genesis does not do, stated plainly.
---

- **Python-first analysis.** The import graph and anti-pattern rules target Python packages. The agent skill's project templates cover more languages than the analysis engines do.
- **Static imports only.** Dynamic imports and runtime plugin loading are invisible to the cycle detector.
- **Research depends on public evidence.** The CLI `init` searches GitHub only; the agent skill can research more broadly with the tools your agent has. Niche domains with few public repositories give thin evidence. Genesis reports `THIN` rather than hiding it.
- **`genesis init` needs an LLM key** and sends your project description to GitHub and to that LLM.
- **No `genesis mcp` subcommand.** The MCP server is started from Python. See [MCP](../mcp/).
- **The score is a signal, not a verdict.** Read the findings behind it.
- **Not for trivial scripts.** If the project is ten lines, the research costs more than it saves.
- **Dual licensing.** The code is AGPL-3.0-or-later. A commercial license is available if AGPL does not fit your use.
