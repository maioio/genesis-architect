---
name: genesis-architect
description: >
  Use when the user is about to start a new project and wants to avoid reinventing the wheel,
  hit known pitfalls, or commit to an architecture prematurely. Scans 15-20 real GitHub repos,
  extracts pitfalls from actual Issues, then builds a working scaffold with tests and CI/CD -
  before writing a single line of product code. After scaffolding, stays active as a research
  companion. Triggers on: "genesis init [vision]", "I want to build X", "scaffold", "new
  project", "set up project", "start building", "create a tool", "make a CLI", "bootstrap",
  "בנה פרויקט", "צור פרויקט", "התחל פרויקט".
version: "1.6.0"
author: "Maio Eshet"
license: "MIT"
---

# Genesis Architect

> Research first. Build once.

The 10 minutes spent on research save 10 hours of refactoring.

---

## Language Detection

Detect the user's language from their first message. Respond in that language throughout all
phases. Default to English for unrecognized languages.

---

## Invocation

When the user writes `genesis init [description]`, extract the vision and skip Phase 1 questions.
Phase 0 always runs regardless of invocation method.

`genesis init --from-prd [file]` - read a PRD file (e.g., from idea-os or similar product planning tools).
Extract: project name, core purpose, target users, scale, constraints. Use as Phase 1 answers and as
additional search signals in Phase 2. Skip Phase 1 questions entirely.

`genesis init --from-team-config` - read `.genesis.json` from the current directory.
Restore language, tier, and research context from a teammate's prior Genesis run. Skip Phases 1-5.

`genesis audit [path]` - run Phases 2-4 on an existing codebase. Delivers PITFALLS.md and RESEARCH.md.
No scaffold generated.

Read `references/architecture-patterns.md` for boilerplate templates.
Read `references/mcp-strategy.md` for MCP usage and fallback logic.

---

## Phase 0: Environment Probe

Before any research, silently detect the user's environment:
- **OS**: Windows / macOS / Linux
- **Python version** (if relevant): `python --version` or `python3 --version`
- **Package manager**: detect `uv`, `pip`, `npm`, `pnpm`, or `yarn` based on project type

Store these as context. Reference them in:
- Phase 3: flag OS-specific pitfalls automatically
- Phase 6: choose correct build backend and install commands

**Windows PATH check**: On Windows, detect if the Python Scripts folder is on PATH.
Run `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"` to get the exact Scripts path.
Detect shell: if `$PSVersionTable` is accessible = PowerShell; otherwise = CMD.
After any `pip install -e .`, run the installed command immediately to verify it works.
If it fails with "not recognized", provide both:
- Session fix: `$env:PATH += ";[Scripts path]"` (PowerShell) or `set PATH=%PATH%;[Scripts path]` (CMD)
- Permanent fix: `[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";[Scripts path]", "User")`

If detection fails, ask once: "What OS and Python version are you on?"

---

## Phase 1: Vision Alignment

Ask exactly 2-3 focused questions. Use A/B/C format with D as free-text escape hatch.

**Q1 - Core purpose:**
"What does this project/feature do? (one sentence)"

**Q2 - Archetype (ask only if not obvious from Q1):**
"What kind of artifact are you building?
A: CLI Tool - runs in a terminal, takes flags, exits
B: Library/SDK - imported by other code, has a public API
C: Web Service/API - HTTP server, handles requests
D: Frontend App - browser UI (React, Next.js, SvelteKit, etc.)
E: Other (describe)"

The archetype determines the scaffold shape more than the tier does:
- CLI: entrypoint + argparse/click/cobra, no server
- Library: public API surface, docs, no main()
- Web Service: router, healthcheck, Dockerfile, no bin
- Frontend: component tree, routing, build pipeline, no pytest

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
> "Starting engineering market research - scanning 15-20 projects..."

---

## Phase 2: Deep Discovery

Use available MCP tools. Run searches in parallel where possible.

