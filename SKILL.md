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
---

<!--
Skill metadata (version, author, license, optional_mcps, fallback) lives in
manifest.json and plugin.json. Claude Code only reads `name` and `description`
from this frontmatter; extra keys are silently ignored, so they belong with
the rest of the package metadata, not here.
-->


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

`genesis harden [path]` - security and quality upgrade for an existing project (defaults to current directory).
Runs a gap scan and injects missing standards:
1. Check for: secret-scanning workflow, SAST workflow, quality-gate config, strict .gitignore
2. Inject any missing files using templates from references/security-templates.md
3. Scan src/ for common security gaps: missing input sanitization, hardcoded strings resembling secrets (regex: [A-Za-z0-9]{32,}), unsafe file opens without path validation
4. Output a status table: what was injected (auto) vs what needs manual action (tokens, org name)
Pre-flight Check (Phase 0.5) does not apply - this is an explicit command.

Read `references/architecture-patterns.md` for boilerplate templates.
Read `references/mcp-strategy.md` for MCP usage and fallback logic.

---

## Phase 0: Environment Probe

Run `python scripts/env_probe.py` and parse the JSON. Fields: `os`, `wsl`, `python_version`, `package_managers.{python,node}`, `windows_scripts_path`. Store the result for use in Phases 3, 5, and 6. If the script fails (e.g. Python missing), ask once: "What OS and Python version are you on?"

**Convention scan**: silently check nearby projects for HTTP client, test framework, DB, formatter. Present once in Phase 5: "Your projects use [X]. Match? [Y/n]"

**Windows PATH check**: when `os == "windows"` and `wsl == false`, use `windows_scripts_path` from the probe. Detect shell: if `$PSVersionTable` is accessible = PowerShell; otherwise = CMD.
After any `pip install -e .`, run the installed command immediately. If "not recognized": session fix `$env:PATH += ";[Scripts path]"` (PS) or `set PATH=%PATH%;[Scripts path]` (CMD); permanent fix `[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";[Scripts path]", "User")`.

**WSL note**: when `wsl == true`, treat as Linux - skip Windows PATH fixes entirely.

---

## Phase 0.5: Pre-flight Check

**Skip for any explicit command** (`genesis init`, `genesis audit`, `genesis harden`, `genesis init --from-prd`, `genesis init --from-team-config`) - the user already opted in.

Run only when triggered by natural language ("I want to build X", "scaffold a project", etc.).

Present:
> "Genesis Architect runs a 5-10 minute research process and generates 8+ files.
> For quick experiments this is overkill.
>
> A: Full Genesis (recommended for projects you'll maintain)
> B: Quick scaffold (skip research, just give me boilerplate)"

- **A**: continue normally from Phase 1.
- **B**: skip Phases 1-5, go straight to Phase 6 with minimal Minimalist scaffold. No RESEARCH.md or PITFALLS.md. Create `QUICK_SCAFFOLD.md`: "Quick scaffold - no research. Run `genesis audit .` for pitfall analysis."

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

After receiving answers, announce: "Starting research - scanning 15-20 repos, deep-analyzing top 5-8..."

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

**Stream C - Issue mining**: for top 5-8 repos from Stream A, scan up to 100 issues per repo. Rank by engagement density (comments + reactions). Prioritize: issues with 5+ comments or 10+ reactions, labels 'bug'/'regression'/'breaking-change'/'security', closed issues with 'fixed in X.Y.Z'. Surface top 10 per repo. Extract: recurring errors (3+ reports), architecture regrets, performance problems at scale, patched security issues.

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
| 0 repos found | Architect Mode: apply SOLID + Clean Architecture principles. Note in RESEARCH.md: "First-principles design - no direct ecosystem precedent found." |
| Active forks detected | Mandatory: analyze top 3 forks for bug fixes and patches. Incorporate improvements into output. |
| 1-2 repos found | Warn user. Offer: A) Broaden search and retry B) Continue with THIN quality C) Architect Mode. |
| 3-4 repos found | Warn (THIN quality). Require explicit user approval before Phase 3. |
| 5+ repos found | Continue normally |
| API timeout | Report briefly, try web search fallback, continue |
| MCP unavailable | Switch to next tool, mention the switch |

