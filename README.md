# Genesis Architect

**Research first. Build once.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.9.0-blue.svg)](CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-orange.svg)](https://github.com/anthropics/claude-code)
[![CI](https://img.shields.io/github/actions/workflow/status/maioio/genesis-architect/ci.yml?branch=main&label=CI)](https://github.com/maioio/genesis-architect/actions)
[![GitHub Stars](https://img.shields.io/github/stars/maioio/genesis-architect?style=flat)](https://github.com/maioio/genesis-architect)

> Scans 15-20 real GitHub repos and mines their Issues for pitfalls — before writing a single file.
> No other scaffolding tool does this automatically.

---

## The problem with every other scaffolding tool

Every tool — create-t3-app, bolt.new, Copilot Workspace, Cookiecutter — assumes you already know what to build and how. They generate code from templates, not from evidence.

Genesis Architect treats scaffolding as a **research problem first**.

Before creating a single directory, it:
- Scans 15-20 real GitHub repos matching your vision
- Mines their Issues for recurring failures, architecture regrets, and security patches
- Synthesizes the "wise average" of what successful projects actually look like
- Builds a scaffold that avoids the mistakes others already made

---

## Demo

<p align="center"><img src="assets/demo.gif" alt="Genesis Architect demo" width="860" /></p>

> `genesis init a Python CLI for log analysis` - 18 repos scanned, scaffold complete in under 3 minutes.

---

## Real output — not fabricated

From an actual TypeScript CLI project:

- [`examples/typescript-cli/RESEARCH.md`](examples/typescript-cli/RESEARCH.md) - 17 repos analyzed, every source linked
- [`examples/typescript-cli/PITFALLS.md`](examples/typescript-cli/PITFALLS.md) - 4 real pitfalls from GitHub Issues, with mitigations built into the scaffold
- [`examples/typescript-cli/ROADMAP.md`](examples/typescript-cli/ROADMAP.md) - 5-phase development plan calibrated to what the research found

---

## Install

```bash
git clone https://github.com/maioio/genesis-architect ~/.claude/skills/genesis-architect
```

That's it. No build step, no dependencies.

---

## Usage

**Explicit:**
```
genesis init a REST API in TypeScript
genesis init a Python CLI for batch image processing
genesis init --from-prd PRD.md          # read a product spec
genesis init --from-team-config          # restore a teammate's research
genesis audit ./my-existing-project      # audit existing code, no scaffold
```

**Natural — just describe what you want to build:**
```
I want to build a Telegram bot
scaffold a new project for web scraping
start building a VS Code extension
I need to build a data pipeline from scratch
```

---

## What every project gets

| Deliverable | Contents |
|-------------|----------|
| `RESEARCH.md` | 15-20 repos analyzed, sources linked, ecosystem velocity signals |
| `PITFALLS.md` | 3-7 real pitfalls from GitHub Issues with root causes and mitigations |
| `ROADMAP.md` | 5-10 phase development plan calibrated to research complexity |
| `src/` | Functional boilerplate — not empty stubs |
| `tests/` | Passing unit tests for core logic |
| `.github/workflows/ci.yml` | Language-specific GitHub Actions CI/CD |
| `docs/adr/001-initial-architecture.md` | Every architectural decision explained with evidence |
| `.gitignore` | Language-appropriate, generated before first commit |

**Production-readiness defaults** included in every scaffold:
- Structured logging (pino/winston/slog) from the first line
- Non-root Dockerfile user
- Startup validation of required env vars — fails loudly if missing
- `GET /health` endpoint (Web Service archetype)
- No wildcard CORS, Secure+HttpOnly cookies

---

## The 9 phases

| Phase | What happens |
|-------|-------------|
| 0. Environment Probe | Detects OS, package manager, PATH; scans nearby projects for conventions |
| 1. Vision Alignment | Archetype (CLI/Library/API/Frontend) + scale + language — 3 focused questions |
| 2. Deep Discovery | **3 parallel streams**: GitHub repos + Exa ecosystem context + Issue mining |
| 3. Architecture Analysis | Synthesizes the "wise average" across analyzed repos |
| 4. Pitfall Identification | Extracts recurring failures with root causes |
| 5. Interactive Choice | Archetype-appropriate Minimalist vs. Scalable structures + ecosystem velocity signals |
| 6. Genesis Build | Scaffold + tests + CI/CD + production defaults + ADR + self-validating smoke test |
| 7. Development Companion | Stays active — `genesis help`, `genesis research`, `genesis check` |

**Hard gates that protect you:**
- Phase 2: fewer than 5 repos found = stops, offers broader search or Architect Mode
- Phase 5: requires explicit A/B/C/D before any files are created
- Phase 6: smoke test must pass before `git commit` — auto-fixes up to 3 times

---

## Development Companion Mode

After scaffolding, Genesis Architect stays active for the rest of your session:

```
genesis help I need to add rate limiting
genesis research authentication patterns
genesis check                            # freshness audit — CVEs, outdated deps, CI versions
```

Suggestions are grounded in the repos analyzed in Phase 2 — not generic advice.

In a new session, it reads `RESEARCH.md` from your project to restore context.

---

## Works at every level of MCP setup

| Setup | What you get |
|-------|-------------|
| No MCPs | Web search only — finds real repos, shallower issue analysis |
| GitHub MCP | Deep repo scan + real Issue extraction (recommended) |
| GitHub + Exa | Full parallel research: repos + Reddit/HN/StackOverflow context |

The skill never blocks on a missing tool — it reports what it's using and continues.

---

## Languages and archetypes

Languages auto-detected from research. Built-in templates for:
**TypeScript / JavaScript, Python, Go, Rust**

Archetypes — each shapes the scaffold differently:

| Archetype | What changes |
|-----------|-------------|
| CLI Tool | Entrypoint + argparse/click/cobra, no server |
| Library/SDK | Public API surface, no `main()`, no CLI |
| Web Service/API | Router + Dockerfile + `/health` endpoint |
| Frontend App | Component tree + build pipeline, no pytest |

---

## Project structure

```
genesis-architect/
├── SKILL.md                        # Skill definition (under 400 lines)
├── scripts/
│   ├── scaffold_generator.py       # Creates project structure
│   ├── research_validator.py       # Validates RESEARCH.md completeness
│   └── eval_runner.py              # Measures trigger rate
├── evals/
│   ├── test_queries.json           # 36 trigger/no-trigger test cases
│   └── README.md
├── examples/
│   └── typescript-cli/             # Real output — not fabricated
├── assets/
│   ├── RESEARCH.template.md
│   ├── PITFALLS.template.md
│   └── ROADMAP.template.md
├── references/
│   ├── architecture-patterns.md    # Boilerplate per language/tier + production defaults
│   └── mcp-strategy.md
└── .github/workflows/ci.yml        # CI for this repo: validator + evals + scaffold smoke test
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

New language templates, improved MCP strategies, and workflow refinements are welcome.

## License

[MIT](LICENSE) - Maio Eshet
