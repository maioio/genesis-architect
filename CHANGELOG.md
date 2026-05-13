# Changelog

All notable changes to Genesis Architect will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

## [2.2.0] - 2026-05-13

### Added
- **5 new scripts closing community issues #3-7**
  - `genesis_state.py` - machine-readable Phase 5/6 hard gates via state files
  - `genesis_subcommands.py check` - OSV.dev CVE scan + CI action version audit
  - `pitfall_coverage_check.py` - mechanizes Phase 6 Step 6.5 mitigation coverage check
  - `pitfall_coverage_check.py` - parses PITFALLS.md, walks src/, reports JSON coverage
- **`eval_runner --mode validate`** - schema validation for test_queries.json, wired into CI
- **`references/folder-structures.toml`** - single source of truth for all scaffold file lists; `scaffold_generator.py` now loads from TOML (removes 140-line hardcoded dict)
- **`docs/adr/001-initial-architecture.md`** - ADR for repo structure, feeds drift_detector.py baseline
- **Branch protection** on main: 5 required status checks

### Fixed
- `scaffold_generator.py`: path traversal via `--name` blocked; `_validate_name()` added with full validation
- `vault.py`: atomic index write (tmp + replace) prevents partial corruption; JSONDecodeError handled
- `drift_detector.py`: bullet-list ADR parser, baseline corruption recovery, `--help` guard
- `resolve_engine.py`: duplicate `from pathlib import Path` removed
- `python-cli` test isolation: `process_file()` accepts optional `base` param
- SonarCloud hotspots: `NOSONAR` annotations on safe `urlopen`/`subprocess`/`sha1` usages
- `evals/test_queries.json`: 15 missing `expected_flow` fields populated
- `python-cli/PITFALLS.md` Pitfall 3: replaced tqdm (unused) with path traversal (actual code)

### Infrastructure
- Dependabot: actions/checkout@v6, setup-python@v6, codeql-action@v4, sonarqube-scan-action@v8
- 12 GitHub topics (was 8)

## [2.1.0] - 2026-05-10

### Added
- **`genesis harden` command**: security and quality upgrade for existing projects. Gap-scans for missing secret-scanning workflow, SAST workflow, quality-gate config, and strict `.gitignore`; injects missing files; scans src/ for common security gaps; outputs a status table (auto-injected vs. manual action required)
- **Step 7b: Security and Quality Hardening** - automatic on every `genesis init`: creates `genesis_quality.yml` (secret scanning + SAST), `sonar-project.properties`, strict `.gitignore` additions, and ROADMAP phase for activating quality gates
- **`references/security-templates.md`**: production-ready CI templates for secret scanning, SAST, code quality gate, pre-commit hook, and language selection guide; includes `genesis harden` status table format
- **README**: `genesis harden` added to explicit commands, Companion Mode, deliverables table, and project structure tree; three new production-readiness defaults (secret scanning CI, SAST CI, code quality gate)

### Changed
- Version bumped from 2.0.0 to 2.1.0 across SKILL.md, README.md, CHANGELOG.md

### Fixed
- `examples/typescript-cli/RESEARCH.md`: replaced non-existent `nicolo-ribaudo/csv-parser` repo with `mafintosh/csv-parser` (1.5k stars, verified live)
- `examples/typescript-cli/PITFALLS.md`: updated issue URL from fabricated `nicolo-ribaudo/csv-parser/issues/142` to verified `mafintosh/csv-parser/issues/152`
- `research_validator.py` now returns exit 0 on the typescript-cli example
- Quality Score updated to 78/100 (measured) from previously reported 72/100

## [2.0.0] - 2026-05-10

### Breaking Changes
- SKILL.md refactored to 343 lines (was 400) - higher logic density, same behavior
- Phase 2 Stream C now ranks by engagement density (comments + reactions), not recency

