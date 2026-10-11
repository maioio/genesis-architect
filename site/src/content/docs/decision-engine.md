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
4. **Gate.** Proposed writes pass through the approval gate. See the [approval model](../approval-model/).
5. **Log.** The decision log is saved. `genesis explain` prints the last one.

`--classify-only` stops after step 1, so you can see which engines a sentence would reach without running any.

`genesis engines` lists every engine and the command that reaches it.
