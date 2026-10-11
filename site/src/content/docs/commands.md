---
title: Commands
description: The genesis command reference.
---

Run `genesis <command> --help` for exact options. `genesis --help` is the source for this page.

| Command | Purpose |
|---|---|
| `init` | Scan GitHub, mine pitfalls, scaffold a new project |
| `research` | Multi-source research on a topic |
| `recover [PATH]` | Diagnose drift, broken imports, anti-patterns, decay |
| `harden [PATH]` | STRIDE threat model, OWASP Top 10, secrets scan |
| `decide "<text>"` | Route an instruction to the right engines |
| `explain` | Print the last session's decision log |
| `engines` | List every engine and the command that reaches it |
| `deps [PATH]` | Third-party dependencies per module, plus advisories |
| `advise` | Recommend MCP servers and skills for this project; installs nothing |
| `memory` | Show or manage per-project memory in `.genesis/` |
| `doctor` | Readiness check for the install |
| `config` | Set, get or show API keys |
| `publish` | Generate a Show HN post and GitHub Release notes |
| `ui`, `companion` | HTML canvas workspace and the local health page |
| `sync`, `fetch`, `purge` | Autonomous sync, read-only skill-pack fetch, expired-resource cleanup |
| `telemetry` | Manage opt-in telemetry. The default is off |

## Common flags

| Flag | Meaning |
|---|---|
| `--no-commit` | Analysis only: skips the approve and commit stage. Reports are still written to `.genesis/` and `FRAGILITY_MAP.md` |
| `--json` | Structured output; implies `--no-commit` |
| `--yes`, `-y` | Auto-approve writes (CI) |
| `--resume` | Resume a saved session |
| `--serial` | Run engines one at a time |
| `--classify-only` | Classify the instruction, run nothing |
