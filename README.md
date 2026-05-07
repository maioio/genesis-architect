# Genesis Architect

**Research first. Build once.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-orange.svg)](https://github.com/anthropics/claude-code)

A Claude Code skill that scans 15-20 real GitHub repos, extracts pitfalls from actual Issues,
and builds a battle-tested scaffold — before writing a single line of code.

After scaffolding, enters **Development Companion Mode**: keeps searching and suggesting as you build.

---

## Install

```bash
git clone https://github.com/maioio/genesis-architect ~/.claude/skills/genesis-architect
```

---

## Usage

**Explicit invocation:**
```
genesis init a REST API in TypeScript
genesis init a Chrome extension that does X
genesis init a Python CLI for batch image processing
```

**Natural triggers:**
```
I want to build a Telegram bot
scaffold a new project for web scraping
start building a VS Code extension
```

---

## What you get

Every project receives:

| File | Contents |
|------|----------|
| `RESEARCH.md` | Market analysis of 15-20 real repos, sources linked |
| `PITFALLS.md` | 3-7 real pitfalls from GitHub Issues with mitigations |
| `ROADMAP.md` | 5-10 phase development roadmap |
| `src/` | Functional boilerplate (not empty stubs) |
| `tests/` | Passing unit tests for core logic |
| `.github/workflows/ci.yml` | GitHub Actions CI/CD |

---

## The 7 phases

| Phase | What happens |
|-------|-------------|
| 1. Vision Alignment | 2-3 focused questions about scope and scale |
| 2. Deep Discovery | Scans 15-20 repos, reads last 50 issues each |
| 3. Architecture Analysis | Synthesizes the "wise average" across the ecosystem |
| 4. Pitfall Identification | Extracts recurring failures with root causes |
| 5. Interactive Choice | Minimalist vs. Scalable architecture options |
| 6. Genesis Build | Creates scaffold with tests and CI/CD |
| 7. Development Companion | Keeps searching and suggesting as you build |

---

## Development Companion Mode

After scaffolding, Genesis Architect stays active. Tell it what you're working on:

```
genesis help I need to add authentication
genesis research rate limiting patterns
```

It searches the repos it already analyzed and returns grounded suggestions — not generic advice.

---

## Languages supported

Auto-detected from research. Built-in templates for:
- TypeScript / JavaScript
- Python
- Go
- Rust

---

## MCP tool chain

| Priority | Tool | Purpose |
|----------|------|---------|
| 1 | GitHub MCP | Repo analysis, issue scanning |
| 2 | Exa MCP | Reddit, HN, StackOverflow |
| 3 | Firecrawl MCP | Targeted page scraping |
| 4 | Web search | Fallback |

All tools optional — skill degrades gracefully.

---

## Project structure

```
genesis-architect/
├── SKILL.md                        # Skill definition (344 lines)
├── plugin.json                     # Manifest for skill marketplaces
├── scripts/
│   ├── scaffold_generator.py       # Creates project structure
│   ├── research_validator.py       # Validates RESEARCH.md completeness
│   └── eval_runner.py              # Measures trigger rate
├── evals/
│   ├── test_queries.json           # 31 trigger/no-trigger test cases
│   └── README.md                   # How to run evals
├── examples/
│   └── typescript-cli/             # Real output example
│       ├── RESEARCH.md
│       ├── PITFALLS.md
│       └── ROADMAP.md
├── assets/
│   ├── RESEARCH.template.md
│   ├── PITFALLS.template.md
│   └── ROADMAP.template.md
├── references/
│   ├── architecture-patterns.md    # Boilerplate per language/tier
│   └── mcp-strategy.md             # MCP usage and fallback logic
└── CLAUDE.md                       # Claude Code project instructions
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) to add language templates or improve the workflow.

## License

[MIT](LICENSE) - Maio Eshet
