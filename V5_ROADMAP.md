# Genesis V5 Architecture Roadmap

**Status:** Planning
**Decision date:** 2026-05-30
**Author:** Maio + Claude

---

## The Risk We Are Managing

The spec is ambitious. The failure mode is clear:

```
Phase 1 + Phase 2 + Phase 3 + ... + Phase 11
= 40 files, 800-line SKILL.md, 0 working product
```

The governing rule for V5:

**Every capability that goes into SKILL.md must be validated on a real project before the next capability is added.**

---

## Core Insight

Genesis V4 answers: "How should I build this?"
Genesis V5 must answer: "Should I build this, and what exactly?"

The shift is from **Research -> Code** to **Research -> Decision -> Code**.

Development Partner Mode is the mechanism that enforces this shift.

---

## Current State (V4 baseline)

SKILL.md: **399/400 lines** - zero budget for additions without cuts.

What exists today:
- Phase 0: Environment probe
- Phase 0.5: Quick Scaffold vs Full Genesis choice
- Phase 1: Vision Alignment (4 A/B/C/D questions)
- Phase 2: Deep Discovery (GitHub repos + issues)
- Phase 3: Architecture Analysis
- Phase 4: Pitfall Identification (Implementation Extraction)
- Phase 5: Interactive Architecture Choice
- Phase 6: Genesis Build (9 steps, Implementation Extraction)
- Phase 7: Development Companion Mode (genesis check/resolve/research/help)

What is missing for V5:
- Experience Selection (Fast / Professional / Founder / Auto)
- Product Discovery ("Should I build this?" before "How?")
- Commercial Intelligence (SaaS, extensions, paid tools)
- Market Gap Analysis
- Project Recovery
- Fragility Analysis
- Long-term Project Memory
- Development Partner enforcement (questions before major decisions)

---

## V5 Implementation Plan

### Constraint: SKILL.md must stay under 400 lines

Every new capability requires either:
1. Removing existing lines
2. Compressing existing phases
3. Splitting SKILL.md into SKILL.md (behavior) + SKILL_REFERENCE.md (templates/examples)

The current Phase 6 uses ~100 lines for 9 steps. This is a compression candidate.

---

## Phase V5.1 - Development Partner Mode (implement first)

**Why first:** Highest impact, lowest complexity. Touches existing Phase 0.5 and Phase 1.

**What changes:**

Replace Phase 0.5 (currently: Quick Scaffold vs Full Genesis) with Experience Selection:

```
A. Fast Build Mode      - 3-5 questions, quick MVP
B. Professional Mode    - 5-10 questions, structured project  [Recommended]
C. Founder Mode         - 10-20 questions, full product strategy
D. Auto Select          - Genesis analyzes and recommends
```

Add Development Partner rules:
- Before major architecture decision: present A/B/C/D options + recommended + why
- Before major product decision: same
- Genesis cannot silently choose between two real alternatives
- User can always choose "go with your recommendation" to skip

Question format (enforced):

```
[Question text]

A. [Option]
B. [Option]
C. [Option]  [Recommended]
D. [Option]

Why [C] is recommended: [one sentence]
Tradeoff if you choose differently: [one sentence]
```

**What does NOT change:** Phase 2, 3, 4, 5, 6, 7 - untouched.

**SKILL.md budget:** Phase 0.5 is currently ~14 lines. Replace with ~20 lines. Net: +6 lines.
This requires compressing 6 lines elsewhere (Phase 6 has candidates).

**Tests to add:**
- `test_partner_question_has_abcd_options`
- `test_partner_question_has_recommended_field`
- `test_partner_default_continues_on_no_answer`
- `test_experience_selection_affects_question_count`

**Command:**
```
genesis init --partner [description]
```
Or integrate into default flow as the first question.

**Validation:** Run on one real project. Count how many times Genesis asked vs decided silently.

---

## Phase V5.2 - Product Discovery Layer (implement second)

**Why second:** "Should I build this?" before "How to build it?"

**New phase: Phase 0.8 - Product Discovery**
Runs between Experience Selection and Phase 1.

Questions in this phase (Founder Mode only, or when user says "I have an idea"):
1. What problem does this solve? (open answer)
2. Who specifically has this problem? (user type)
3. Does a solution already exist? (Genesis researches before answering)
4. Why would users choose your version? (differentiator)
5. What is the smallest thing that proves the idea works? (MVP definition)

