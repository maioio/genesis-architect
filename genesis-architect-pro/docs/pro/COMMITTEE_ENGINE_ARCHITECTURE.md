# Committee Engine — Core Primitive Architecture

> **Status:** Architecture specification for integration into Genesis Core  
> **Version:** v1.0 | 2026-07-01  
> **Supersedes:** Standalone `llm-council` skill (external, unversioned)  
> **Target module:** `genesis_architect_pro.engines.committee`

---

## 0. Design Intent

The Committee engine was previously a standalone Claude skill (`~/.claude/skills/llm-council`).
This document defines its integration as a **first-class engine behind the GDE** — callable by
any mode, with behavior controlled by the license tier via Transparency Profiles.

The Committee is Genesis's anti-sycophancy primitive: when a decision is ambiguous, high-stakes,
or structurally complex, it runs the question through five advisors using **radically different
reasoning methods** (not just different role labels), forces peer-review, detects convergence vs.
manufactured consensus, and surfaces a verdict with honest confidence.

**Key invariant:** The Committee never produces a "confident" verdict from a single reasoning
thread. Divergence is a signal, not a failure.

---

## 1. Engine Contract (GDE Interface)

```python
@dataclass
class CommitteeRequest:
    question: str                         # The decision or architectural question
    context: CommitteeContext             # Evidence, code snippets, prior decisions
    mode: CommitteeMode                   # ARCHITECTURE | RESEARCH | GATE | RECOVERY | GENERAL
    urgency: Urgency                      # BLOCKING | HIGH | NORMAL | BACKGROUND
    transparency: TransparencyProfile     # FREE | PRO  (injected by license gate)
    max_rounds: int = 2                   # Debate rounds before synthesis

@dataclass
class CommitteeResult:
    verdict: str                          # The synthesized decision/recommendation
    confidence: float                     # 0.0–1.0 (calibrated, never inflated)
    consensus_type: ConsensusType         # EARNED | MANUFACTURED | DIVERGENT | SPLIT
    # PRO-only fields (None in FREE tier):
    advisor_positions: list[AdvisorPosition] | None
    peer_review_round: list[PeerReview] | None
    divergence_map: dict[str, float] | None
    voting_record: VotingRecord | None
    minority_view: str | None             # strongest dissent, if any
```

The GDE calls `committee_engine.run(request)` — it never calls advisors directly.

---

## 2. The Five Advisors

Based on Zhang et al. 2025 / Cambridge MAD 2026: homogeneous agents amplify errors.
Each advisor uses a **structurally different reasoning method**:

| Advisor | Reasoning Method | Blind Spot (known) |
|---------|-----------------|-------------------|
| **The Contrarian** | Inductive from failure cases — what went wrong in similar situations? | Pessimism bias; may over-weight tail risks |
| **The First Principles Thinker** | Deductive from base axioms — no analogies, no patterns | Misses domain-specific constraints |
| **The Expansionist** | Historical analogy across domains — what field solved this differently? | May import inapplicable context |
| **The Outsider** | Statistical base rates only — what does the prior distribution say? | Ignores project-specific signals |
| **The Executor** | Causal chain backward from desired outcome — what must be true for this to work? | May rationalize a conclusion |

Each advisor sees: the question, the mode context, and — in round 2 — the anonymized positions
of the other four (no attribution; prevents anchoring to authority).

---

## 3. Execution Pipeline

