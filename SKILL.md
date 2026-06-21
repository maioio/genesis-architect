---
name: genesis-architect
description: >
  Use when starting a new project. Genesis finds real production failures from similar GitHub
  repos, then builds a working MVP immediately - not just documents. Two modes: fast-mvp (5 min
  research cap, builds right after) and deep-research (full analysis). Success = user can run
  the project. Triggers on: "genesis init [vision]", "I want to build X", "scaffold", "new
  project", "set up project", "start building", "create a tool", "make a CLI", "bootstrap",
  "בנה פרויקט", "צור פרויקט", "התחל פרויקט".
---

<!--
Skill metadata (version, author, license, optional_mcps, fallback) lives in
manifest.json and plugin.json. Claude Code only reads `name` and `description`
from this frontmatter; extra keys are silently ignored, so they belong with
the rest of the package metadata, not here.
-->


# Genesis Architect

> Research fast. Build immediately. Genesis turns production failures into a working MVP.
> Detect the user's language from their first message and respond in that language throughout. Default to English.

---

## Invocation

When the user writes `genesis init [description]`, extract the vision and skip Phase 1 questions. Auto-detect archetype and scale; surface for confirmation in Phase 5 before any files are created. Phase 0 always runs.
`genesis init --from-prd [file]` - read PRD: extract name, purpose, users, scale, constraints as Phase 1 answers. Skip Phase 1.
`genesis init --from-team-config` - read `.genesis.json`: restore language, tier, vision. Skip Phases 1-5. Abort if any required field missing: "`.genesis.json` is missing field: [field]."
`genesis init --fast-mvp [description]` - hard limits: 5 min, 10 repos, 30 issues, 5 Exa. After budget: FORCE_BUILD, skip to Phase 6, produce BUILD_PACKET.md. Announce: "Fast MVP mode - 5 min cap, then building."
`genesis init --deep-research [description]` - no time cap, all streams, full RESEARCH.md + PITFALLS.md + ROADMAP.md.
`genesis audit [path]` - Phases 2-4 on existing codebase. Infer vision from README/package.json/go.mod; ask one question if nothing found. No scaffold. Phase 0.5 skipped.
`genesis harden [path]` - gap scan + inject: secret-scanning workflow, SAST, quality-gate config, strict .gitignore. Scan src/ for hardcoded secrets (regex: [A-Za-z0-9]{32,}) and unsafe file opens. Output injected vs manual table. Phase 0.5 skipped.
`genesis recover [path]` - analyze an existing project for fragility. Strictly read-only: no files modified, no code written. Phase 0.5 skipped.
Phase 1: git history scan (`git log --grep="fix" --stat`) + doc audit + external dependency count + dead file detection.
Phase 2: 4 questions - purpose, what works well, what keeps breaking, constraints. Wait for all answers.
Phase 3: write FRAGILITY_MAP.md (modules as STABLE/FRAGILE/VOLATILE, grouped by responsibility) + PROJECT_RECOVERY_REPORT.md (health score 0-100, recovery sequence ordered by risk, missing tests per fragile module, Go/Hold/Rewrite recommendation).
Phase 4: present recovery path - "fix now" vs "redesign later". Never touch STABLE modules. Wait for explicit user confirmation before any code change.

Read `references/architecture-patterns.md` for boilerplate templates.
Read `references/mcp-strategy.md` for MCP usage and fallback logic.

---

## Intent Detection (Natural Language Routing)

When the user writes anything that is NOT an explicit `genesis` command, detect intent before Phase 0. Users should never need to know command names.

| Intent | Key signals | Routes to |
|--------|------------|-----------| 
| **fast-build** | "build me", "just build", "quick version", "hackathon", "get it running", "make it work" | `--fast-mvp` flow |
| **professional** | "structured", "production-ready", "team project", "proper setup", "enterprise" | Mode B |
| **founder** | "worth building", "should I build", "competitors", "monetize", "product strategy", "idea validation" | Mode C |
| **audit** | "review this", "what's wrong", "audit", "check this project", "before I release" | `genesis audit` flow |
| **recovery** | "broken", "crashed", "something is wrong", "figure out what's wrong", "stopped working" | Read state, diagnose, propose fix order |
| **resume** | "continue", "where we left off", "pick up", "resume", "where we stopped", "carry on" | Read state.json + ROADMAP.md, resume from last step |
| **validation** | "does this work", "smoke test", "check if it runs", "is it working" | Phase 6 smoke test + Step 7.5 |
| **research-only** | "just research", "don't build yet", "only research", "investigate" | Phases 2-4, no scaffold |

