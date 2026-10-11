---
title: Existing projects
description: Diagnose a project you already have, without changing it.
---

```bash
genesis recover .            # drift, broken imports, anti-patterns, fragile modules
genesis harden .             # STRIDE threat model, OWASP Top 10 checklist, secrets scan
genesis deps .               # third-party imports per module and their advisories
```

`recover` and `harden` accept `--json` for machine-readable output and `--no-commit` to guarantee that nothing is written.

## What `recover` reports

- Import cycles and the modules that sit on them.
- Anti-patterns, with severity. Critical ones are counted separately.
- An architecture score from 0 to 100, with the dimension breakdown.
- Fragile modules.

## What it does not do

Genesis never executes code from the project it analyzes. It reads source files and the import graph. Writes happen only after an explicit approval step, described in the [approval model](../approval-model/).

## Asking in plain English

```bash
genesis decide "why is this project so hard to change?"
```

The [decision engine](../decision-engine/) maps the sentence to the engines that can answer it.
