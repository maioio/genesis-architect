# The Source Registry + Research Profiles

## Source Registry

Genesis does not hard-code its sources. They live in a registry
(`.genesis/knowledge/research_sources.yaml`, with per-project overrides), each
with a category, role, and reliability score. **New sources can be added without
changing the research engine** — the pipeline reads the registry.

This is how Engineering Source Intelligence, Research Intelligence, and Developer
Field Intelligence stay configurable and ranked.

## The 9 research profiles

A profile tunes which sources the pipeline prioritizes for a kind of task. The
[Learning Engine](24_memory_learning.md) tracks which profile actually produces
accepted recommendations for each task kind.

| Profile | Use it for |
|---------|-----------|
| `deep_research` | Broad, thorough investigation of an unfamiliar area |
| `bug_hunter` | Tracking down a specific defect / regression |
| `architecture_review` | Evaluating structure, coupling, layering |
| `security_review` | Threat modeling, CVEs, dependency risk |
| `performance_review` | Bottlenecks, scaling, profiling guidance |
| `migration_planner` | Moving frameworks / versions / platforms |
| `recovery_mode` | Diagnosing and recovering a legacy codebase |
| `ai_model_comparison` | Comparing models / providers |
| `library_evaluation` | "Should we adopt X?" with field evidence |

```python
from genesis_architect_pro import recommend_profile
recommend_profile("migration")   # learned best profile for migration tasks
```