```
CommitteeRequest
       │
       ▼
[0] TRIAGE
  ├─ Fast path: question is unambiguous → skip Committee, return trivial verdict
  │   (confidence ≥ 0.85 from context alone)
  └─ Full path: proceed ↓

[1] POSITION ROUND (parallel)
  ├─ Advisor 1 (Contrarian)        → position + confidence
  ├─ Advisor 2 (First Principles)  → position + confidence  
  ├─ Advisor 3 (Expansionist)      → position + confidence
  ├─ Advisor 4 (Outsider)          → position + confidence
  └─ Advisor 5 (Executor)          → position + confidence

[2] ANONYMIZED PEER REVIEW (parallel, round 2 only if divergence > threshold)
  ├─ Each advisor sees the 4 anonymized positions
  ├─ Rates agreement (0–1) + states what would change their mind
  └─ May revise or reinforce their own position (logged separately)

[3] COLLAPSE DETECTION
  ├─ If ≥4 advisors converge after seeing each other → MANUFACTURED CONSENSUS flag
  ├─ If convergence emerged organically (pre-review) → EARNED CONSENSUS
  ├─ If 3:2 split remains → SPLIT verdict
  └─ If all diverge → DIVERGENT (escalate to human)

[4] SYNTHESIS
  ├─ Weighted by reasoning quality, not advisor "rank"
  ├─ Confidence inflation warning: if final confidence > any individual's → cap and warn
  └─ Minority view preserved if meaningful

[5] CommitteeResult
```

---

## 4. Transparency Profiles

This is the license-tier differentiation. The **engine runs identically** in both tiers —
only what is **exposed** differs.

### FREE: Abstracted Experience

```python
result = committee.run(request)

# What FREE users see:
print(result.verdict)           # "The architecture scorer should run before antipattern_detector"
print(result.confidence)        # 0.78
print(result.consensus_type)    # ConsensusType.EARNED
# result.advisor_positions   → None
# result.peer_review_round   → None
# result.divergence_map      → None
# result.voting_record       → None
# result.minority_view       → None
```

**UI surface (FREE):** A single recommendation card. "Committee reviewed this decision. Confidence: 78%."
No drill-down. The user gets the conclusion, not the process.

### PRO: Full Investigative Suite

```python
result = committee.run(request)

# All fields populated:
result.verdict              # synthesized decision
result.confidence           # 0.78
result.consensus_type       # ConsensusType.SPLIT  ← user knows it was close
result.advisor_positions    # [AdvisorPosition(advisor="Contrarian", stance="...", confidence=0.6), ...]
result.peer_review_round    # [PeerReview(reviewer="Outsider", target_position=1, agreement=0.3, ...), ...]
result.divergence_map       # {"Contrarian": 0.6, "Executor": 0.9, ...}
result.voting_record        # VotingRecord(for_=3, against=1, abstain=1)
result.minority_view        # "The Outsider notes that 70% of similar refactors introduce new coupling..."
```

**UI surface (PRO):** Full Committee panel in the Floating Assistant sidebar.
- Collapsible advisor cards (position + confidence per advisor)
- Divergence heatmap
- Voting record badge
- Minority view section (highlighted if confidence gap > 0.3)
- Decision Journal auto-entry

---

## 5. GDE Routing — When the Committee Is Called

The GDE invokes the Committee engine automatically in these conditions:

| Trigger | Mode | Escalation behavior |
|---------|------|-------------------|
| Intent classifier confidence < 0.55 | Any | Pause → Committee → re-classify |
| Architecture question with > 1 valid path | REFACTOR / BUILD | Run in background; show result before COMMIT |
| Gate vote is CONFIDENCE_LOW (< 0.40) | Any | Hard block → Committee required |
| User types "ask committee" / "council this" | Any | Immediate foreground Committee run |
| COMMITTEE mode classified by intent classifier | COMMITTEE | Full committee pipeline, all 5 advisors |
| Recovery plan has conflicting engine outputs | RECOVERY | Committee arbitrates the conflict |
| Two+ research paths with evidence split | RESEARCH | Committee evaluates evidence packs |

The Committee is **never** called for:
- Read-only operations (score, antipattern scan, C4 generation)
- Operations with a single valid execution path
- Operations already covered by a hard gate (PLAN_WRITE, RULES_FAIL)

---

## 6. COMMITTEE Mode — Full Pipeline (13 Engines)

When the GDE classifies intent as `COMMITTEE`, the full investigative suite runs:

