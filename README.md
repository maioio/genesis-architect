# Genesis Architect

A Claude skill for **strategic project scaffolding with pre-build market research**.

Before writing a single line of code, Genesis Architect scans GitHub and the web for 15–20 existing solutions, analyzes their architectures, identifies real pitfalls from GitHub Issues — then builds a battle-tested functional scaffold.

> The 10 minutes spent on research save 10 hours of refactoring.

---

## What it does

1. **Vision Alignment** — asks 2–3 focused questions to understand scope and scale
2. **Deep Discovery** — scans 15–20 GitHub repos, reads issues, extracts pitfalls
3. **Architecture Analysis** — synthesizes the "wise average" across the ecosystem
4. **Pitfall Identification** — documents 3–7 real issues with mitigations
5. **Interactive Choice** — presents Minimalist vs. Scalable architecture options
6. **Genesis Build** — creates a complete, working scaffold with tests and CI/CD

---

## Deliverables

Every project gets:

- `RESEARCH.md` — full market research report with analyzed repos and sources
- `PITFALLS.md` — real pitfalls from GitHub Issues with mitigations built into the scaffold
- `ROADMAP.md` — 5–10 phase development roadmap
- Functional boilerplate (not empty stubs) with engineering decision comments
- Passing unit tests
- GitHub Actions CI/CD workflow

---

## Installation

### In Claude Code (VS Code)

```bash
npx skills add https://github.com/maio-eshet/genesis-architect
```

### Manual

Copy the `genesis-architect/` folder into your `~/.claude/skills/` directory.

---

## Usage

### Explicit invocation

```
genesis init [vision description]
```

Example:
```
genesis init a Chrome extension that downloads Hebrew subtitles for anime
```

### Natural language triggers

Genesis Architect also activates on phrases like:
- "I want to build X"
- "scaffold a new project"
- "create a tool that..."
- "start building..."
- "set up a project for..."

---

## Tool support

Genesis Architect uses MCP tools in priority order:

| Priority | Tool | Purpose |
|----------|------|---------|
| 1 | GitHub MCP | Deep repo analysis, issue scanning |
| 2 | Exa MCP | Broad web search (Reddit, HN, StackOverflow) |
| 3 | Firecrawl MCP | Scrape specific pages |
| 4 | Web search | General fallback |

All tools are optional — the skill degrades gracefully if any are unavailable.

---

## File structure

```
genesis-architect/
├── SKILL.md                        # Main skill definition (305 lines)
└── references/
    ├── mcp-strategy.md             # MCP usage and fallback logic
    └── architecture-patterns.md   # Boilerplate templates per language
```

---

## Languages supported

- JavaScript / TypeScript (Minimalist and Scalable tiers)
- Python (Minimalist and Scalable tiers)
- Auto-detect from ecosystem research

---

## License

MIT
