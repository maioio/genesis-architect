---
title: New projects
description: What genesis init does before it writes a single file.
---

```bash
genesis init a Python CLI for analyzing log files
```

Keep the description short. Long descriptions match nothing on GitHub.

## What happens

This is what the standalone `genesis init` command does. Its research is GitHub only.

1. **Research.** Genesis searches GitHub for repositories like the one you describe.
2. **Mining.** It reads issues from the top matches and extracts the failures that recur.
3. **Choice.** It shows the pitfalls it found and offers architecture options. You choose.
4. **Scaffold.** It writes the project with the mitigations already in place, plus `RESEARCH.md`, `PITFALLS.md` and `ROADMAP.md` that record what it found.

Every pitfall in `PITFALLS.md` links to the issue it came from. A claim without a retrievable source is rejected by the citation validator rather than written down.

## What it sends

The project description goes to GitHub search and to your configured LLM. For confidential work, point the LLM setting at a local model, or skip `init` and write the specification by hand.

## Deeper discovery as an agent skill

When Genesis runs as an agent skill, the agent follows a broader discovery workflow that the CLI does not run itself. It combines GitHub repositories and issue mining with ecosystem and community search, package and security data, and video metadata, to whatever extent the host agent has those tools. See [Research and evidence](../research-and-evidence/) for the split, and for how sources are checked.
