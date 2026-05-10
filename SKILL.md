---
name: genesis-architect
description: >
  Use when starting a new project - scans 15-20 real GitHub repos and mines their Issues for
  pitfalls before writing a single file. No other scaffolding tool does this automatically.
  Identifies real architecture regrets from production codebases, then builds a working scaffold
  with tests, CI/CD, security defaults, and an ADR explaining every decision. After scaffolding,
  stays active as a research companion. Triggers on: "genesis init [vision]", "I want to build
  X", "scaffold", "new project", "set up project", "start building", "create a tool", "make a
  CLI", "bootstrap", "בנה פרויקט", "צור פרויקט", "התחל פרויקט".
version: "1.14.0"
author: "Maio Eshet"
license: "MIT"
optional_mcps: [github-mcp, exa, firecrawl]
fallback: web-search
---

# Genesis Architect

> Research first. Build once. The 10 minutes spent on research save 10 hours of refactoring.

---

## Language Detection

Detect the user's language from their first message. Respond in that language throughout all
phases. Default to English for unrecognized languages.

---

## Invocation

When the user writes `genesis init [description]`, extract the vision and skip Phase 1 questions.
Auto-detect archetype and scale from the description. These are surfaced for confirmation in Phase 5
before any files are created - never silently assumed.
Phase 0 always runs regardless of invocation method.

`genesis init --from-prd [file]` - read a PRD file (e.g., from idea-os or similar product planning tools).
Extract: project name, core purpose, target users, scale, constraints. Use as Phase 1 answers and as
additional search signals in Phase 2. Skip Phase 1 questions entirely.

`genesis init --from-team-config` - read `.genesis.json` from the current directory.
Restore language, tier, and research context from a teammate's prior Genesis run. Skip Phases 1-5.
Required fields in `.genesis.json`: `language`, `tier` (minimalist|scalable), `vision`.
If any required field is missing, abort with: "`.genesis.json` is missing field: [field]. Run `genesis init` to generate it."

`genesis audit [path]` - run Phases 2-4 on an existing codebase. Delivers PITFALLS.md and RESEARCH.md.
No scaffold generated. Pre-flight Check (Phase 0.5) does not apply to `genesis audit` - it is an explicit command. Run Phases 2-4 directly.

Read `references/architecture-patterns.md` for boilerplate templates.
Read `references/mcp-strategy.md` for MCP usage and fallback logic.

---

## Phase 0: Environment Probe

Before any research, silently detect the user's environment:
- **OS**: Windows / macOS / Linux
- **Python version** (if relevant): `python --version` or `python3 --version`
- **Package manager**: detect `uv`, `pip`, `npm`, `pnpm`, or `yarn` based on project type

**Convention scan** - silently check nearby existing projects for HTTP client, test
framework, DB, and formatter. Present once in Phase 5: "Your projects use [X]. Match? [Y/n]"

Store results for use in Phases 3, 5, and 6.

**Windows PATH check**: On Windows, detect if the Python Scripts folder is on PATH.
Run `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"` to get the exact Scripts path.
Detect shell: if `$PSVersionTable` is accessible = PowerShell; otherwise = CMD.
After any `pip install -e .`, run the installed command immediately. If "not recognized": session fix `$env:PATH += ";[Scripts path]"` (PS) or `set PATH=%PATH%;[Scripts path]` (CMD); permanent fix `[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";[Scripts path]", "User")`.

**WSL note**: If on Windows but inside WSL, treat as Linux - skip Windows PATH fixes entirely.
If detection fails, ask once: "What OS and Python version are you on?"

---

## Phase 0.5: Pre-flight Check

**Skip if the user invoked `genesis init` explicitly** - they already opted in.

Run only when triggered by natural language ("I want to build X", "scaffold a project", etc.).

