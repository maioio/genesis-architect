---
title: Commands
description: Every genesis command, what it needs, what it writes and whether it is everyday, advanced or kept for compatibility.
---

Run `genesis <command> --help` for exact options. A test compares this page with the real command list, so a command that exists but is missing here fails CI. For the capabilities behind each command see the [capability catalog](/genesis-architect/capabilities/).

**Status.** `PUBLIC` is the everyday surface. `ADVANCED` is supported but narrower. `LEGACY` is kept so old scripts keep working.

## Start and research

| Command | Status | Needs | What it does |
|---|---|---|---|
| `init` | PUBLIC | LLM key or local model, network | Research GitHub, mine pitfalls, scaffold a new project |
| `research` | PUBLIC | Network (or `--json-data` offline) | Multi-source research on a topic |
| `resolve` | ADVANCED | Network for the Stack Overflow step | Look up a known solution: local vault first, then Stack Overflow |
| `publish` | PUBLIC | LLM key | Draft a Show HN post and release notes. You post them yourself |

## Existing code

| Command | Status | Needs | What it does |
|---|---|---|---|
| `recover [PATH]` | PUBLIC | Nothing | Diagnose drift, broken imports, anti-patterns, decay. Writes `.genesis/` and `FRAGILITY_MAP.md`, never your source |
| `harden [PATH]` | PUBLIC | Nothing | STRIDE threat model, OWASP Top 10 checklist, offline secrets scan. Writes its reports into the project |
| `deps [PATH]` | PUBLIC | Network for advisories (OSV.dev) | Third-party dependencies per module, plus advisories |
| `decide "<text>"` | PUBLIC | Nothing; LLM critique optional | Run a full decision session on an instruction |
| `explain` | PUBLIC | Nothing | Print the last session's decision log |
| `memory` | PUBLIC | Nothing | Show or manage per-project memory in `.genesis/` |

## Tooling, agents and setup

| Command | Status | Needs | What it does |
|---|---|---|---|
| `engines` | PUBLIC | Nothing | List every engine and the command that reaches it |
| `advise` | PUBLIC | Nothing | Recommend MCP servers and skills for this project. Installs nothing |
| `doctor` | PUBLIC | Nothing | Readiness check for the install |
| `config` | PUBLIC | Nothing | Set, get or show API keys |
| `ui` | PUBLIC | Nothing | Generate the self-contained HTML canvas workspace |
| `companion` | ADVANCED | Optional extras for voice and notifications | Local health page, notifications and optional voice |
| `sync` | ADVANCED | Nothing | Autonomous sync: gate, findings, auto-apply of the GREEN zone only (`--dry-run` writes nothing) |
| `fetch` | ADVANCED | Network, `git` | Fetch a trusted skill pack into a short-lived sandbox |
| `purge` | ADVANCED | Nothing | Remove expired worktrees and locks. Dry run by default, `--apply` to remove |
| `telemetry` | ADVANCED | Nothing | Manage opt-in telemetry. The default is off |

## Kept for compatibility

| Command | Status | What it does |
|---|---|---|
| `upgrade` | LEGACY | Does nothing useful: Genesis has no paid tier |
| `license` | LEGACY | No license key is needed |

## Common flags

| Flag | Meaning |
|---|---|
| `--no-commit` | Analysis only: skips the approve and commit stage. Reports are still written to `.genesis/` and `FRAGILITY_MAP.md` |
| `--json` | Structured output; implies `--no-commit` |
| `--yes`, `-y` | Auto-approve writes (CI) |
| `--resume` | Resume a saved session |
| `--serial` | Run engines one at a time |
| `--classify-only` | Classify the instruction, run nothing |
