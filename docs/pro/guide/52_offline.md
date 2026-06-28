# Offline / Degraded Mode

Genesis is useful with no network at all, and **honest** about what it can't do
offline.

## Works fully offline (local analysis)

import graph · architecture score · anti-patterns · C4 diagrams · drift
detection · recovery report · `genesis gate` · knowledge graph · decision engine.

None of these need the network.

## Needs the network

research intelligence · developer field intelligence (Reddit / SO / HN) · YouTube
transcript learning · CVE / OSV lookups.

## What happens offline (honesty clause)

> Network-backed sources are marked **unavailable** in the Evidence Pack. Local
> analysis continues. Genesis never blocks, and never fabricates a result to
> cover a missing source.

```python
from genesis_architect_pro import offline_capability_report
rep = offline_capability_report(network_available=False)
rep["available"]     # all local capabilities
rep["unavailable"]   # the network ones, honestly listed
```

## Self-healing

- Missing optional dep (e.g. ffmpeg) → detected and offered for one-prompt
  install, or guided — never a crash.
- Corrupt `.genesis/` cache → rebuilt automatically from source (read-only
  re-analysis).
- Bad update → rollback to the previous version.