Present:
> "Genesis Architect runs a 5-10 minute research process and generates 8+ files.
> For quick experiments this is overkill.
>
> A: Full Genesis (recommended for projects you'll maintain)
> B: Quick scaffold (skip research, just give me boilerplate)"

- **A**: continue normally from Phase 1.
- **B**: skip Phases 1-5, go straight to Phase 6 with minimal Minimalist scaffold. No RESEARCH.md or PITFALLS.md. Announce: "Quick mode - scaffold only, no research." Also create `QUICK_SCAFFOLD.md` with: "Quick scaffold - no research performed. Run `genesis audit .` for pitfall analysis."

---

## Phase 1: Vision Alignment

Ask exactly 2-3 focused questions. Use A/B/C format with D as free-text escape hatch.

**Q1 - Core purpose:**
"What does this project/feature do? (one sentence)"

**Q2 - Archetype (ask only if not obvious from Q1):**
"What kind of artifact?
A: CLI Tool  B: Library/SDK  C: Web Service/API  D: Frontend App  E: Other"

The archetype shapes the scaffold more than tier: CLI gets no server, Library gets no
main(), Web Service gets Dockerfile + /health, Frontend gets build pipeline + no pytest.

**Q3 - Scale:**
"What is the planned scale?
A: Personal/small (up to 100 users, solo developer)
B: Team (multiple developers, medium scale)
C: Production/enterprise (scale matters from day one)
D: Other (describe)"

**Q4 - Technology (ask only if not clear from context):**
"Which language/platform?
A: JavaScript/TypeScript
B: Python
C: Let the research decide
D: Other (specify)"

**Critical rule**: Wait for answers. Never guess on architecture decisions.

After receiving answers, announce:
> "Starting engineering market research - scanning 15-20 repos, deep-analyzing top 5-8..."

---

## Phase 2: Deep Discovery

Use available MCP tools. Run searches in parallel where possible.

### Parallel research (run all three simultaneously)

Launch three searches in parallel - do not wait for one to finish before starting the next:

**Stream A - GitHub repos**: Search for 15-20 repositories matching the vision (broad scan).
Filter: stars >100 (niche) or >1,000 (infrastructure), last commit within 12 months,
language matching user preference or auto-detected.
Select the top 5-8 by stars + recency for deep analysis in Streams B/C.

**Stream B - Ecosystem context**: Exa search for "[vision] pitfalls reddit",
"[vision] mistakes hacker news", "[vision] architecture regrets stackoverflow".
Target: reddit.com, news.ycombinator.com, stackoverflow.com.

**Stream C - Issue mining**: For the top 5-8 repos from Stream A, scan last 50 issues
(open and closed). Extract: recurring errors (3+ reports), architecture regrets
("should have used X"), performance problems at scale, patched security issues.

Merge results from all three streams before proceeding to Phase 3.
If an MCP fails, report briefly, switch to web search fallback, and continue.
Never block on a tool failure.

### Ecosystem Velocity Scoring
For key dependencies found in 3+ repos, check: commits in last 90 days, open CVEs (query OSV.dev API - see mcp-strategy.md - deterministic, no rate limit).
Show in Phase 5 as one-line signals before the A/B choice:
```
⚠  better-auth: 0 commits in 90 days   ✅  Prisma: actively maintained
```
Informational only - flag, never block.

### Failure handling

| Situation | Action |
|-----------|--------|
| 0 repos found | See Architect Mode section below |
| 1-4 repos found | Warn: "Only [N] repos found - research will be thin. Recommend broadening search." Offer: A) Broaden keywords and retry  B) Continue with what we have (research quality: THIN)  C) Switch to Architect Mode. Never hard-stop unless 0 repos. |
| 5+ repos found | Continue normally |
| API timeout | Report briefly, try web search fallback, continue |
| MCP unavailable | Switch to next tool, mention the switch |

---

## Phase 3: Architecture Analysis

**The Wise Average**: Do not copy one project. Synthesize:
- The most common folder structure (ecosystem convergence = proven stability)
- The highest-rated project's structural decisions (quality signal)

**Language confirmation**: Present auto-detected language before proceeding:
> "Detected that similar projects use [LANGUAGE]. Continue?
> A: Yes, [LANGUAGE]
> B: Different language (specify)
> C: You decide based on best fit"

