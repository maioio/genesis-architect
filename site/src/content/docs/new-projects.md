---
title: New projects
description: What genesis init does before it writes a single file.
---

```bash
genesis init a Python CLI for analyzing log files
```

Keep the description short. Long descriptions match nothing on GitHub.

## What happens

1. **Research.** Genesis searches GitHub for repositories like the one you describe.
2. **Mining.** It reads closed issues, forks and post-mortems from those repositories and extracts the failures that recur.
3. **Choice.** It shows the pitfalls it found and offers architecture options. You choose.
4. **Scaffold.** It writes the project with the mitigations already in place, plus `RESEARCH.md`, `PITFALLS.md` and `ROADMAP.md` that record what it found.

Every pitfall in `PITFALLS.md` links to the issue it came from. A claim without a retrievable source is rejected by the citation validator rather than written down.

## What it sends

The project description goes to GitHub search and to your configured LLM. For confidential work, point the LLM setting at a local model, or skip `init` and write the specification by hand.

See [Research and evidence](../research-and-evidence/) for how sources are checked.