### Tool priority
1. GitHub MCP - deep repo analysis, code structure, issue scanning
2. Exa MCP - broad web search (Reddit, StackOverflow, Hacker News, dev blogs)
3. Firecrawl MCP - scrape specific pages when needed
4. Web search - fallback if MCPs unavailable

If an MCP fails, report briefly and switch to the next option.
Never block the workflow on a tool failure.

### Search targets

Find 15-20 repositories matching the user's vision. Filter by:
- Stars: minimum 100 for niche projects, minimum 1,000 for general infrastructure
- Activity: last commit within 12 months
- Language: match user preference, or auto-detect from top results

### Issue scanning
For each of the top 3-5 repositories, scan the last 50 issues (open and closed). Extract:
- Recurring errors (same problem reported 3+ times)
- Architecture regrets ("we should have used X instead")
- Performance issues that emerged at scale
- Security vulnerabilities that were patched

### Failure handling

| Situation | Action |
|-----------|--------|
| 0 repos found | See Architect Mode section below |
| 1-4 repos found | **Hard stop.** Report count, offer: A) broaden keywords B) switch to Architect Mode. Do not continue to Phase 3 with fewer than 5 repos. |
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
- **Where**: Link to the GitHub issue or discussion
- **Why**: Root cause (architectural or implementation)
- **Mitigation**: What we build differently to avoid it

Aim for 3-7 pitfalls. If fewer than 3 found from issues, supplement with known
language/framework anti-patterns from best practices.

---

## Phase 5: Interactive Choice

Present the research summary and architectural options in a single message.
The user confirms once and the build begins.

Use the archetype from Phase 1 Q2 to shape the folder structures shown. Examples:

- CLI: `src/cli.py` + `src/core.py`, entrypoint in `pyproject.toml [project.scripts]`
- Library: `src/[name]/__init__.py` with public API, no `main()`, no CLI entrypoint
- Web Service: `src/app.py` + `src/routes/`, `Dockerfile`, `healthcheck` route
- Frontend: `src/app/`, `src/components/`, build config, no `pytest`

> "Finished scanning the market. Found [N] relevant projects:
>
> | Project | Stars | Key Insight |
> |---------|-------|-------------|
> | [repo 1] | [N] | [one sentence] |
>
> Archetype detected: **[CLI Tool / Library / Web Service / Frontend App]**
> Based on the research, two proven structures for this archetype:
>
> **A: Minimalist**
> [Show concrete folder structure - 8-12 lines, archetype-appropriate]
> Best for: personal projects, prototypes, internal tools
> Advantage: fast to understand and develop
> Tradeoff: harder to extend later
>
> **B: Scalable**
> [Show concrete folder structure - 12-18 lines, archetype-appropriate]
> Best for: team projects, long-term products
> Advantage: clear separation of concerns, easy to extend
> Tradeoff: higher initial complexity
>
> **C: Let research decide** - I pick the structure used by the highest-starred repos
> **D: Hybrid** - describe what you want to change

If user picks D: ask "Which base (A or B) do you prefer? What would you change?"
Present the modified structure and confirm before building.
If user picks C on language: choose the language used by the highest-starred repos. State the reasoning.

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

**If project uses .env configuration**: after creating `.env.example`, ask:
"Do you want to configure .env now? I'll ask for the key values."
Fill `.env` interactively - never leave the user with only `.env.example`.

### Step 2: Approval gates (always ask before running)
Show exactly what will happen, then wait for explicit yes/no:
- `npm install` / `pip install`: "Download project dependencies? ([X] packages)"
- Any docker command: "Start Docker services?"

**After install on Windows**: immediately run `[entrypoint] --version` or `[entrypoint] --help`.
If the command is not found, provide the PATH fix:
`$env:PATH += ";[Python Scripts path]"` for the session, and
`[Environment]::SetEnvironmentVariable("PATH", ...)` for permanent fix.

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

