# ADR 001: Initial Architecture

**Status**: Accepted
**Date**: 2026-05-20

## Context

Python CLI for log file analysis. Research across 5 repos (click, typer, python-fire, tqdm, prompt-toolkit).

## Decision

Minimalist tier: thin CLI entry point (`cli.py`) delegates to pure-function core (`core.py`).
No server, no database. File-based I/O only.

## Top-level structure

- `src/` - application source
- `tests/` - unit tests
- `docs/` - architecture decision records

## Consequences

- Core logic testable without subprocess
- Path traversal blocked at entry point via security.py
- Pitfalls from PITFALLS.md avoided by construction
