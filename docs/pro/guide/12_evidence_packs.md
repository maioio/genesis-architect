# Evidence Packs

**Pro.** Every significant recommendation carries an Evidence Pack — the proof
behind the advice.

## What's in one

| Field | Meaning |
|-------|---------|
| **Sources** | Every source consulted, with its category + reliability score. |
| **Confidence** | How sure Genesis is — never "high" without supporting evidence. |
| **Contradictions** | Where sources disagree, surfaced rather than hidden. |
| **Recommendation** | The conclusion, with *"what would change it."* |

## How to read it

- **Reliability vs confidence.** Reliability is a property of a *source*
  (official docs = 100); confidence is Genesis's certainty in the *conclusion*
  given all sources. A field-only finding caps confidence lower than an
  official-docs-backed one.
- **Contradictions are a feature.** If Stack Overflow says one thing and the
  changelog says another, the pack shows both and explains which it trusts and
  why.
- **Honesty clause.** If a source was unreachable (e.g. offline), it is listed as
  **unavailable** — the pack never fabricates a citation. See
  [Offline mode](52_offline.md).

Evidence Packs are stored under `.genesis/evidence_packs/`, one file per pack, so
a recommendation's basis is always auditable later.
