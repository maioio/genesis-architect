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

---

## Scores

### TypeScript CLI (measured - run 2026-05-07)

| Section | Points | Notes |
|---------|--------|-------|
| S1: Research Authenticity | 24/30 | 5 repo URLs format-valid (live verification pending). Issue URLs present for Pitfalls 1, 2, 4. Pitfall 3 cites "multiple repos" with no URL. Stars plausible. Commit dates within window. Quality Signal "Full" matches GitHub MCP. |
| S2: Pitfall Relevance | 21/25 | All 4 pitfalls are TS CLI-specific. Root causes present and mechanistic. Mitigations reference scaffold files by path. Pitfall 3 lacks a traceable issue URL. |
| S3: Scaffold Quality | 17/25 | ADR references specific repos. Streaming I/O default present. Structured logging and env validation not mentioned. Scaffold files not included in examples folder so test and .gitignore quality unverifiable. |
| S4: Phase Correctness | 10/20 | Research phase demonstrably ran. Hard gate, smoke test, archetype confirmation, and pre-flight check unverifiable from output files alone. |
| **Total** | **72/100** | Grade: Acceptable |

### Projected scores (need real runs to measure)

| Run | Project Type | S1 | S2 | S3 | S4 | Total | Basis |
|-----|-------------|----|----|----|----|-------|-------|
| 1 | Python CLI | 22 | 20 | 18 | 12 | 72 | Projected: Python ecosystem well-covered by GitHub MCP; pitfalls likely specific but venv/packaging edge cases may miss issue URLs |
| 2 | TypeScript CLI | 24 | 21 | 17 | 10 | **72** | Measured (see above) |
| 3 | Go service | 20 | 19 | 16 | 12 | 67 | Projected: Go template in architecture-patterns.md is thinner; fewer issue URL examples expected |
| 4 | Rust CLI | 19 | 18 | 15 | 12 | 64 | Projected: Rust template least mature; borrow-checker pitfalls risk being generic |
| 5 | React app | 22 | 20 | 18 | 12 | 72 | Projected: React ecosystem broad; pitfalls risk generic advice ("don't over-render") without strong issue mining |
| | **Average** | **21.4** | **19.6** | **16.8** | **11.6** | **69.4** | 1 measured + 4 projected |

---

Measured: 72/100 (TypeScript CLI). Projected average: 69/100. Target: 80+.