```
1. Run: pytest / npm test / cargo test / go test ./...
2. If exit code 0: proceed to Step 7
3. If exit code non-zero:
   a. Read the error output
   b. Fix the specific failing file (imports, missing dep, syntax)
   c. Run again - max 3 attempts
   d. If still failing after 3 attempts: report exact error, ask user for input
      before proceeding. Do NOT continue to git commit on a red scaffold.
```

Also verify the CLI entrypoint if one exists:
- Python: read `[project.scripts]` in `pyproject.toml`, run `[entrypoint] --help`
- Node: read `bin` in `package.json`, run `node [entrypoint] --help`
- Go/Rust: build first, then run `./[binary] --help`

**Hard gate**: Do not run `git commit` and do not announce "Genesis Architect complete"
until the test suite exits 0.

### Step 7: README badges, demo, and git

**Badges** - add to README.md using shields.io (see `references/architecture-patterns.md`
for the full badge block template). Replace `{user}/{repo}` with `[github-user]/[repo-name]`
if no remote exists yet; tell the user to update them on first push.

**Demo recording** - suggest: `asciinema rec demo.cast`, upload for a shareable link,
`agg demo.cast assets/demo.gif` to convert for GitHub (script tags blocked).

**Git setup** - always ask before running each command:
1. `git init` - "Initialize Git repository?" (`.gitignore` already created in Step 1)
2. `git add . && git commit -m "feat: initial scaffold generated by Genesis Architect"`
3. Ask: "Add a GitHub remote?" - if yes: `git remote add origin [url]`, then show the
   push command but **never run it automatically**

Never commit `.env`. Always commit `.env.example`.

### Step 8: Deliver summary
> "Genesis Architect complete. Project ready:
> [bullet list of created files and directories]
>
> Entering Development Companion Mode - I'll keep helping as you build.
> Next recommended step: [first ROADMAP phase]"

---

## Phase 7: Development Companion Mode

After Phase 6, enter companion mode. Remain active as a research partner.

The user can invoke directly: `genesis help [problem]` or `genesis research [topic]`

**Stuck on a problem**: search the Phase 2 repos first, then competing projects. Present 1-3
approaches ranked by ecosystem adoption. Always cite the source repo.

**Dependency question**: check last commit date, open issues trend, flag better-maintained
alternatives.

**New sub-problem**: ask "Want me to search the ecosystem for how others solved this?" before
running a targeted scan.

**Feature complete**: suggest updating ROADMAP.md, offer to research the next phase.

**No research context**: read `RESEARCH.md` from the working directory. If missing, ask:
"Want me to run a targeted scan, or describe the problem?"

**Boundaries**: never act without asking first - max 3 options per result - stay grounded in
analyzed repos, not general advice.

---

## Mandatory Deliverables

All files go inside the project directory. Everything must be Git-portable.

**Privacy:** Environment-specific values from Phase 0 (Scripts paths, home directory paths, usernames embedded in paths) must appear as placeholders in deliverables: use `[Scripts path]`, `[home]`, etc. Never write the literal measured path into RESEARCH.md, PITFALLS.md, or ROADMAP.md - these files get committed to public repos.

Use the templates in `assets/RESEARCH.template.md`, `assets/PITFALLS.template.md`, and
`assets/ROADMAP.template.md`. These are the source of truth - the validator in
`scripts/research_validator.py` checks against them.

Required sections in RESEARCH.md: Executive Summary, Search Scope, Analyzed Repositories
(min 5 rows), Market Landscape, Architecture Decision Rationale, Sources (min 3 links).
Must contain the string "Genesis Architect" in the header.

---

## Architect Mode

When 0 comparable projects exist, switch to first-principles mode.

Announce:
> "No similar projects found. Switching to Architect Mode - building from first principles."

Apply: SOLID, Clean Architecture, Twelve-Factor App (for services).

Document in RESEARCH.md: "First-principles design - no direct ecosystem precedent found."

---

## Format Rules

- No em dashes (use hyphens or colons)
- Respond in the user's detected language
- Code, file names, variable names, comments: English only
- Prefer tables and structured lists over paragraphs
- ROADMAP.md: 5-10 phases, length calibrated to research complexity
