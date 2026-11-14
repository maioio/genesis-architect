---
title: Decision engine
description: How one sentence is routed to the right engines.
---

```bash
genesis decide "diagnose the project"
genesis decide --classify-only "refactor the CLI module"
```

## Flow

1. **Classify.** The intent classifier maps the instruction onto a mode.
2. **Route.** The engines for that mode run, in parallel unless you pass `--serial`.
3. **Critique.** The red-team critic attacks the plan and separates evidence from inference.
4. **Gate checks, then approval.** The gate checks run first; a hard block stops the session before any proposed write is executed. Otherwise the proposed writes go to you for approval. See the [approval model](../approval-model/).
5. **Log.** The decision log is saved. `genesis explain` prints the last one.

Other options: `--resume` continues a saved session, `--yes` approves every proposed write (CI mode), `--no-commit` stops after analysis, and `--json` prints structured output and implies `--no-commit`.

`--classify-only` stops after step 1, so you can see which engines a sentence would reach without running any.

`genesis engines` lists every engine and the command that reaches it.