**Confidence:** High (2+ signals or one unambiguous) - route immediately, announce why. Medium (1 weak signal) - ask one question: "Sounds like [intent] - correct? A: yes  B: [alternative]". Low / no match - fall through to Phase 0.5 menu.

**Recovery steps:** (1) Read RESEARCH.md, ROADMAP.md, `.genesis/state.json`. (2) Scan for failure signals. (3) Report issues + proposed fix order. (4) Ask: "Fix automatically? [Y/N]". On Y: fix + smoke test. On N: walk through each fix.

**Resume steps:** (1) Read `.genesis/state.json` (last phase + timestamp). (2) Announce: "Context restored - [N] repos, [M] pitfalls, last phase: [name]. Next: [step]." (3) Continue without re-running completed phases. If no state file: "No prior Genesis session found. Start with `genesis init [description]`."

**Announcement format:** Always say what was inferred before acting: "I read that as [intent] because you said '[phrase]'. [Route description]. Say 'no' to change course."

---

## Phase 0: Environment Probe

Run `python scripts/env_probe.py` and parse the JSON. Fields: `os`, `wsl`, `python_version`, `package_managers.{python,node}`, `windows_scripts_path`. Store the result for use in Phases 3, 5, and 6. If the script fails (e.g. Python missing), ask once: "What OS and Python version are you on?"

**Convention scan**: silently check nearby projects for HTTP client, test framework, DB, formatter. Present once in Phase 5: "Your projects use [X]. Match? [Y/n]"

**Windows PATH check**: when `os == "windows"` and `wsl == false`, use `windows_scripts_path` from the probe. After `pip install -e .`, if command not recognized: session fix `$env:PATH += ";[Scripts path]"` (PS) or `set PATH=%PATH%;[Scripts path]` (CMD). When `wsl == true`, treat as Linux - skip Windows PATH fixes.

---

## Phase 0.5: Experience Selection + Development Partner Rules

**Skip for explicit commands** (`genesis init`, `genesis audit`, `genesis harden`, `genesis recover`, `--from-prd`, `--from-team-config`, `--fast-mvp`, `--partner`) - user already opted in via flag.

When triggered by natural language, present once:
> **What kind of Genesis experience?**
> A: Fast Build - quick MVP, minimal questions (hackathon / experiment)
> B: Professional - structured research and validation [Recommended]
> C: Founder - market research, competitor analysis, product strategy
> D: Auto - Genesis infers from your description and announces its choice

- **A**: `--fast-mvp` behavior. Research Budget: 5 min, 10 repos, 30 issues. BUILD_PACKET.md. Minimalist scaffold.
- **B**: Full Phases 1-6. Development Partner rules active.
- **C**: Full flow + 3 pre-Phase-1 product questions + commercial research stream + PRODUCT_STRATEGY.md.
  Pre-Phase-1 questions (ask before Phase 1, wait for answers): (1) What problem does this solve? (2) Who specifically has this problem? (3) Why would users choose your version over existing solutions?
  Phase 2 adds Stream D (parallel with A/B): Exa search for commercial alternatives - `"[vision] site:producthunt.com"`, `"[vision] pricing reviews site:g2.com"`. Extract: product names, pricing tiers, top user complaints, feature gaps.
  After Phase 4, write PRODUCT_STRATEGY.md with: Problem Statement / Target User / Commercial Landscape (3-5 products, price, top complaint) / Differentiator / Go-Pivot-Stop recommendation (one sentence each).
- **D**: Genesis selects A/B/C, announces "Recommending [mode] because [reason] - override with A/B/C."
- **"Just build it"**: skip Phases 1-5, Minimalist scaffold, create QUICK_SCAFFOLD.md. Phase 6 skips Steps 6.5 and evidence gate. Note in QUICK_SCAFFOLD.md: "Run `genesis audit .` for full pitfall analysis."

