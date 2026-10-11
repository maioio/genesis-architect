---
title: Architecture
description: How Genesis is built and how it is checked against itself.
---

Genesis is a single Python package. The numbers below are generated from the code and published in `data/public-product-facts.json`.

- Engines, approval gates, modes, research sources and tiers are counted from the running package into `ARCHITECTURE_INVARIANTS.json`.
- CI regenerates that file and fails when it drifts.
- Genesis runs its own analysis on itself in CI: import cycles and critical anti-patterns must stay at zero.

The mechanism-by-mechanism write-up, including how interface parity was proven across a nine-module split, is the [architecture overview](https://github.com/maioio/genesis-architect/blob/main/docs/architecture/overview.md) in the repository.

## Self-audit

The self-audit inputs (research, pitfalls, roadmap) live in `docs/self-audit/`. CI feeds them to the evidence pack generator, so the tool is tested on a real project: itself.
