# The Five Principles + the Honesty Clause

Everything Genesis does follows five principles. They are not slogans — they are
enforced in the engines.

## 1. Research-first
Genesis does not write code before it knows the landscape. It searches official
docs, source, security databases, and the field before recommending an approach.

## 2. Evidence-first
Every significant recommendation carries an [Evidence Pack](12_evidence_packs.md):
sources, confidence, and any contradictions found. A claim without evidence is
flagged as such.

## 3. Decision-first
The [Decision Engine](22_decision_engine.md) does not just present options — it
recommends one, with trade-offs, a confidence level, and *"what would change
this."*

## 4. Progressive autonomy
Genesis earns trust gradually: **Guided → Assisted → Trusted → Autonomous.**
Dangerous actions are **always** gated for approval, at every level — even
Autonomous. See [Governance](26_governance.md).

## 5. Continuous learning
Genesis learns which strategies actually worked and adjusts. Per-project lessons
feed back immediately; cross-project learning happens only via anonymous,
consented telemetry. See [Memory + Learning](24_memory_learning.md).

## The honesty clause (binding)

> If a source is empty, unreachable, or failed, Genesis reports it as
> **unavailable** — it never fabricates data to fill a gap.

Concretely:
- An engine that cannot run returns a low-confidence, *degraded* result with a
  warning — it does not raise and does not invent output.
- Offline, network-backed research is marked **unavailable** in the Evidence
  Pack; local analysis continues. See [Offline mode](52_offline.md).
- A link in the Knowledge Graph with no basis is low-confidence by construction.
- Confidence is never "high" without supporting evidence, no matter how large
  the apparent gap between options.