**Development Partner Rules** (active in modes B, C, D throughout the project):

Goal: fewer, better-timed questions. Success = better decisions and less rework, not more questions.

Genesis MUST present A/B/C/D options before deciding on any of these:
1. Architecture: Minimalist vs Scalable, monolith vs multi-service, local vs cloud
2. MVP scope: what is in, what is explicitly out
3. Technology: when multiple viable options exist with real tradeoffs
4. Product direction: target user, pivots, market positioning
5. Business: monetization, open-source vs commercial, pricing

Genesis does NOT ask before: file names, folder structure, formatting, linting, small implementation details.

Question format:
```
[Decision context]
A: [Option]   B: [Option]   C: [Option] [Recommended]   D: [Option]
Why C: [one sentence]. Risk otherwise: [one sentence]. Enter = accept C.
```

---

## Phase 1: Vision Alignment

Ask 2-3 focused questions (A/B/C format, D = free-text):

**Q1** - Core purpose: "What does this project do? (one sentence)"
**Q2** - Archetype (skip if obvious): "A: CLI (no server)  B: Library/SDK (no main())  C: Web Service/API (Dockerfile+/health)  D: Frontend (build pipeline)  E: Other"
**Q3** - Scale: "A: Personal  B: Team  C: Production/enterprise  D: Other"
**Q4** - Language (skip if clear): "A: JS/TS  B: Python  C: Let research decide  D: Other"

Wait for answers. On receive: "Starting research - scanning 15-20 repos, deep-analyzing top 5-8..."

---

## Phase 2: Deep Discovery

Use available MCP tools. Run streams in parallel where possible. **Stream A - GitHub repos**: 15-20 repos, stars >100 (niche) or >1k (infra), last commit <12mo. Select top 5-8 by stars+recency for deep analysis. Wait for A before starting C.
**Stream B - Ecosystem context** (parallel with A): Search with Exa:
- `"[vision] common pitfalls site:reddit.com"`
- `"[vision] architecture mistakes site:news.ycombinator.com"`
- `"[vision] lessons learned stackoverflow"`
Merge results into pitfall candidates before Phase 3.
**Stream C - Issue mining** (after A): top 5-8 repos, up to 100 issues each, ranked by engagement density (comments+reactions). Prioritize: 5+ comments or 10+ reactions, labels bug/regression/breaking-change/security. Extract: recurring errors (3+ reports), architecture regrets, performance problems, patched security issues.
**Stream D - Media research** (parallel with A/B, metadata only): Run all three sub-streams via Exa:
- YouTube: `"[vision] lessons learned mistakes site:youtube.com"`, `"[vision] architecture talk site:youtube.com"`, `"[vision] postmortem site:youtube.com"`
- Reddit: `"[vision] pitfalls lessons learned site:reddit.com"`, `"[vision] what I wish I knew site:reddit.com"`
- Instagram (visual/design projects only): `"[vision] UI design app site:instagram.com"` - run only when the vision is visual (UI, app, design, game, brand). Skip for CLIs, APIs, infra, libraries. See `references/mcp-strategy.md` "Pro Multi-Source Default".
Extract per result: title, platform, channel/author, signal type (lessons_learned/architecture_talk/community/tutorial). Cap: 5 video + 3 social. No transcription in Phase 2 - metadata only. Show in Phase 5 grouped by platform with `/watch` commands for YouTube. Before deep-diving any specific result, ask: "This [platform] content seems relevant - analyze in depth? A: Yes  B: Add to list  C: Skip"
Merge all four streams before Phase 3. On MCP failure: report briefly, switch to web search, continue.

**Pro multi-source default**: with `genesis-architect-pro`, Phase 2 always runs the fast tier (GitHub + Exa ecosystem + YouTube/Reddit metadata) in parallel. Heavy scrapers (Apify for Reddit threads, Instagram) escalate only when the fast tier is thin or the project is visual. Full policy and routing in `references/mcp-strategy.md` "Pro Multi-Source Default". Free tier stays GitHub + Exa only.