### Added
- **Security: path traversal protection** in research_validator.py - `_safe_path()` guard + null-byte/metachar sanitization
- **Go/Rust/Frontend production parity**: non-root Dockerfiles, structured logging (slog/tracing), env validation (`mustEnv`/`require_env`) for all Go and Rust tiers; VITE_ env guard for Frontend
- **Phase 2: engagement-density issue ranking** - scans 100 issues/repo, surfaces top 10 by comments+reactions; priority labels (bug, regression, security)
- **Phase 7: structured context restoration** - extracts repos, pitfalls, architecture decision, language/tier from RESEARCH.md; announces "N repos, M pitfalls loaded"
- **Security and quality badges** in README
- **"Quality Shield" section** in README with 4-job verification table
- **Portfolio note** callout before License
- **.gitignore hardened**: `__pycache__/`, `*.pyc`, `.env`, `.env.*` (with `!.env.example` exception)

### Fixed
- Version consistency: SKILL.md, manifest.json, README.md all at 2.0.0
- PITFALLS.md Pitfall 3: replaced "Multiple repos" citation with traceable GitHub issue URL
- Quality score updated: 78/100 (was 72/100)

---

## [1.14.0] - 2026-05-10

### Added
- **manifest.json**: skills.sh/agentskills.io compatible manifest with categories, triggers, optional_mcps, install paths for Claude Code/skills.sh/Cursor/Codex CLI.
- **optional_mcps + fallback in SKILL.md frontmatter**: machine-readable MCP declarations.
- **OSV.dev CVE integration**: Phase 2 Ecosystem Velocity and Phase 7 `genesis check` now use OSV.dev API (no key, no rate limit) for deterministic CVE detection. See mcp-strategy.md.
- **Endpoint drift detection**: Web Service archetype Phase 6 creates `endpoint-inventory.json` for `genesis check` to detect API surface drift after 30+ days.
- **README comparison table**: "Why not just use X?" section with 10-row capability comparison vs create-t3-app, bolt.new, Cursor Rules, madison/scaffolding.
- **Cross-platform install**: README now shows Claude Code, skills.sh, Cursor, and Codex CLI install options.

### Changed
- Tagline: added subtitle "The only scaffolder that verifies its sources before building."
- Version badge updated to 1.14.0.

---

## [1.13.0] - 2026-05-10

### Added
- **Quality Score section in README**: measured 72/100 on TypeScript CLI example against the quality rubric (4 dimensions, 100 points). Projected average 69/100. Target 80+ for v2.0.0. Proves the claim, not just makes it.
- **Phase 4 rate-limit-aware verification**: when `GITHUB_TOKEN` is set, full `--verify-issues` runs; when not set, first 3 URLs are web-fetched and PITFALLS.md notes how many were live-verified. Resolves the CI opt-in vs Phase 4 auto-run contradiction.
- **Phase 6 Step 6.5 mitigation coverage check**: after smoke test, greps `src/` for each pitfall's mitigation keyword. Warns (not blocks) on 0 matches. Closes the loop between PITFALLS.md and actual scaffold code.
- **evals/test_queries.json flow annotation**: every test case now has `expected_flow` field (full/preflight_skip/audit/from_prd/from_team_config/null). Top-level `flow_coverage` object shows distribution. Test coverage now maps trigger -> flow, not just trigger -> yes/no.

---

## [1.12.0] - 2026-05-10

### Added
- **Validator self-check wired into Phase 4**: after writing PITFALLS.md, the skill now runs `python scripts/research_validator.py PITFALLS.md --verify-issues`. Any 404 URL must be replaced with a real issue before Phase 5. The skill validates its own output, not just produces it.
- **QUICK_SCAFFOLD.md in quick mode**: Phase 0.5 option B now creates a `QUICK_SCAFFOLD.md` noting no research was performed and pointing to `genesis audit .` for post-hoc analysis.
- **Quality eval rubric** (`evals/quality_rubric.md`): 100-point human-review rubric across 4 dimensions (Research Authenticity, Pitfall Relevance, Scaffold Quality, Phase Correctness). Intended for 5-run review before major releases.

### Fixed
- **Unit test templates are no longer trivial**: TypeScript `core.ts` exports `transform(input)` with empty-input guard; test checks return value AND rejects on empty. Python `core.py` exports `transform` with `ValueError` on empty; test uses `pytest.raises`. Smoke test now catches real logic errors.
- **`genesis audit` pre-flight clarification**: explicitly stated that Phase 0.5 does not apply to `genesis audit` - it is an explicit invocation, run Phases 2-4 directly.
- SKILL.md: 399 lines.