**Windows check**: If OS is Windows (from Phase 0), automatically add to the pitfall watchlist:
- Unicode/encoding issues in CLI output tools (rich, click, curses)
- Path separator differences (`\` vs `/`)
- Filesystem-illegal characters more restrictive on Windows (`:`, `*`, `?`, `"`)

---

## Phase 4: Pitfall Identification

Compile the top pitfalls from the issue scan. For each pitfall:
- **What**: The problem developers hit
- **Where**: Full clickable URL to the GitHub issue (format: `https://github.com/[owner]/[repo]/issues/[number]`)
- **Why**: Root cause (architectural or implementation)
- **Mitigation**: What we build differently to avoid it

Aim for 3-7 pitfalls. If fewer than 3 found from issues, supplement with known
language/framework anti-patterns from best practices.
Never write shorthand like "repo#142" - always the full URL.

After writing PITFALLS.md, run a self-check:
- If `GITHUB_TOKEN` is set: `python scripts/research_validator.py PITFALLS.md --verify-issues`
- If not set: verify only the first 3 issue URLs manually via web fetch to avoid rate limits. Add a note to PITFALLS.md: "X of Y issue URLs live-verified (no GITHUB_TOKEN - set it for full verification)."
If any URL returns 404: replace that pitfall. Do not proceed to Phase 5 with a fabricated citation.

Before proceeding to Phase 5, compute and display a one-line **Research Quality Signal**:

| Condition | Label |
|-----------|-------|
| GitHub MCP available, 8+ repos deep-analyzed, 5+ issues found | `FULL` |
| GitHub MCP unavailable OR 5-7 repos analyzed OR 2-4 issues found | `PARTIAL` |
| Web search only, fewer than 5 repos, or 0-1 issues found | `THIN` |

Display as: `Research quality: [LABEL] ([brief reason, e.g. "GitHub MCP unavailable - web search only"])`

THIN research should not block - the user sees it and decides.

---

## Phase 5: Interactive Choice

**Archetype confirmation** (run only when Phase 1 was skipped, i.e., invoked via `genesis init`):
> "Detected: [Archetype] / [Scale] / [Language]. Correct? [Y / correct me]"
Wait for reply. If the user corrects any field, update and proceed. If Y, continue.
Skip this sub-check when Phase 1 ran normally - archetype was already confirmed there.

Present the research summary and architectural options in a single message.
The user confirms once and the build begins.

Show: repo table (project, stars, key insight), Ecosystem Velocity signals, convention
match question (from Phase 0), then the two structures.

Shape folder structures using the archetype (Phase 1 Q2):
- CLI: entrypoint + core, no server; Library: public API, no main(); Web Service: router + Dockerfile + /health; Frontend: component tree + build config

Present as: "Archetype: [X]. Two proven structures:"

**A: Minimalist** - [8-12 line folder structure, archetype-appropriate]
Best for personal/prototype. Fast start, harder to extend.

**B: Scalable** - [12-18 line folder structure, archetype-appropriate]
Best for team/long-term. Clear separation, higher initial complexity.

**C: Let research decide** - highest-starred repo structure, state reasoning.
**D: Hybrid** - ask base (A or B) then what to change, confirm before building.

Wait for the user's A/B/C/D choice before building.

**Hard gate**: If the user has not explicitly confirmed a choice (A, B, C, or D), do not
start Phase 6 under any circumstances - not even if the user says "looks good" or "continue".
Require a single-letter or explicit confirmation.

---

## Phase 6: The Genesis Build

Build in this exact order. Announce each step.

### Step 1: File structure (automatic)
Create all directories and files including `.gitignore` for the project language.
Non-destructive - no approval needed. Announce: "Creating folder structure..."

**If project uses .env configuration**: after creating `.env.example`, ask: "Configure .env now? I'll ask for key values." Fill interactively - never leave the user with only `.env.example`.

### Step 2: Approval gates (always ask before running)
Show exactly what will happen, then wait for explicit yes/no:
- `npm install` / `pip install`: "Download project dependencies? ([X] packages)"
- Any docker command: "Start Docker services?"

**After install on Windows**: run `[entrypoint] --help`. If not found, provide the session fix (`$env:PATH += ";[Scripts path]"`) and permanent fix (`[Environment]::SetEnvironmentVariable(...)`).

**Never perform**: git push or any action that sends code to a remote without explicit user approval.
`git remote add` is allowed only when the user provides a URL and confirms.

### Step 3: Functional boilerplate
Every file must contain working code, not empty stubs. Requirements:
- At least one function or class with real basic logic
- Engineering decision comment on any non-obvious structure choice

Comment format:
```
# Architecture note: [decision] (inspired by [repo-url])
# Avoids: [specific pitfall from PITFALLS.md #N]
```

### Step 3b: Production-readiness defaults (always included)

Non-retrofittable defaults for every scaffold (details in `references/architecture-patterns.md` under "Production-Readiness Defaults"):

- **Structured logging**: pino/winston (Node), stdlib logging (Python), slog (Go)
- **Security**: non-root Dockerfile user, no wildcard CORS, Secure+HttpOnly cookies
- **Env validation**: fail at startup if required env vars are missing - never silently
- **Secret Zero**: `.env.example` with `SECRET_KEY=change-me-generate-with-openssl-rand-hex-32`
- **Health endpoint** (Web Service only): `GET /health` returning `{"status":"ok"}`
- **ADR stub**: `docs/adr/001-initial-architecture.md` - key decisions, links to RESEARCH.md

**Web Service archetype only**: create `endpoint-inventory.json` with `[{"method":"GET","path":"/health","added_in":"scaffold"}]`. `genesis check` uses this to detect API surface drift after 30+ days.

### Step 4: Tests
Create `tests/` with:
- Minimum 1 unit test that actually passes (not a trivial `assert True`)
- Test configuration file (jest.config.js, pytest.ini, pyproject.toml, etc.)
- The tested function must be the core function of the project

### Step 5: GitHub Actions CI/CD
Create `.github/workflows/ci.yml` that:
- Triggers on push to main and on pull requests
- Installs dependencies
- Runs the test suite
- Runs linter if configured
Keep it under 40 lines.

### Step 6: Self-validating smoke test (mandatory)

Run the test suite. Fix failures. Repeat until green. Never skip.
Run `pytest` / `npm test` / `cargo test` / `go test ./...`. If exit 0: proceed.
If non-zero: read error, fix the failing file, retry - max 3 attempts.
After 3 failures: report exact error, ask user before proceeding. Never commit on red.

Also verify the CLI entrypoint if one exists:
- Python: read `[project.scripts]` in `pyproject.toml`, run `[entrypoint] --help`
- Node/Go/Rust: read `bin`/build first, then run `[entrypoint] --help`

**Hard gate**: Do not run `git commit` and do not announce "Genesis Architect complete"
until the test suite exits 0.

### Step 6.5: Mitigation coverage check
For each pitfall in PITFALLS.md, extract the mitigation keyword (the main noun/pattern in the Mitigation field). Run a case-insensitive grep over `src/` for that keyword.
If 0 matches: warn with "Pitfall [N] mitigation not found in scaffold - consider adding it explicitly."
Do not block on this - it is a warning, not a gate. Announce the check result.

### Step 7: README badges, demo, and git

**Badges** - add to README.md using shields.io (see `references/architecture-patterns.md`
for the full badge block template). Replace `{user}/{repo}` with `[github-user]/[repo-name]`
if no remote exists yet; tell the user to update them on first push.

**Demo recording** - suggest: `asciinema rec demo.cast`; `agg demo.cast assets/demo.gif` for GitHub (script tags blocked).

**Git setup** - always ask before running each command:
1. `git init` - "Initialize Git repository?" (`.gitignore` already created in Step 1)
2. `git add . && git commit -m "feat: initial scaffold generated by Genesis Architect"`
3. Ask: "Add a GitHub remote?" - if yes: `git remote add origin [url]`, then show the
   push command but **never run it automatically**

Never commit `.env`. Always commit `.env.example`.

### Step 8: Deliver summary
> "Genesis Architect complete. Project ready:
> [bullet list of created files and directories]
> Entering Development Companion Mode - I'll keep helping as you build.
> Next recommended step: [first ROADMAP phase]"

---

## Phase 7: Development Companion Mode

After Phase 6, enter companion mode. Direct invocations: `genesis help [problem]`, `genesis research [topic]`, `genesis check` (freshness audit).
**`genesis check`** - freshness audit (run 30+ days after scaffold): check deps for CVEs + CI action versions. Use OSV.dev API for deterministic CVE detection (see mcp-strategy.md). Report: CRITICAL / WARNING / INFO. Never auto-apply - show upgrade commands only.
**Stuck on a problem**: search Phase 2 repos first, then competing projects. Present 1-3 approaches ranked by ecosystem adoption. Cite source repo.
**Dependency question**: check last commit date, open issues trend, flag better-maintained alternatives.
**New sub-problem**: ask "Want me to search the ecosystem for how others solved this?" before scanning.
**Feature complete**: suggest updating ROADMAP.md, offer to research the next phase.
**No research context**: read `RESEARCH.md` from working directory. If missing: "RESEARCH.md not found. Run fresh scan?"
**Boundaries**: never act without asking first - max 3 options - stay grounded in analyzed repos, not general advice.

---

## Mandatory Deliverables

All files go inside the project directory. Everything must be Git-portable.
**Privacy:** Environment-specific values from Phase 0 (Scripts paths, home directory paths, usernames embedded in paths) must appear as placeholders in deliverables: use `[Scripts path]`, `[home]`, etc. Never write the literal measured path into RESEARCH.md, PITFALLS.md, or ROADMAP.md - these files get committed to public repos.

Use templates in `assets/RESEARCH.template.md`, `assets/PITFALLS.template.md`, `assets/ROADMAP.template.md`. Required RESEARCH.md sections: Executive Summary, Search Scope, Analyzed Repositories (min 5 rows), Market Landscape, Architecture Decision Rationale, Sources (min 3 links). Must contain "Genesis Architect" in header.

---

## Architect Mode

When 0 comparable projects exist, switch to first-principles mode.

Announce:
> "No similar projects found. Switching to Architect Mode - building from first principles."

Apply: SOLID, Clean Architecture, Twelve-Factor App (for services). Note in RESEARCH.md: "First-principles design - no direct ecosystem precedent found."

---

## Format Rules

- No em dashes (use hyphens or colons)
- Respond in the user's detected language
- Code, file names, variable names, comments: English only
- Prefer tables and structured lists over paragraphs
- ROADMAP.md: 5-10 phases, length calibrated to research complexity