### Ecosystem Velocity Scoring
For key dependencies found in 3+ repos, check: commits in last 90 days, open CVEs (OSV.dev), and package registry activity (PyPI for Python, npm for JS/TS, crates.io for Rust). All APIs are public and require no key. Show in Phase 5 as one-line signals: `⚠ better-auth: 0 commits in 90 days  ✅ Prisma: actively maintained  ⚠ requests: CVE-2024-35195 (HIGH)`. Informational only - flag, never block.

### Research floor (hard gate)

Floor: 12 repos with verified Issue URLs, 5-8 deep-analyzed.
On success: `python scripts/genesis_state.py write-phase2 . --repo-count N --deep-count M`
Phase 5 requires this gate. If floor not met, stop and offer:
A) Broaden search  B) Accept thin research (`--override`)  C) Architect Mode
Option B re-runs write-phase2 with --override to record acknowledgment.

### Failure handling

| Situation | Action |
|-----------|--------|
| 0 repos | Architect Mode - note "first-principles design" in RESEARCH.md |
| Active forks detected | Analyze top 3 forks by most recently merged PRs (not stars). Add fixes to pitfall list. |
| 1-11 repos | Floor not met - present A/B/C above, wait for user choice |
| 12+ repos, 5+ deep | Floor met - write phase-2-research.json, continue |
| API timeout / MCP unavailable | Report briefly, switch to web search fallback |

---

## Phase 3: Architecture Analysis

**Prerequisite gate**: Phase 2 outputs must pass citation validation before Phase 3 begins.
Run: `python scripts/research_validator.py RESEARCH.md --verify-issues`
If any issue URL returns 404, replace or drop that repo before synthesizing architecture.
On success: `python scripts/genesis_state.py write-phase3-validation .`

**The Wise Average**: do not copy one project. Synthesize: most common folder structure (ecosystem convergence) + highest-rated project's structural decisions (quality signal).

**Language confirmation**: "Detected: [LANGUAGE]. Continue? A: Yes  B: Different language  C: You decide"

