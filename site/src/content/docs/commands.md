---
title: Commands
description: Every genesis command, what it needs, what it writes and whether it is everyday, advanced or kept for compatibility.
---

Run `genesis <command> --help` for exact options. A test compares this page with the real command list, so a command that exists but is missing here fails CI. For the capabilities behind each command see the [capability catalog](https://maioio.github.io/genesis-architect/capabilities/).

**Status.** `PUBLIC` is the everyday surface. `ADVANCED` is supported but narrower. `LEGACY` is kept so old scripts keep working.

## Start and research

| Command | Status | Needs | What it does |
|---|---|---|---|
| `init` | PUBLIC | `LLM_API_KEY` (also with a local model), network | Research GitHub repos and their issues, then write `RESEARCH.md` and `PITFALLS.md`. Writes no application code; the full build is the [agent-skill workflow](../new-projects/) |
| `research` | PUBLIC | Nothing | Rank research evidence you or your agent collected (`--json-data`); with no data it prints a collection guide. It does not search by itself. `--video` builds video search queries for `/watch`; `--absorb` turns a `/watch` analysis into `PITFALLS.md` entries |
| `resolve` | ADVANCED | Network for the Stack Overflow step | Look up a known solution: local vault first, then Stack Overflow |
| `publish` | PUBLIC | `LLM_API_KEY` | Draft a Show HN post and release notes. You post them yourself |

## Existing code

| Command | Status | Needs | What it does |
|---|---|---|---|
| `recover [PATH]` | PUBLIC | Nothing | Diagnose drift, broken imports, anti-patterns, decay. Writes `.genesis/` and `FRAGILITY_MAP.md`; `PROJECT_RECOVERY_REPORT.md` only after you approve. Never edits your source |
| `harden [PATH]` | PUBLIC | Nothing required; in gate mode it asks OSV.dev about up to 15 package names from Python imports, and skips the lookup if it fails | STRIDE threat model, OWASP Top 10 checklist, offline secrets scan. Writes `.genesis/` and `FRAGILITY_MAP.md`; proposes its reports under `docs/security/`; they are written only after you approve (default is Defer) or pass `--yes` |
| `deps [PATH]` | PUBLIC | Network for advisories (OSV.dev); `--no-cve` skips the lookup | Third-party dependencies per module (read from Python imports), plus advisories. A project scan exits with code 1 when advisories are found (`--json` always exits 0). `--package NAME` skips the scan and looks up one package in its public registry (PyPI by default; `--ecosystem npm`, `crates`, `maven` or `nuget` for the others), prints what the registry reports about its releases, and exits 0 |
| `decide "<text>"` | PUBLIC | Nothing required; LLM critique optional; a session in gate mode can ask OSV.dev like `harden` | Run a full decision session on an instruction |
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
| `--no-commit` | Analysis only: skips the approve and commit stages, so no proposed report is written. Analysis output is still written: `.genesis/` state and, when the fragility classifier runs (as in `recover` and `harden`), `FRAGILITY_MAP.md`. See the [approval model](../approval-model/) |
| `--json` | Structured output; implies `--no-commit` |
| `--yes`, `-y` | Auto-approve pending writes (CI). Does not override a hard block |
| `--resume` | Resume a saved session |
| `--serial` | Run engines one at a time |
| `--classify-only` | Classify the instruction, run nothing |