Genesis output from Phase 0.8:
- **Go / Pivot / Stop** recommendation with reasoning
- If Stop: specific reason (market saturated, problem doesn't exist, etc.)
- If Pivot: concrete alternative to consider
- If Go: proceed to Phase 1 with pre-filled answers

**SKILL.md budget:** New phase ~15 lines. Requires compressing 15 lines elsewhere.

**Compression candidates:**
- Phase 3 Windows pitfall watchlist: move to SKILL_REFERENCE.md (saves ~8 lines)
- Phase 6 step numbering: consolidate 3b/6.5/7b into parent steps (saves ~5 lines)
- Phase 7 sub-commands: compress to 4 lines instead of 12 (saves ~8 lines)

Total savings: ~21 lines. Budget for Phase 0.8: 15 lines. Net: 6 lines to spare.

**Validation:** Run on a project where the answer is "don't build this." Verify Genesis says it.

---

## Phase V5.3 - Commercial Intelligence (implement third)

**What it adds:** Research SaaS, paid tools, and browser extensions - not just GitHub.

**Currently:** Phase 2 searches GitHub repos only.

**Change:** Stream D (new) in Phase 2:
- Search Product Hunt, G2, Capterra for similar commercial products
- Extract: pricing, user complaints, feature gaps
- Add to RESEARCH.md: "Commercial Landscape" section

**New output section in RESEARCH.md:**
```markdown
## Commercial Landscape
[3-5 commercial products in this space]
[User complaints from reviews]
[Opportunities not covered by existing products]
```

**SKILL.md budget:** ~8 lines for Stream D description. Requires 8 lines elsewhere.

**Validation:** Run on a SaaS project idea. Verify the commercial section contains real products.

---

## Phase V5.4 - Project Recovery Mode (implement fourth)

**Command:**
```
genesis recover [path]
```

**What it does:**
1. Analyzes existing project: reads all source files, tests, CI, dependencies
2. Runs fragility analysis: identifies what is likely to break
3. Identifies architecture problems: God classes, no tests, hardcoded values
4. Generates recovery plan: what to fix, in what order, with what effort

**Outputs:**
- `PROJECT_RECOVERY_REPORT.md`
- `FRAGILITY_MAP.md`

**SKILL.md budget:** ~12 lines. No compression needed - this is a new command at the Invocation section level, similar to `genesis audit`.

**Validation:** Run on an existing project with known technical debt. Verify the report identifies real problems.

---

## Phase V5.5 - Long-term Project Memory (implement fifth, last)

**What it adds:** Genesis remembers decisions across sessions.

**Storage:** `.genesis/project_intelligence.md`

**Tracked:**
- Major decisions made and why
- Rejected alternatives and why rejected
- Architecture pivots
- Recurring failures
- Lessons learned

**How it works:**
- After Phase 6: Genesis writes a decision log entry to `.genesis/project_intelligence.md`
- On new session: Genesis reads this file before starting
- On `genesis resolve`: Genesis checks here before Stack Overflow

**SKILL.md budget:** ~6 lines. Minimal - it's an addition to Phase 6 Step 9 (Summary) and Phase 7 (new session restore).

**Validation:** Run two sessions on the same project. Verify the second session references decisions from the first.

---

## What Is NOT in V5

The following capabilities from the spec are explicitly deferred or rejected:

| Capability | Decision | Reason |
|---|---|---|
| COMPETITOR_REPORT.md as separate file | Deferred | Commercial Intelligence (V5.3) covers this inside RESEARCH.md - separate file is overhead |
| MARKET_GAP_REPORT.md as separate file | Deferred | Same - the gap analysis goes in RESEARCH.md |
| PRODUCT_STRATEGY.md as separate file | Deferred | Phase 0.8 Product Discovery covers this inline |
| NEXT_GENERATION_ARCHITECTURE.md | Rejected for V5 | Too speculative - adds complexity without clear use case |
| Phases 9, 10 from original spec | Deferred to V6 | Fragility analysis is covered in Project Recovery (V5.4) |
| genesis update / genesis migrate | Deferred | Not in V5 scope |

These are not abandoned - they belong in V6 once V5 is validated.

---

## Implementation Order and Gates

Each phase must be validated before the next begins.

```
V5.1 Development Partner Mode
  Gate: Run on 1 real project, verify questions are asked before major decisions
  
V5.2 Product Discovery Layer  
  Gate: Run on 1 project where Genesis recommends Stop or Pivot. Verify it does.
  
V5.3 Commercial Intelligence
  Gate: Run on 1 SaaS idea. Verify RESEARCH.md contains commercial product analysis.
  
V5.4 Project Recovery Mode
  Gate: Run on a project with real debt. Verify FRAGILITY_MAP.md identifies real problems.
  
V5.5 Long-term Project Memory
  Gate: Run two sessions on the same project. Verify session 2 references session 1 decisions.
```

---

## SKILL.md Budget Plan

Current: 399 lines. Hard limit: 400.

Planned additions:
- V5.1 Development Partner: +6 net (replace Phase 0.5, 20 lines new vs 14 current)
- V5.2 Product Discovery: 0 net (compress 21, add 15)
- V5.3 Commercial Intelligence: 0 net (compress 8, add 8)
- V5.4 Project Recovery: +12 (new command, no compression needed)
- V5.5 Long-term Memory: +6

Total additions: +24 lines.
Total compressions needed: ~24 lines.

This is tight but achievable without destroying existing functionality.
The key move: split long reference content into SKILL_REFERENCE.md.

---

## The Question Genesis Must Answer for V5

Before building anything, Genesis should be able to answer:

1. Should you build this? (Product Discovery)
2. Who already built it? (Commercial Intelligence)
3. What is the minimum version that proves the idea? (MVP definition)
4. How should it be built? (existing V4 capability)
5. What will break? (Pitfall Extraction - existing V4 capability)
6. Is it still working? (Companion Mode - existing V4 capability)
7. How do I recover it if it breaks? (Project Recovery - V5.4)

Genesis V4 answers questions 4, 5, 6.
Genesis V5 adds questions 1, 2, 3, 7.

---

## Success Criteria

Genesis V5 succeeds when:

1. A user with an idea gets a Go/Pivot/Stop recommendation before any code is generated.
2. A user making an architecture decision sees options A/B/C/D with a recommended default.
3. A user with a broken project gets a recovery plan from `genesis recover`.
4. Genesis does not add a single feature that cannot be validated on a real project.

---

## V5.1 Status: COMPLETE

Implemented 2026-05-30. Validated with 14 tests (test_partner_mode.py). All 386 tests green.

## Next Step

Implement V5.2 (Product Discovery Layer) - requires Design Review first.

Changes required:
1. SKILL.md: Replace Phase 0.5 with Experience Selection + Development Partner question format
2. tests/: 4 new tests for question format validation
3. README.md: Example interaction showing A/B/C/D question flow
4. `genesis init --partner` command entry in SKILL.md Invocation section

Do not touch V5.2-V5.5 until V5.1 is validated.