```
Phase 1 (parallel):  import_graph → architecture_scorer → antipattern_detector → fragility_classifier
Phase 2 (parallel):  knowledge_graph (requires phase 1) → git_churn → drift_scorer
Phase 3:             committee_analysis (requires all of phase 1+2)
                     └─ runs all 5 advisors with full engine context
                     └─ divergence_detection
                     └─ synthesis → CommitteeResult
Phase 4:             decision_journal entry (auto)
```

---

## 7. Divergence Detection — Anti-Sycophancy

Collapse detection runs before synthesis:

```python
def detect_collapse(positions: list[AdvisorPosition], post_review: list[AdvisorPosition]) -> CollapseType:
    pre_variance = variance([p.confidence for p in positions])
    post_variance = variance([p.confidence for p in post_review])
    
    if post_variance < pre_variance * 0.3:
        # Positions converged dramatically after seeing peers → manufactured
        return CollapseType.MANUFACTURED
    
    agreement_rate = mean([p.agreement for p in post_review])
    if agreement_rate > 0.85 and pre_variance > 0.2:
        # High post-review agreement despite high pre-review variance → suspicious
        return CollapseType.MANUFACTURED
    
    return CollapseType.EARNED
```

If `MANUFACTURED`: confidence is capped at 0.65 and a warning is attached to the result.

---

## 8. Decision Journal Integration

Every Committee run auto-writes to `.genesis/gde_decision_log.jsonl`:

```json
{
  "session_id": "sess_abc123",
  "engine": "committee",
  "timestamp": "2026-07-01T14:23:00Z",
  "question": "Should we split the AuthModule god class or introduce a service layer?",
  "verdict": "Introduce a service layer first; split after tests are green",
  "confidence": 0.74,
  "consensus_type": "SPLIT",
  "minority_view": "The Contrarian argues splitting first reduces regression risk",
  "what_would_change_it": "If test coverage < 40%, the Contrarian position gains weight",
  "transparency": "PRO",
  "advisor_count": 5,
  "rounds": 2
}
```

FREE tier: same entry, `advisor_positions` field omitted.

---

## 9. Implementation Checklist

- [ ] `genesis_architect_pro/engines/committee/__init__.py`
- [ ] `genesis_architect_pro/engines/committee/types.py` — all dataclasses
- [ ] `genesis_architect_pro/engines/committee/advisors.py` — 5 advisor prompt templates
- [ ] `genesis_architect_pro/engines/committee/pipeline.py` — position → peer-review → synthesis
- [ ] `genesis_architect_pro/engines/committee/collapse_detector.py`
- [ ] `genesis_architect_pro/engines/committee/transparency.py` — FREE/PRO field masking
- [ ] `genesis_architect_pro/engines/committee/journal.py` — auto decision log entry
- [ ] GDE engine registry: register `committee` with deps `[knowledge_graph, antipattern_detector]`
- [ ] Intent classifier: add COMMITTEE mode signal expansion
- [ ] Gate policy: add `COMMITTEE_REQUIRED` gate (soft block, overridable by PRO users only)
- [ ] Tests: 15 unit + 3 integration (earned vs. manufactured consensus; FREE vs. PRO masking)

---

## 10. Market Differentiation

No competing tool (Cursor, Cline, Aider, Copilot Workspace, Devin, SWE-agent, OpenHands,
AutoCodeRover, Sweep, Cody, Continue) has a structured multi-advisor debate layer with:
- Anti-sycophancy architecture (distinct reasoning methods, not role labels)
- Collapse detection (earned vs. manufactured consensus)
- License-tiered transparency
- Automatic Decision Journal integration
- GDE-native routing (no user prompt required)

**The moat:** competitors either use a single LLM pass (one perspective) or a "team of agents"
with homogeneous prompts (mathematically equivalent to majority voting, per Zhang et al. 2025).
Genesis Committee is the only tool with structurally forced disagreement.
