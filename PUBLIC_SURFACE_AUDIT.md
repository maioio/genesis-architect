# Public Surface Audit (Phase A)

Audit date: 2026-10-11. Base: `origin/main` at 71e5ccf (PR #64 merged). Working branch: `feat/public-surface-v1`, worktree `genesis-public-surface` (the owner's PRE-v10 worktrees were not touched).

This file is a planning artifact. It is deleted or moved to `docs/archive/` before the PR.

## 1. Root inventory (tracked, at audit time)

| File | Role | Decision |
|---|---|---|
| README.md, LICENSE, CHANGELOG.md, pyproject.toml, CLAUDE.md, SKILL.md, manifest.json, plugin.json, sonar-project.properties, .editorconfig, .gitattributes, .gitignore, .gitleaks.toml | Ecosystem-convention files | Keep in root |
| CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md | Community health | Keep in root (see 6) |
| ARCHITECTURE.md | Mechanism doc | Move to docs/architecture/overview.md |
| SELF_RESEARCH.md, SELF_PITFALLS.md, SELF_ROADMAP.md | Inputs for the self-audit run in CI | Move to docs/self-audit/ |
| ARCHITECTURE_EVIDENCE.md | Output of the self-audit | Keep in root (blocker B1) |
| ARCHITECTURE_INVARIANTS.json | Generated structural facts | Keep in root for now (blocker B2) |
| WEBSITE_COPY.md | Landing copy | Move to site/content/website-copy.md when site/ exists |
| PUBLIC_SURFACE_AUDIT.md | This file | Temporary |

Directories: .claude, .github, assets, case_studies, docker, docs, evals, examples, genesis-architect-pro (historical, never deleted), references, scripts, src, tests, validation. 769 tracked files.

## 2. Current website: source, build, deploy

- Pages config (from the GitHub API): `build_type: legacy`, source `main:/docs`. It is a Jekyll-legacy publish of whatever is committed in `docs/`.
- `docs/index.html` is a 16-line React shell that loads `docs/assets/index-PlI8H8p2.js` (minified Vite bundle) and `index-BzCqOy_V.css`.
- The source of that bundle is NOT in this repository. `ci.yml:152` and `WEBSITE_COPY.md:3` name a separate `genesis-react` repo, built by hand and copied in. I could not recover it. Since 2026-10-11 the bundle has been hand-patched twice at byte level (PR #64): this is exactly the practice the spec forbids, and it ends with Phase D.
- `docs/_demos/` (8 HTML files plus `_build.py`) contains old landing mockups with "$9/mo" Gumroad pricing. They return 404 on the live site (legacy Jekyll skips underscore directories), but they are tracked in the repo and one `gh api` listing away from a reader.
- No site tests, no link check, no accessibility check, no Lighthouse run exist today. The em-dash check explicitly excludes `docs/`.

## 3. Claim contradictions

| Claim | Where | Value | Truth |
|---|---|---|---|
| Tests | README.md:290 | 2852 | 2852 collected today (verified: `pytest --collect-only`) |
| Tests | WEBSITE_COPY.md:38 | 2,845 | stale |
| Engines | built site bundle (7 strings) | 19 | ARCHITECTURE_INVARIANTS.json: 19 |
| Engines | docker/capability_audit.py:545-553 | "17 engines registered" | contradicts invariants (19) |
| Gates | docker/capability_audit.py:556 | "12 approval gates" | invariants: 14 |
| Engines | built site bundle (1 string) | 8 | historical changelog entry |
| Sources | docker/capability_audit.py:464 | 30 sources, 11 tiers | matches invariants |
| Version badge | built site bundle | v9.0 (after PR #64) | matches |
| Quality score | manifest.json | "78/100 (measured)" | not reproducible from a command; unverified |

The capability audit is a runtime-adjacent script under `docker/`. Its disagreement with the invariants is a real finding: either it is stale or the invariants count differently. I will report it and not edit it (spec: no runtime changes to make claims true).

## 4. Version and metadata contradictions

| Field | pyproject.toml | manifest.json | plugin.json | PyPI | GitHub Release |
|---|---|---|---|---|---|
| version | 9.0.0 | 8.0.0 | 8.0.0 | 9.0.0 | v9.0.0 (Latest) |
| homepage | github.com/maioio/genesis-architect | same | github.com/maioio-projects/genesis-architect | same | |
| repository | same | | github.com/maioio-projects/genesis-architect | | |

Other stale text: manifest.json description says "The only scaffolder that verifies its sources before building" (scaffolder-only framing, plus a superlative); plugin.json says "the AI Software Architect that researches before it builds". pyproject.toml description still ends "Dual-licensed (AGPL-3.0 + Commercial)". README says a commercial license exists; SECURITY.md says "no paid tier". These are compatible (dual licensing is not a paid product tier) but the wording must be consistent.

The GitHub About description already carries a strong claim ("Zero import cycles, zero critical anti-patterns - measured against itself") that is backed by the invariants file.

## 5. Stale URLs, paid-tier wording

- `maioio-projects` URLs: plugin.json:8-9 only (2 hits, outside CHANGELOG).
- Paid-tier wording: docs/_demos/*.html and `_build.py` ($9/mo, Gumroad link, "Get Pro"); docs/archive/GUMROAD_RETIREMENT.md (historical, fine). README, SECURITY and WEBSITE_COPY correctly say there is no paid tier.

## 6. Proposed moves and blockers

Reference search covered: .github, README, SKILL.md, src, scripts, tests, docker, references, docs, pyproject, sonar properties.

| Move | References to update | Blocker |
|---|---|---|
| ARCHITECTURE.md to docs/architecture/overview.md | README (5 links, 1 tree), ci.yml:126,156, docs/archive/README.md | none |
| SELF_RESEARCH/PITFALLS/ROADMAP.md to docs/self-audit/{research,pitfalls,roadmap}.md | ci.yml:114-122 only (CLI arguments) | none |
| WEBSITE_COPY.md to site/content/website-copy.md | ci.yml:156, its own header | needs site/ (Phase D) |
| ARCHITECTURE_EVIDENCE.md | | **B1**: `evidence_pack.py` and `genesis_state.py` hard-code `<project>/ARCHITECTURE_EVIDENCE.md`, and CI regenerates it at the root. Moving the tracked copy leaves a regenerated duplicate at the root. Fixing that is a runtime change, which is out of scope. |
| ARCHITECTURE_INVARIANTS.json to data/ | scripts/architecture_invariants.py:31, tests/test_architecture_invariants.py:20, docker/Dockerfile.test:35, README (3), ci.yml:125 | **B2**: README promises agents can parse this file at a stable path; raw-URL consumers are unknown and the move would silently break them. Defer to a release that announces it. |
| CONTRIBUTING/SECURITY/CODE_OF_CONDUCT to .github/ | README links, ci.yml:155, PyPI long description links | **B3**: GitHub accepts both locations, so the move buys only a shorter root and risks the PyPI/README relative links and the security-advisory link. Kept. |
| manifest.json, plugin.json | | marketplace and skill registries read them from root. Kept. |
| assets/ split | demo_tools, templates (used by runtime? `assets/*.template.md` are read by scaffolding) | **B4**: not moved. Template files may be loaded by `src/`; a dedicated verified migration is needed. |

Root after Phase C: 13 convention files, 3 community files, ARCHITECTURE_EVIDENCE.md, ARCHITECTURE_INVARIANTS.json, plus directories. That removes 5 files from root (ARCHITECTURE.md, three SELF_*, WEBSITE_COPY.md).

## 7. Workflow overlap and gaps

Existing: `ci.yml` (quality gates matrix, packaged install, build artifacts, gitleaks, Sonar, Snyk), `codeql.yml`, `publish.yml` (PyPI on tag), Dependabot, CODEOWNERS (`* @maioio`).

Gaps for the public surface: no site build, no link check, no markdown lint, no accessibility or E2E, no claim-drift validator, no metadata validator. Not needed: a second secret scanner or SAST (gitleaks, CodeQL and Snyk already cover them). Candidates to evaluate: lychee (links), markdownlint-cli2, actionlint, zizmor. Release Drafter and OpenSSF Scorecard are optional; neither changes the public surface much.

Known operational issue (not part of this work): the required check "Dependency Security (Snyk)" is skipped, so every PR needs an admin merge.

## 8. Repository and release surface

- GitHub: Discussions on, Issues on, 17 topics, homepage set, About description set. Social preview: not verifiable through the API; recommend manual check.
- Issue templates: bug_report.yml, feature_request.yml only. PR template is SKILL.md-centric ("Which phase or file does this affect", "SKILL.md stays under 480 lines").
- Releases: v9.0.0 is Latest and matches PyPI 9.0.0. Open PRs: 15, including #65 and #66 (docs), #59 README accuracy, #58, #60 and several Dependabot bumps. #66 touches the README install lines this rebuild will rewrite; the rebuild supersedes it.

## 9. Target architecture (what this branch will deliver)

```text
data/public-product-facts.json          generated; validated in CI
scripts/public_surface/                 generate_product_facts.py, validate_public_claims.py
docs/architecture/overview.md           moved
docs/self-audit/{research,pitfalls,roadmap}.md   moved
site/                                   tracked source, static export
.github/ISSUE_TEMPLATE/                 + docs, evidence-correction, integration proposal, config.yml
.github/PULL_REQUEST_TEMPLATE.md        project-wide
.github/workflows/public-surface.yml    new, additive
```

Deployment cutover (Phase G) and every remote action wait for owner approval.
