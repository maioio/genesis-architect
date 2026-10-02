# Memory + Learning Engines

**Pro.** Genesis remembers what it learned about your project and gets better at
choosing research strategies over time.

## Memory Engine

No vector DB required. Per-project memory is plain Markdown + JSON under
`.genesis/`:

```
.genesis/
  project_memory.md          # what the project is, current state
  decision_log.md            # every significant decision + why
  research_history.md        # what was researched, when, result
  architecture_decisions.md  # ADRs — the drift baseline
  known_risks.md             # open risks, severity, status
  lessons_learned.md         # what worked, what did not
```

**Cross-session memory** restores context at the start of a new session, so you
never re-research a project you already worked on.

### Decision Journal (binding)

Every entry in `decision_log.md` records: the decision, the alternatives, the
evidence/sources, the confidence, *"what would change this,"* and an absolute
date + the loop step that produced it. **A decision with no journal entry is
treated as not made** — it must be re-derived.

## Learning Engine

The Learning Engine records which research **profiles** produced accepted
recommendations, and recommends the best one for a given kind of task.

```python
from genesis_architect_pro import (
    record_outcome, recommend_profile, write_lessons)

record_outcome("bug", "bug_hunter", accepted=True)
rec = recommend_profile("bug")
# rec.profile == "bug_hunter", rec.confidence == "low" (one sample)
write_lessons(".")          # → .genesis/lessons_learned.md digest
```

### Honest confidence

Scoring is deterministic (acceptance rate, ties broken by sample count) and
**confidence stays low until enough evidence accumulates**: `low` (≥1 sample),
`medium` (≥3), `high` (≥8). A perfect rate from one sample is never "high."

### Two scopes

- **Per-project** — outcomes feed back into the same project's next task
  immediately, from local files.
- **Cross-project** — only via anonymous, consented
  [telemetry](29_product_intelligence.md). Never from project code or content.