---

## Phase 3: Architecture Analysis

**The Wise Average**: do not copy one project. Synthesize: most common folder structure (ecosystem convergence) + highest-rated project's structural decisions (quality signal).

**Language confirmation**: Present auto-detected language before proceeding:
"Detected: [LANGUAGE]. Continue? A: Yes  B: Different language  C: You decide"

**Windows check**: If OS is Windows (from Phase 0), automatically add to the pitfall watchlist:
- Unicode/encoding issues in CLI output tools (rich, click, curses)
- Path separator differences (`\` vs `/`)
- Filesystem-illegal characters more restrictive on Windows (`:`, `*`, `?`, `"`)

---

## Phase 4: Pitfall Identification

Compile top pitfalls from the issue scan. For each pitfall: **What** (problem), **Where** (full URL `https://github.com/[owner]/[repo]/issues/[number]` - never shorthand like "repo#142"), **Why** (root cause), **Mitigation** (what we build differently). Aim for 3-7; if fewer than 3 from issues, supplement with known language/framework anti-patterns.

After writing PITFALLS.md, run self-check: if `GITHUB_TOKEN` set run `python scripts/research_validator.py PITFALLS.md --verify-issues`; otherwise verify first 3 URLs via web fetch and add note: "X of Y issue URLs live-verified (no GITHUB_TOKEN - set it for full verification)." If any URL returns 404: replace that pitfall. Do not proceed to Phase 5 with a fabricated citation.

Before proceeding to Phase 5, compute and display a one-line **Research Quality Signal**:

| Condition | Label |
|-----------|-------|
| GitHub MCP available, 8+ repos deep-analyzed, 5+ issues found | `FULL` |
| GitHub MCP unavailable OR 5-7 repos analyzed OR 2-4 issues found | `PARTIAL` |
| Web search only, fewer than 5 repos, or 0-1 issues found | `THIN` |

Display as: `Research quality: [LABEL] ([brief reason])`. THIN does not block - the user sees it and decides.

---

## Phase 5: Interactive Choice

**Archetype confirmation** (run only when Phase 1 was skipped via `genesis init`):
> "Detected: [Archetype] / [Scale] / [Language]. Correct? [Y / correct me]"
Wait for reply. If user corrects any field, update and proceed. Skip when Phase 1 ran normally.

Present research summary and architectural options in a single message. Show: repo table (project, stars, key insight), Ecosystem Velocity signals, convention match question (from Phase 0), then the two structures.

Shape folder structures using the archetype (Phase 1 Q2):
- CLI: entrypoint + core, no server; Library: public API, no main(); Web Service: router + Dockerfile + /health; Frontend: component tree + build config

Present as: "Archetype: [X]. Two proven structures:"

**A: Minimalist** - [8-12 line folder structure, archetype-appropriate]
Best for personal/prototype. Fast start, harder to extend.

**B: Scalable** - [12-18 line folder structure, archetype-appropriate]
Best for team/long-term. Clear separation, higher initial complexity.

**C: Let research decide** - highest-starred repo structure, state reasoning.
**D: Hybrid** - ask base (A or B) then what to change, confirm before building.

**Hard gate**: user must provide exactly A, B, C, or D (case-insensitive). If prose is provided, repeat: 'Please choose A, B, C, or D to proceed.' After 3 invalid attempts, ask: 'Start over from Phase 1? [Y/N]'. Do not start Phase 6 until confirmed.

---

## Phase 6: The Genesis Build

Build in this exact order. Announce each step.

### Step 1: File structure (automatic)
Create all directories and files including `.gitignore`. Non-destructive - no approval needed. Announce: "Creating folder structure..."
If project uses .env: after creating `.env.example`, ask: "Configure .env now? I'll ask for key values." Fill interactively - never leave the user with only `.env.example`.

### Step 2: Approval gates (always ask before running)
Show what will happen, wait for explicit yes/no: `npm install`/`pip install` ("Download project dependencies? ([X] packages)"), any docker command ("Start Docker services?").
After install on Windows: run `[entrypoint] --help`. If not found, provide session fix (`$env:PATH += ";[Scripts path]"`) and permanent fix (`[Environment]::SetEnvironmentVariable(...)`).
Never run `git push` or send code to a remote without explicit user approval. `git remote add` only when user provides URL and confirms.

### Step 3: Functional boilerplate
Every file must contain working code, not empty stubs. Requirements: at least one function or class with real basic logic, engineering decision comment on any non-obvious structure choice.

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
- **Secret leak protection**: secret-scanning CI job in `ci.yml` - fails build on exposed credentials
- **Dependency and SAST scan**: static analysis CI job in `ci.yml` - catches injection and path traversal vulnerabilities
- **Quality gate**: `sonar-project.properties` ready; add `SONAR_TOKEN` to GitHub Secrets to activate the quality badge and merge gate
- **Path traversal guard**: inject `_safe_path` (from `references/architecture-patterns.md`) when the project handles user-supplied file paths (CLI tools, file processors, upload endpoints); skip for pure API services or frontends

**Web Service archetype only**: create `endpoint-inventory.json` with `[{"method":"GET","path":"/health","added_in":"scaffold"}]`. `genesis check` uses this to detect API surface drift after 30+ days.

### Step 4: Tests
Create `tests/` with: minimum 1 unit test that actually passes (not `assert True`), test config file (jest.config.js, pytest.ini, pyproject.toml, etc.), tested function must be the core function of the project.

### Step 5: GitHub Actions CI/CD
Create `.github/workflows/ci.yml` using the language-specific template from `references/architecture-patterns.md`.
The template includes four parallel jobs: `test`, `secrets-scan`, `sast`, `quality-gate`.
The `quality-gate` job activates automatically once `SONAR_TOKEN` is added to GitHub Secrets.
Note: after creating the project in SonarCloud, disable "Automatic Analysis" in the SonarCloud project settings - CI-based analysis and Automatic Analysis conflict.

### Step 6: Self-validating smoke test (mandatory)

Run the test suite. Fix failures. Repeat until green. Never skip.
Run `pytest` / `npm test` / `cargo test` / `go test ./...`. If exit 0: proceed.
If non-zero: read error, fix the failing file, retry - max 3 attempts.
After 3 failures: report exact error, ask user before proceeding. Never commit on red.

Also verify the CLI entrypoint if one exists:
- Python: read `[project.scripts]` in `pyproject.toml`, run `[entrypoint] --help`
- Node/Go/Rust: read `bin`/build first, then run `[entrypoint] --help`

**Hard gate**: do not run `git commit` and do not announce "Genesis Architect complete" until the test suite exits 0.

### Step 6.5: Mitigation coverage check
For each pitfall in PITFALLS.md, extract the Mitigation field and identify core nouns/verbs (e.g., "lazy-load", "validate", "stream").
Search src/ for files containing the key patterns.
Output:
- "Pitfall [N]: mitigation detected" if found
- "Pitfall [N]: mitigation not detected - manual review advised" if not found
Do not block on this - it is a warning, not a gate.

### Step 7: README badges, demo, and git

**Badges**: add to README.md using shields.io (see `references/architecture-patterns.md` for badge block template). Replace `{user}/{repo}` with `[github-user]/[repo-name]` if no remote exists; tell user to update on first push.
**Demo recording**: suggest `asciinema rec demo.cast` then `agg demo.cast assets/demo.gif`.
**Git setup** - always ask before each command:
1. `git init` - "Initialize Git repository?" (`.gitignore` already created in Step 1)
2. `git add . && git commit -m "feat: initial scaffold generated by Genesis Architect"`
3. Ask: "Add a GitHub remote?" - if yes: `git remote add origin [url]`, then show the
   push command but **never run it automatically**

Never commit `.env` - always commit `.env.example`.

### Step 7b: Security and Quality Hardening (automatic on every genesis init)

The four-job `ci.yml` created in Step 5 already includes secret scanning and SAST. Additionally create `sonar-project.properties` (use template from `references/security-templates.md`):
```
sonar.projectKey=[github-username]_[project-name]
sonar.organization=[github-username]
sonar.sources=src
sonar.qualitygate.wait=true
```
Announce: 'Quality gate ready. To activate: (1) add SONAR_TOKEN to GitHub Settings > Secrets, (2) disable Automatic Analysis in SonarCloud project settings.'

Create strict `.gitignore` additions (append to existing):
```
.env
.env.*
!.env.example
*.pem
*.key
*.p12
venv/
node_modules/
__pycache__/
```

Add to ROADMAP.md a Phase titled 'Activate Quality Gates' with steps: (1) Add SONAR_TOKEN secret to GitHub Settings > Secrets, (2) Add SNYK_TOKEN secret to enable dependency CVE scanning, (3) Verify first green CI run.

### Step 8: Deliver summary
Announce: "Genesis Architect complete. [bullet list of created files]. Next: [first ROADMAP phase]. Entering companion mode."

---

## Phase 7: Development Companion Mode

After Phase 6, enter companion mode. Direct invocations: `genesis help [problem]`, `genesis research [topic]`, `genesis check` (freshness audit).
**`genesis check`** - freshness audit (run 30+ days after scaffold): check deps for CVEs + CI action versions. Use OSV.dev API for deterministic CVE detection (see mcp-strategy.md). Report: CRITICAL / WARNING / INFO. Never auto-apply - show upgrade commands only.
**`genesis resolve [topic]`** - Smart Resolution Engine: checks local Knowledge Vault first, then fetches from Stack Overflow. Prioritizes accepted answers and high-score results. Includes recency classification (recent: last 24 months / classic). Always shows source URL. Never patches code without explicit user confirmation.
**Knowledge Vault**: solutions are cached in `.genesis/vault/` by topic and language. Use `python scripts/vault.py search "[topic]" [language]` to query, `vault.py save` to add entries, `vault.py stats` to inspect. Vault hits avoid external API calls entirely.
**Stuck on a problem**: search Phase 2 repos first, then competing projects. Present 1-3 approaches ranked by ecosystem adoption. Cite source repo.
**Dependency question**: check last commit date, open issues trend, flag better-maintained alternatives.
**New sub-problem**: ask "Want me to search the ecosystem for how others solved this?" before scanning.
**Feature complete**: suggest updating ROADMAP.md, offer to research the next phase.
**No research context / new session**: read `RESEARCH.md` from working directory.
Extract and restore:
- Repos analyzed (Analyzed Repositories table)
- Pitfalls found (link to PITFALLS.md mitigation patterns)
- Architecture decision (Architecture Decision Rationale section)
- Language and tier chosen
Announce: 'Research context restored from RESEARCH.md - [N] repos, [M] pitfalls loaded.'
If RESEARCH.md missing: 'RESEARCH.md not found. Run genesis audit . or describe the current project.'
**Boundaries**: never act without asking first - max 3 options - stay grounded in analyzed repos, not general advice.

---

## Mandatory Deliverables

All files go inside the project directory. Everything must be Git-portable.
**Privacy:** Environment-specific values from Phase 0 (Scripts paths, home directory paths, usernames embedded in paths) must appear as placeholders in deliverables: use `[Scripts path]`, `[home]`, etc. Never write the literal measured path into RESEARCH.md, PITFALLS.md, or ROADMAP.md - these files get committed to public repos.

Use templates in `assets/RESEARCH.template.md`, `assets/PITFALLS.template.md`, `assets/ROADMAP.template.md`. Required RESEARCH.md sections: Executive Summary, Search Scope, Analyzed Repositories (min 5 rows), Market Landscape, Architecture Decision Rationale, Sources (min 3 links). Must contain "Genesis Architect" in header.

---

## Architect Mode

When 0 comparable projects exist, switch to first-principles mode. Announce: "No similar projects found. Switching to Architect Mode."
Apply: SOLID, Clean Architecture, Twelve-Factor App (for services). Note in RESEARCH.md: "First-principles design - no direct ecosystem precedent found."

---

## Format Rules

- No em dashes (use hyphens or colons)
- Respond in the user's detected language
- Code, file names, variable names, comments: English only
- Prefer tables and structured lists over paragraphs
- ROADMAP.md: 5-10 phases, length calibrated to research complexity