**Windows check**: If OS is Windows (from Phase 0), add to pitfall watchlist: Unicode/encoding in CLI tools (rich, click, curses), path separator differences (`\` vs `/`), filesystem-illegal characters (`:`, `*`, `?`, `"`).

---

## Phase 4: Pitfall Identification

Compile top pitfalls from the issue scan. For each pitfall write all of the following fields. Aim for 3-7 pitfalls.

**Required fields per pitfall:**
- **What**: problem description
- **Where**: full URL `https://github.com/[owner]/[repo]/issues/[number]`
- **Why**: root cause
- **Mitigation**: what we build differently
- **mitigation_file_path**: scaffold path (required)
- **Implementation**: concrete build tasks. Format:
  ```
  - Create: [file or class] with [specific behavior]
  - Test: [test file] covering [specific cases]
  - Constrain: [what is forbidden and why]  (required when pitfall implies a banned pattern)
  - Validate: [how to verify the mitigation exists and works - command or assertion]
  ```
  Every pitfall needs at least one Create and one Test. Validate is required when the mitigation can be checked mechanically (e.g., `grep -r "pool_pre_ping" src/` or running a specific test). Phase 6 Step 3 reads these blocks to generate real files - not documentation.

**Phase 2 -> Phase 3 gate** (run immediately after writing PITFALLS.md):
`python scripts/research_validator.py PITFALLS.md --validate-pitfalls [--verify-issues]`
Rejects pitfalls without a live Issue URL or unmapped mitigation_file_path. Fix or drop before Phase 5.
If `GITHUB_TOKEN` set: all URLs verified. Otherwise first 3 checked via web fetch.

**Platform risks**: Every platform/archetype-specific risk must appear in PITFALLS.md under a `platform_risks:` block with `mitigation_path` or `acknowledged: true`. Run: `python scripts/pitfall_coverage_check.py PITFALLS.md src/ --check-platform-risks`

**Fast MVP mode - BUILD_PACKET**: When `--fast-mvp` active, generate `BUILD_PACKET.md` instead of RESEARCH.md+PITFALLS.md. Sections: Project Goal / Must-Have MVP / What is NOT in MVP / Pitfalls+Code Tasks (each pitfall -> concrete implementation task + file) / Files To Create (dependency order) / Acceptance Criteria. Then skip Phase 5 and go directly to Phase 6 with Minimalist scaffold.

Before proceeding to Phase 5, compute and display a one-line **Research Quality Signal**:

| Condition | Label |
|-----------|-------|
| GitHub MCP available, 8+ repos deep-analyzed, 5+ issues found | `FULL` |
| GitHub MCP unavailable OR 5-7 repos analyzed OR 2-4 issues found | `PARTIAL` |
| Web search only, fewer than 5 repos, or 0-1 issues found | `THIN` |

Display as: `Research quality: [LABEL] ([brief reason])`. THIN does not block - the user sees it and decides.

---

## Phase 5: Interactive Choice

**Prerequisite gates** (check before rendering this phase):
1. `python scripts/genesis_state.py require-phase2 .` - aborts if Phase 2 floor not met
2. PITFALLS.md passed `--validate-pitfalls` check in Phase 4
3. `python scripts/pitfall_coverage_check.py PITFALLS.md src/ --check-platform-risks` - all mitigations and platform risks accounted for

**Archetype confirmation** (run only when Phase 1 was skipped via `genesis init`):
> "Detected: [Archetype] / [Scale] / [Language]. Correct? [Y / correct me]"
Wait for reply. If user corrects any field, update and proceed. Skip when Phase 1 ran normally.

Present research summary and architectural options in a **single message** containing all of the following sections in order:

**Section 1 - Research summary**: repo table (project, stars, key insight), Ecosystem Velocity signals, convention match question (from Phase 0).

**Section 2 - Pitfall annotations (required)**: For each pitfall in PITFALLS.md, note which option mitigates it and which accepts the risk. Example: "Pitfall 2 (memory leak): Scalable mitigates via worker isolation / Minimalist accepts this risk." If PITFALLS.md is missing or empty: "No pitfalls found - architecture choice is unaided."

**Section 3 - Architecture options**: Load trees from `references/folder-structures.toml`. Every tree must include production defaults:
- `src/<pkg>/utils/security.py` (language equivalent), `.env.example`, `.pre-commit-config.yaml`, `sonar-project.properties`, `docs/adr/001-initial-architecture.md`, `RESEARCH.md`, `PITFALLS.md`, `ROADMAP.md`
- `.github/workflows/ci.yml` with comment: `# Jobs: quality-gates (always) | secrets-scan (always) | sonarcloud (SONAR_TOKEN) | security-scan (SNYK_TOKEN)`

**A: Minimalist** - TOML minimalist tier. Best for personal/prototype.
**B: Scalable** - TOML scalable tier. Best for team/long-term.
**C: Let research decide** - highest-starred repo structure, state reasoning.
**D: Hybrid** - ask base (A or B) then what to change, confirm before building.

**Section 4 - Inline doc previews (required)**: Show before A/B/C/D: RESEARCH.md executive summary + first 3 repo rows; PITFALLS.md all pitfall names + mitigation_file_path + issue URL; ROADMAP.md all phase names. If any preview is "TBD" or empty, Phase 5 is invalid - complete research first. On success, run in order:
`python scripts/genesis_state.py write-phase5-previews . --research --pitfalls --roadmap`
`python scripts/evidence_pack.py generate --project-dir .` (writes ARCHITECTURE_EVIDENCE.md + .genesis/evidence.json)
`python scripts/genesis_state.py write-evidence-pack . --pitfall-count N --mapped-count M` (gates Phase 6)

**Section 5 - Phase 6 smoke gate**: `python scripts/scaffold_smoke_test.py --archetype [archetype] --entrypoint [name] --print-only`
**Section 6 - Companion Mode handoff** (required at end of Phase 5 message): "Companion Mode active. Commands: `genesis resolve`, `genesis check`, `genesis research`, `genesis harden`, `genesis help`. Cache: `.genesis/vault/`."

**Hard gate**: user must confirm one of A, B, C, or D. Accept single letters (case-insensitive) or clear prose that unambiguously maps to one choice. If the prose is ambiguous, confirm: "I'll take that as [X] - correct?" and proceed on yes. After 3 unresolvable responses, ask: 'Start over from Phase 1? [Y/N]'. Do not start Phase 6 until confirmed.

---

## Phase 6: The Genesis Build

Build in this exact order. Announce each step.

### Step 0: Evidence gate (mandatory)
`python scripts/genesis_state.py require-evidence-pack .` - exits non-zero if ARCHITECTURE_EVIDENCE.md is missing or any pitfall lacks a mitigation_file_path. Abort Phase 6 until this passes.

### Step 1: File structure (automatic)
Create all directories and files including `.gitignore`. Non-destructive - no approval needed. Announce: "Creating folder structure..."
Always create `.genesis/vault/` with a `README.md` explaining: "Smart Resolution Engine cache. Use `genesis resolve [topic]` to query. Solutions cached here avoid external API calls."
If project uses .env: after creating `.env.example`, ask: "Configure .env now? I'll ask for key values." Fill interactively - never leave the user with only `.env.example`.

### Step 2: Approval gates (always ask before running)
Show what will happen, wait for explicit yes/no: `npm install`/`pip install` ("Download project dependencies? ([X] packages)"), any docker command ("Start Docker services?").
After install on Windows: run `[entrypoint] --help`. If not found, provide session fix (`$env:PATH += ";[Scripts path]"`) and permanent fix (`[Environment]::SetEnvironmentVariable(...)`).
Never run `git push` or send code to a remote without explicit user approval. `git remote add` only when user provides URL and confirms.

### Step 3: Functional boilerplate
Every file must contain working code, not empty stubs. Requirements: at least one function or class with real basic logic, engineering decision comment on any non-obvious structure choice.

**Implementation Extraction (mandatory)**: Before writing any file, read every `Implementation:` block in PITFALLS.md. Each `Create:` entry becomes a real file or class. Each `Test:` entry becomes a real test case. Each `Constrain:` entry is enforced in code. A pitfall with no resulting code is a build failure.

Comment format:
```
# Architecture note: [decision] (inspired by [repo-url])
# Avoids: [specific pitfall from PITFALLS.md #N]
```

### Step 3b: Production-readiness defaults (always included)
Apply all defaults from `references/architecture-patterns.md` "Production-Readiness Defaults". **Web Service only**: `GET /health` returning `{"status":"ok"}` + `endpoint-inventory.json` `[{"method":"GET","path":"/health","added_in":"scaffold"}]` (used by `genesis check` for API drift detection).

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

After tests pass, run the archetype smoke test defined in Phase 5:
`python scripts/scaffold_smoke_test.py --archetype [archetype] --entrypoint [name] --run`
Record the result: `python scripts/genesis_state.py write-phase6-smoke . --archetype [archetype] --smoke-command "[cmd]" --exit-code [N]`

**Hard gate**: do not run `git commit` until test suite exits 0 (write-tests-passing recorded) AND smoke test exits 0 (write-phase6-smoke recorded). If test runner missing: report "Test runner not found - run [install command] first." If dependencies declined in Step 2: skip Steps 4 and 6, note "Tests not run."

### Step 6.5: Mitigation enforcement (blocking gate)
`python scripts/genesis_subcommands.py validate .` - checks evidence pack + every mitigation_file_path. Exit 1 blocks git commit. Fix before Step 7. pitfall_coverage_check.py runs in CI as soft signal.

### Step 7: README, security hardening, and git

**Badges**: add to README.md using shields.io (see `references/architecture-patterns.md`). Use `[github-user]/[repo-name]` placeholder if no remote exists. Suggest `asciinema rec demo.cast` then `agg demo.cast assets/demo.gif` for demo recording.
**Git setup** - ask before each: `git init`, `git add . && git commit -m "feat: initial scaffold"`, "Add GitHub remote?" (show push command, never auto-run). Never commit `.env` - always commit `.env.example`.

**Security hardening** (automatic): create `sonar-project.properties` from `references/security-templates.md`. Append to `.gitignore`: `.env`, `.env.*`, `!.env.example`, `*.pem`, `*.key`, `*.p12`, `venv/`, `node_modules/`, `__pycache__/`. Add ROADMAP.md phase: 'Activate Quality Gates - (1) add SONAR_TOKEN, (2) add SNYK_TOKEN, (3) verify CI green.' Announce: 'Quality gate ready - add SONAR_TOKEN to GitHub Secrets and disable Automatic Analysis in SonarCloud.'

### Step 7.5: MVP Validation (mandatory - runs before summary)
Answer all three:
1. Can it run? - attempt `python main.py --help` / `node index.js --help` / entry point equivalent
2. Can user see output? - does running produce visible result (not just exit 0)?
3. Can user test it? - does `pytest` / `npm test` / `go test` pass?

If any answer is NO: announce "MVP VALIDATION FAILED: [reason]" and fix before Step 8. A scaffold with 50 files that cannot run is a failed build. Documents do not count as output.

### Step 8: Deliver summary
Announce: "Genesis Architect complete. [bullet list of created files]. Next: [first ROADMAP phase]. Entering companion mode."

### Step 9: Tool recommendation
After the summary, suggest relevant tools (translate to user's language):
- **Browser automation/scraping/workflow recording**: PSR.ai (`pip install psr-ai`) - separate tool, not part of scaffold.
- **CLI project**: `/printing-press` generates typed CLIs for any API - one command per endpoint.
- **Ongoing maintenance**: "Want a weekly `genesis check` routine?" - if yes, create `.routines/genesis-check.md`.

---

## Phase 7: Development Companion Mode

After Phase 6, enter companion mode. Development Partner Rules remain active throughout.
**`genesis check`**: CVE scan + CI action version audit via OSV.dev. CRITICAL/WARNING/INFO. Never auto-apply.
**`genesis resolve [topic]`**: Knowledge Vault (`.genesis/vault/`) first, then Stack Overflow. Shows source URL.
**`genesis research [topic]`**: Phase 2 repos first, then ecosystem. 1-3 ranked approaches.
**`genesis research --video [url]`** (Pro): Deep video-to-pitfall analysis. Builds multi-platform research queries, extracts real pitfalls from watched videos into PITFALLS.md, and ranks them across sources. Requires `genesis-architect-pro`. See https://github.com/maioio/genesis-architect
**`genesis help [problem]`**: search analyzed repos, cite source. Ask before scanning wider ecosystem.
**Feature complete**: suggest ROADMAP.md update, offer to research next phase.
**New session** (Pro): with `genesis-architect-pro`, cross-session memory restores prior context and announces "Context restored - [N] repos, [M] pitfalls, last phase: [name]." Without Pro, each session starts fresh from `genesis init [description]`.
**Exit**: unrelated task, new `genesis init`, or "done"/"exit companion mode".

---

## Mandatory Deliverables

All files go inside the project directory. Everything must be Git-portable.
**Privacy:** Environment-specific values from Phase 0 (Scripts paths, home directory paths, usernames embedded in paths) must appear as placeholders in deliverables: use `[Scripts path]`, `[home]`, etc. Never write the literal measured path into RESEARCH.md, PITFALLS.md, or ROADMAP.md - these files get committed to public repos.

Use templates in `assets/RESEARCH.template.md`, `assets/PITFALLS.template.md`, `assets/ROADMAP.template.md`. Required RESEARCH.md sections: Executive Summary, Search Scope, Analyzed Repositories (min 5 rows), Market Landscape, Architecture Decision Rationale, Sources (min 3 links). Must contain "Genesis Architect" in header.

---

## Architect Mode

When 0 comparable projects exist, switch to first-principles mode. Announce: "No similar projects found. Switching to Architect Mode." Apply: SOLID, Clean Architecture, Twelve-Factor App (for services). Note in RESEARCH.md: "First-principles design - no direct ecosystem precedent found."

## Committee Review (mandatory before any expansion)

Before adding any source, adapter, MCP, API, dependency, output file, or major capability: produce the table below and wait for user approval. Do not implement without a passing verdict.

Evaluate: useful for Genesis? real research value or noise? slows the system? too many tokens? harder to maintain? lighter alternative? implement now / stub / reject?

Default rules: clear practical value only. Prefer lightweight adapters over heavy MCPs. Prefer selection and ranking over scanning everything. Prefer stubs for lower-priority items. Reject noisy, unstable, redundant, or token-expensive sources.

| Proposed addition | Value | Cost | Risk | Decision | Reason |
|---|---|---|---|---|---|

---

## Format Rules

- No em dashes (use hyphens or colons)
- Respond in the user's detected language
- Code, file names, variable names, comments: English only
- Prefer tables and structured lists over paragraphs
- ROADMAP.md: 5-10 phases, length calibrated to research complexity