---

## [1.11.0] - 2026-05-10

### Added
- **Research Quality Signal (Phase 4 output)**: before Phase 5, displays one-line label - `FULL`, `PARTIAL`, or `THIN` with a brief reason (e.g. "GitHub MCP unavailable - web search only"). Users see research confidence before making architecture decisions.
- **`--verify-repos` flag in research_validator.py**: calls `https://api.github.com/repos/{owner}/{repo}` for every repo in the RESEARCH.md table. Flags repos that don't exist (404) and star counts outside +-50% of actual. Uses `GITHUB_TOKEN` env var if set.
- **CI runs `--verify-issues` on example PITFALLS.md**: `examples/typescript-cli/PITFALLS.md` is now HTTP-checked on every push.

### Fixed
- **`genesis init` archetype confirmation gap**: when Phase 1 is skipped, Phase 5 now opens with "Detected: [Archetype] / [Scale] / [Language]. Correct?" before A/B/C/D. Never silently assumes architecture. Closes the contradiction with "never guess on architecture decisions."
- **Phase 2 hard-gate on 1-4 repos**: replaced hard stop with graceful degradation - warn + offer to broaden/continue-thin/Architect Mode. Hard stop only on 0 repos. Aligns with mcp-strategy.md "never block on tool failure."
- SKILL.md at exactly 400 lines.

---

## [1.10.0] - 2026-05-10

### Added
- **Phase 0.5 intent check**: natural-language triggers now ask "serious project or quick experiment?" before launching full 8-phase flow. `genesis init` always skips this gate.
- **Quick scaffold mode**: Phase 0.5 option B runs Phase 6 directly with minimal Minimalist scaffold - no research, no waiting.
- **WSL detection in Phase 0**: if user is on Windows but inside WSL, Linux paths and package managers are used; Windows PATH fixes are skipped.
- **Honest Limitations section in README**: documents issue-mining depth, web-search-only quality regression, and opt-in issue URL verification.

### Changed
- **Research claim corrected**: "15-20 repos scanned, top 5-8 deeply analyzed" - Phase 2 Stream C now explicitly targets 5-8 repos for issue mining (was "top 3-5").
- **Phase 2 announcement**: now says "scanning 15-20 repos, deep-analyzing top 5-8" for accuracy.
- **research_validator.py**: added `--verify-issues` flag that HTTP HEAD-checks every GitHub issue URL cited in PITFALLS.md for 404s. Format validation (regex) runs by default; live verification is opt-in.

### Fixed
- SKILL.md at exactly 399 lines (was 401 after v1.9.1 patches).

---

## [1.9.1] - 2026-05-10

### Fixed
- **Phase 4 deep linking**: pitfall "Where" field now requires full GitHub issue URL
  (`https://github.com/owner/repo/issues/N`), not shorthand like `repo#142`.
- **Phase 7 resilience**: when RESEARCH.md is missing, companion mode now surfaces a
  clear message instead of silently failing.

---

## [1.9.0] - 2026-05-10

### Added
- **Parallel research (Phase 2)**: three simultaneous streams instead of sequential search.
  Stream A: GitHub repos. Stream B: Exa ecosystem context (Reddit/HN/SO). Stream C: Issue
  mining on top repos. Merged before Phase 3. Estimated 3-5x faster research phase.

### Changed
- Phase 2 restructured from tool-priority-list to three named parallel streams with explicit
  merge step. Fallback behavior unchanged (fail one stream, continue with others).
- SKILL.md: 397 lines (was 400, 3 lines reclaimed from parallel restructuring)

---

## [1.8.0] - 2026-05-10

### Added
- **Cross-org convention scan** (Phase 0): silently detects HTTP client, test framework,
  DB, and formatter from existing nearby projects; offers to match conventions in Phase 5
- **Ecosystem Velocity Scoring** (Phase 2): for key deps appearing in 3+ repos, checks
  commits in last 90 days and open CVEs; surfaces as one-line signals before Phase 5 A/B choice
