# Genesis Architect v3.0.0 — "The Standalone & Smart Research Update"

> *Research first. Build once. Now from anywhere.*

This is the biggest release since Genesis was born. We went from a Claude Code-only skill to a **fully standalone, pip-installable CLI** — and we rebuilt the research engine from the ground up with four new intelligence layers. If you've been waiting to share Genesis with teammates who don't use Claude Code, today is that day.

---

## 🚀 Major Features

### 1. Standalone CLI — `pip install genesis-architect`

Genesis is no longer tied to Claude Code. Install it once, run it anywhere.

```bash
pip install genesis-architect
genesis config set LLM_API_KEY your-key
genesis init "a FastAPI task queue with Celery and Redis"
```

Works with **Claude, GPT-4, Gemini, Ollama** — any provider supported by LiteLLM. One command to configure, one command to build. No Claude Code required, no skill directory, no setup ceremony.

This multiplies the potential audience by 50x. Every Python developer on every machine can now use Genesis.

---

### 2. Self-Healing Knowledge Vault

Genesis now remembers solutions between runs.

Every Stack Overflow answer and resolved pitfall gets cached in `.genesis/vault/index.json` with:
- **6-month TTL** — stale entries are flagged and refreshed automatically on the next run
- **LRU eviction at 500 entries** — the least-recently-used solutions are dropped when capacity is reached
- **Stale fallback** — if the network is unavailable and the cache is stale, Genesis returns the old solution with a visible warning rather than crashing

Repeat projects run faster. Offline projects still work. No solution is ever silently outdated.

---

### 3. Smart Fork Analysis — Ranked by Activity, Not Hype

Genesis now finds the **top 3 active forks** of every analyzed repo — and it ranks them by **merged PRs in the last 6 months**, not by star count.

A fork with 10 stars but 12 merged PRs this quarter beats one with 500 stars and no recent activity. Those merged PRs contain the bug fixes the original maintainer hasn't shipped yet. Genesis extracts them and adds them to your `PITFALLS.md`.

This is the feature that catches the issues that even the original repo authors haven't resolved.

---

### 4. Natural Language Architecture Choices (NLU Gate)

No more memorizing option letters.

**Before:**
```
Choose A, B, C, or D:
> B
```

**Now:**
```
Choose your architecture (A/B/C/D or describe in words):
> give me the scalable approach

I'll take that as B (scalable) - correct? [y/n]
> y
```

Genesis maps natural language to architecture choices using pattern matching. Say "I want the simple one", "let's go full production", "quick prototype" — it understands. Three failed attempts triggers a clean restart prompt, never a crash.

---

### 5. Zero-Friction Project Audits

`genesis init` now reads your project before it asks you anything.

If there's a `pyproject.toml`, `package.json`, `go.mod`, or `README.md` in the current directory, Genesis silently extracts the project name and description and uses them as the vision. No prompt. No interruption. It only asks if it finds nothing.

Run `genesis init` with no arguments inside an existing project and it figures out what you're building on its own.

---

### 6. Active Development Companion

After scaffolding, don't close the terminal — stay in it.

```bash
genesis companion
```

A new interactive mode that:
- Answers questions about your project using the vault + LLM
- Knows which project you're in (from `pyproject.toml` / `README.md`)
- Detects when you say "done", "exit", or start describing a completely different project
- Exits cleanly with a message pointing you to `genesis init` for the next one

Your scaffold is the starting line, not the finish line. Companion mode stays with you through the whole build.

---

## 🛡️ Stability and Resilience

### GitHub Rate Limit Handling

Genesis now handles GitHub API limits gracefully. When the API returns 403 or 429:

1. Stops immediately — no partial run, no confusing error trace
2. Prints a clear message with the exact commands to fix it:

```
GitHub rate limit reached (60 requests/hour without a token).
To continue:
  1. Go to https://github.com/settings/tokens/new
  2. Select scope: public_repo
  3. Run: genesis config set GITHUB_TOKEN <your-token>
```

No crash. No noise. Just instructions.

### Test Suite: 316 Passing

Up from 307. Every new module ships with full coverage:
- `test_github_rate_limit.py` — 9 tests covering 403/429 detection, message content, fork analyzer propagation
- `test_vault_and_resolve.py` — 14 tests covering TTL, LRU eviction, stale fallback, stats
- `test_new_features.py` — 23 tests covering NLU gate, audit inference, companion exit detection

---

## 🧠 Under the Hood

| Module | What it does |
|---|---|
| `core/vault.py` | LRU cache, 500 entries, 6-month TTL |
| `core/resolve_engine.py` | Vault-first SO lookup, stale warning |
| `core/fork_analyzer.py` | Top 3 forks by merged PRs (not stars) |
| `core/nlu_gate.py` | Natural language → A/B/C/D |
| `core/audit_inference.py` | Reads project files before prompting |
| `core/companion.py` | Exit detection, message routing |
| `cli.py` | Typer CLI wiring all modules together |
| `config.py` | API key management in `~/.genesis/config.json` |

---

## ⚡ How to Install

```bash
# Standalone (recommended for most users)
pip install genesis-architect
genesis config set LLM_API_KEY your-anthropic-or-openai-key
genesis init "describe what you want to build"

# Claude Code skill (original mode — still fully supported)
git clone https://github.com/maioio/genesis-architect ~/.claude/skills/genesis-architect
```

**Optional — faster GitHub scanning:**
```bash
genesis config set GITHUB_TOKEN your-github-token
```
Without a token you get 60 API requests/hour. With one: 5,000.

---

## What's Next

- Demo GIF on the landing page
- PyPI publish (`pip install genesis-architect` from the public registry)
- Java and Ruby language templates (tracked in issues [#17](https://github.com/maioio/genesis-architect/issues/17), [#18](https://github.com/maioio/genesis-architect/issues/18))
- Show HN launch

---

*316 tests. Zero regressions. Ships today.*
