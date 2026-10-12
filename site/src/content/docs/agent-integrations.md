---
title: Agent integrations
description: Use Genesis from Claude Code, Cursor, Codex or any MCP client.
---

Genesis ships as a Python package and as an agent skill (`SKILL.md`).

| Agent | How |
|---|---|
| Claude Code | `git clone https://github.com/maioio/genesis-architect ~/.claude/skills/genesis-architect` |
| skills.sh | `npx skills add maioio/genesis-architect` |
| Cursor | Copy `SKILL.md` to `.cursor/rules/genesis-architect.md` |
| Codex | `git clone https://github.com/maioio/genesis-architect ~/.codex/skills/genesis-architect` |
| Any MCP client | See [MCP](../mcp/) |

The skill triggers on phrases such as "I want to build", "scaffold" and `genesis init`. The CLI works on its own with none of these installed.

As a skill, Genesis can use the web and MCP tools your agent already has (search, GitHub, package and security lookups) for research. That is separate from the four read-only MCP analysis tools Genesis exposes, which do not use the network. The standalone CLI does not do this broader research. See [Research and evidence](../research-and-evidence/).

## Machine-readable facts

Agents that need the structure of Genesis can read `ARCHITECTURE_INVARIANTS.json` (engines, gates, modes, sources, tiers) and `data/public-product-facts.json` from the repository root. Both are generated from the code and checked in CI.