- **Archetype axis** (Phase 1 Q2): CLI Tool / Library/SDK / Web Service/API / Frontend App;
  shapes every scaffold decision - CLI gets no server, Library gets no main(), Web Service
  gets Dockerfile + /health, Frontend gets build pipeline
- **Production-readiness defaults** (Phase 6 Step 3b): structured logging, non-root
  Dockerfile, CORS allowlist, startup env validation, Secret Zero pattern, health endpoint
  for Web Service archetype, ADR stub at docs/adr/001-initial-architecture.md
- **`genesis check`** (Phase 7): freshness audit command - checks deps for CVEs, CI action
  versions, runtime updates; reports CRITICAL/WARNING/INFO; never auto-applies changes
- **Production-Readiness Defaults section** in references/architecture-patterns.md: full
  code templates for env validation, health endpoints, structured logging, ADR stub,
  non-root Dockerfile for Python/Node/Go

### Changed
- **Trigger description** rewritten to lead with the differentiator: "scans 15-20 real
  GitHub repos and mines their Issues for pitfalls before writing a single file. No other
  scaffolding tool does this automatically."
- **Hard gate Phase 2**: fewer than 5 repos = hard stop (was: 1-2 repos = disclaimer only)
- **Hard gate Phase 5**: explicit A/B/C/D required before Phase 6 (was: recommendation only)
- **Hard gate Phase 6**: git commit blocked until tests pass; self-validating loop with
  max 3 auto-fix attempts before reporting to user
- **Phase 5 format**: now shows Ecosystem Velocity signals and convention match before A/B
- SKILL.md: 400 lines (at limit - future additions require trimming elsewhere)

### Fixed
- Rust CI action: `dtactions/rust-toolchain@v1` -> `dtolnay/rust-toolchain@stable`
- Python pyproject template: added `[project.optional-dependencies] dev` section
- scaffold_generator.py: unknown language no longer resets tier to minimalist
- RESEARCH.template.md: now has 5 repo rows and 3 source links (passes its own validator)
- All 40 em dashes removed across 7 files (CONTRIBUTING, README, DEMO_SCRIPT, FEEDBACK,
  CLAUDE.md, PITFALLS example, mcp-strategy)
- Git tags added for v1.3.0, v1.4.0, v1.5.0, v1.6.0, v1.7.0

---

## [1.7.0] - 2026-05-10

### Added
- **Hard gates** (3): Phase 2 <5 repos = stop; Phase 5 requires explicit letter; Phase 6
  blocks git commit until tests pass
- **Self-validating smoke test** (Phase 6 Step 6): run tests, read error, fix, retry up to
  3 times; hard gate on git commit
- **Archetype axis** in Phase 1 Q2 and Phase 5 folder structures
- **.github/workflows/ci.yml**: CI for this repo - validator, eval runner, scaffold smoke
  test, SKILL.md constraints, Python block validation, TOML validation, em dash scan

### Fixed
- Rust CI typo, Python dev deps, scaffold_generator tier bug, RESEARCH.template.md rows

---

## [1.6.0] - 2026-05-09

### Added
- **shields.io badge block** auto-generated in every project README (CI, version, license;
  PyPI variant for Python projects, npm variant for Node projects)
- **asciinema demo suggestion** in Phase 6 Step 7 - suggests recording workflow with exact
  commands; explains GIF conversion via `agg` for GitHub (script tags blocked)
- **Git setup** as structured Phase 6 steps: language-specific `.gitignore` in Step 1,
  `git init` + initial commit in Step 7, optional `git remote add` with user confirmation;
  `git push` never runs automatically
- **README badge block template** in `references/architecture-patterns.md` per language

### Fixed
- `scripts/research_validator.py` line 54: broken regex (unterminated string literal causing
  SyntaxError at runtime - all validation was silently failing)
- `assets/ROADMAP.template.md` Phase 1 name: "Foundation (complete)" -> "Scaffold (generated
  by Genesis Architect)" (declared fixed in v1.5.0 but was not actually updated)
- `examples/typescript-cli/ROADMAP.md` Phase 1 name: same fix applied to live example
- Phase 2 failure table: "0 repos found" row no longer contradicts Architect Mode section
- `evals/test_queries.json`: 5 new cases for v1.5.0 invocation modes (genesis audit,
  --from-prd, --from-team-config, genesis help, genesis research); version field synced
