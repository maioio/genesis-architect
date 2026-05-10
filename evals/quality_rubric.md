# Genesis Architect - Output Quality Rubric

Human review checklist for evaluating real genesis-architect runs. Score 5 runs and average.

---

## Section 1: Research Authenticity (30 points)

- [ ] Every repo in RESEARCH.md table exists on GitHub (run `--verify-repos`)
- [ ] Every issue URL in PITFALLS.md returns HTTP 200 (run `--verify-issues`)
- [ ] Star counts are plausible (within 2x of actual at time of run)
- [ ] Last commit dates fall within the stated 12-month recency window
- [ ] Research Quality Signal matches actual tool availability (FULL if GitHub MCP was used, PARTIAL if web-only)

**Score: __ / 30**

---

## Section 2: Pitfall Relevance (25 points)

- [ ] Each pitfall is specific to the project type (not generic advice like "don't hardcode secrets")
- [ ] Root cause explains WHY the failure happens, not just WHAT breaks
- [ ] Mitigation is visible in the actual scaffold code (grep for the pattern)
- [ ] At least 2 of 3+ pitfalls came from real Issue mining, not "known anti-patterns"

**Score: __ / 25**

---

## Section 3: Scaffold Quality (25 points)

- [ ] Unit tests verify actual behavior (input to expected output), not just "does not throw"
- [ ] Production defaults present: structured logging, env validation, non-root Docker (if applicable)
- [ ] ADR explains choices with reference to specific repos from RESEARCH.md
- [ ] .gitignore is appropriate for the language (no secrets or build artifacts committed)

**Score: __ / 25**

---

## Section 4: Phase Correctness (20 points)

- [ ] Pre-flight check ran and result was displayed (or `genesis init` was used explicitly)
- [ ] Archetype (Minimalist vs Scalable) was confirmed by user before build started
- [ ] Research Quality Signal displayed before Phase 5 choice prompt
- [ ] Hard gate enforced: explicit A/B/C/D selection received before any files were created
- [ ] Smoke test passed before git commit

**Score: __ / 20**

---

## Scoring Guide

| Range | Grade | Meaning |
|-------|-------|---------|
| 90-100 | Excellent | Production-ready output, all gates enforced |
| 75-89 | Good | Minor gaps, acceptable for shipping |
| 60-74 | Acceptable | Research thin or pitfalls generic |
| < 60 | Needs improvement | Fabricated data or missing hard gates |

---

## How to Use

1. Run genesis-architect on 5 different project types: Python CLI, TypeScript API, Go service, Rust CLI, React app.
2. Score each run independently using the four sections above.
3. Record scores in the table below.
4. Average score must be >= 80 before publishing a new major version.

| Run | Project Type | S1 | S2 | S3 | S4 | Total |
|-----|-------------|----|----|----|----|-------|
| 1 | Python CLI | | | | | |
| 2 | TypeScript API | | | | | |
| 3 | Go service | | | | | |
| 4 | Rust CLI | | | | | |
| 5 | React app | | | | | |
| | **Average** | | | | | |