- `references/architecture-patterns.md`: CI/CD template replaced with 4 language-specific
  workflows (Node, Python, Go, Rust) - no more `INSTALL_COMMAND` placeholders
- All Scalable folder structure templates: added missing RESEARCH.md, PITFALLS.md, ROADMAP.md
- `pyproject.toml` template: added `pythonpath = ["src"]` to prevent pytest import failures
- CONTRIBUTING.md: added Phase 0 detection and smoke test to contributor verification checklist
- CLAUDE.md: Phase 0 note separated from phase list into its own paragraph
- Privacy rule added to Mandatory Deliverables: Phase 0 paths must use placeholders in
  deliverables, never literal values (prevents username leakage in public repos)
- SKILL.md trimmed from 393 to 354 lines (Companion Mode condensed, deliverable templates
  moved to assets/ as source of truth)

### Changed
- `plugin.json` and `evals/test_queries.json` version fields synced to 1.6.0

---

## [1.5.0] - 2026-05-07

### Added
- **`genesis init --from-prd [file]`** - new invocation mode: reads a PRD file (e.g., from idea-os),
  extracts vision/scale/target users, skips Phase 1, enriches Phase 2 with product context
- **`genesis init --from-team-config`** - reads `.genesis.json` to restore a teammate's prior research
  context; rebuilds the same scaffold without repeating Phases 1-5
- **`.genesis.json` team config** - generated automatically after Phase 6 with language, tier, repo count,
  pitfall count, and timestamp; enables `--from-team-config` for the whole team

### Fixed
- ROADMAP.md template Phase 1 name corrected to "Scaffold (generated by Genesis Architect)"
  (was "Foundation (complete)" - the v1.3.0 CHANGELOG entry was correct but the template was not updated)

---

## [1.4.0] - 2026-05-07

### Added
- **genesis audit [path]** - new invocation mode: runs Phases 2-4 on an existing codebase,
  delivers PITFALLS.md + RESEARCH.md showing what the project likely does wrong. Skips scaffold.
- **Deprecation Radar** (Phase 4): flags dependencies with last commit >18 months, archived repos,
  or migration-away patterns across analyzed repos
- **Research Quality Signal** (Phase 2): shows Full/Partial/Thin rating before proceeding;
  warns and offers alternatives if fewer than 5 repos found
- **Dynamic repo citations** (Phase 6 Step 3): architecture note comments must use actual
  repo URLs from Phase 2, not placeholders. Pitfall references must match PITFALLS.md headings.
- **RESEARCH.md context restore** (Phase 7): companion mode now explicitly parses the
  Analyzed Repositories table from RESEARCH.md to restore session context

### Changed
- PITFALLS.md and RESEARCH.md templates trimmed to be more concise (same content, fewer lines)
- ROADMAP.md Phase 1 renamed from "Foundation (complete)" to "Scaffold (generated by Genesis Architect)"
- SKILL.md stays at 374 lines (under 400 limit)

## [1.3.1] - 2026-05-07

### Changed
- README restructured: 'See it in action' section moved to top (before Install)
- README: examples explicitly marked as 'real output - not fabricated'
- README: added 'Without MCPs' table showing what you get at each setup level
- README: Development Companion Mode clarified as session-scoped, with RESEARCH.md
  as the restore mechanism in new sessions

## [1.3.0] - 2026-05-07

### Added
- Phase 5: option C (let research decide language by star-weighted repo count)
- Phase 5: option D now has defined flow (ask base + changes, confirm before building)
- Phase 7: RESEARCH.md fallback when companion mode invoked in new session without prior context
- Phase 6 Step 5.5: entrypoint auto-detected from pyproject.toml / package.json / project name
- Phase 0: Scripts path detected via sysconfig, shell detected (PowerShell vs CMD), both PATH fix commands provided
- plugin.json: added Hebrew triggers to match SKILL.md

### Fixed
- CLAUDE.md: updated phase count from 7 to 8, removed stale "checkpoint between Phase 2 and 3" rule
- README.md: updated phase table to include Phase 0, added FEEDBACK.md to project structure
- CONTRIBUTING.md: added Phase 0 and smoke test to contributor verification checklist
- research_validator.py: header row was counted as a data row (inflated repo count by 1)
- research_validator.py: URL regex now strips trailing punctuation
- scaffold_generator.py: tier preserved when falling back to default language
- scaffold_generator.py: makedirs called before file loop as defensive measure
- eval_runner.py: path resolution uses abspath to fix CWD-dependent failures

## [1.2.1] - 2026-05-07

### Fixed
- Phase 0: explicit Windows PATH check - detects if Python Scripts folder is missing from PATH,
  provides exact fix command after any pip install
- Phase 6 Step 2: after install on Windows, immediately verify entrypoint is accessible;
  if not, provides both session-level and permanent PATH fix commands
- Phase 6 Step 1: .env configured interactively after scaffold - never leaves user with
  only .env.example and no guidance

## [1.2.0] - 2026-05-07

### Added
- **Phase 0 - Environment Probe**: before any research, detects OS, Python version, and
  package manager. Context is used in Phase 3 (OS-specific pitfalls) and Phase 6 (build backend)
- **Windows auto-pitfall check**: if OS is Windows, Unicode/encoding risks and path separator
  issues are automatically added to the pitfall watchlist in Phase 3
- **Mandatory smoke test (Phase 6 Step 5.5)**: entrypoint or test suite must exit 0 before
  the skill declares "Genesis Architect complete"
- **FEEDBACK.md**: field feedback from two real project runs (batch-rename, dev-log)

### Changed
- Phase 2 approval checkpoint and Phase 5 A/B choice merged into a single message - one
  confirmation instead of two
- Phase 0 runs even when `genesis init` skips Phase 1
- Version bumped to 1.2.0 in SKILL.md, plugin.json

## [1.1.0] - 2026-05-07

### Added
- **Phase 7 - Development Companion Mode**: after scaffolding, the skill stays active as a
  research partner throughout the project lifecycle
- **Language auto-detection**: skill now responds in the user's language (Hebrew, English, or any other)
- **`scripts/scaffold_generator.py`**: stdlib-only Python script that creates project structure
  for TypeScript, Python, Go, and Rust (minimalist + scalable tiers)
- **`scripts/research_validator.py`**: validates generated RESEARCH.md for completeness
- **`scripts/eval_runner.py`**: prints test queries and report templates for trigger-rate testing
- **`evals/test_queries.json`**: 31 test cases (18 should-trigger, 13 should-not-trigger)
- **`examples/typescript-cli/`**: real output example with RESEARCH.md, PITFALLS.md, ROADMAP.md
- **`assets/`**: output templates for RESEARCH.md, PITFALLS.md, ROADMAP.md
- **`plugin.json`**: machine-readable manifest for skill marketplaces
- **Go templates**: Minimalist and Scalable boilerplate in `references/architecture-patterns.md`
- **Rust templates**: Minimalist and Scalable boilerplate in `references/architecture-patterns.md`
- **YAML frontmatter** in SKILL.md (required by agentskills.io spec)
- README badges and structured installation one-liner

### Changed
- SKILL.md rewritten to be language-agnostic (removed hardcoded Hebrew prompts)
- Phase 2 search approval checkpoint improved with clearer table format
- Phase 6 now references `scaffold_generator.py` when available
- README completely restructured with phase table, file structure, and install one-liner

---

## [1.0.0] - 2026-05-07

### Added
- 6-phase workflow: Vision Alignment, Deep Discovery, Architecture Analysis,
  Pitfall Identification, Interactive Choice, Genesis Build
- `genesis init [vision]` explicit invocation command
- Research Approval Checkpoint between discovery and architecture phases
- Mandatory deliverables: RESEARCH.md, PITFALLS.md, ROADMAP.md
- Functional boilerplate templates for JavaScript/TypeScript and Python (Minimalist + Scalable)
- GitHub Actions CI/CD template
- MCP tool priority chain with graceful fallback (GitHub MCP → Exa → Firecrawl → Web search)
- Architect Mode for first-principles design when no comparable projects exist
- Engineering decision comment format for all generated code
