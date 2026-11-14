---
title: Architecture
description: How Genesis is built, what each public number counts, and how it is checked against itself.
---

Genesis is a single Python package. Every number on this site and in the README is generated from the code and published in `data/public-product-facts.json`; CI fails when a page disagrees with it.

<!-- numbers:start -->
| Number | Value | What it counts |
|---|---|---|
| Architecture score | 93 / 100 | Modularity, coupling, cohesion and layering of this package, scored by its own analyzer |
| Import cycles | 0 | Cycles in this package's import graph |
| Critical anti-patterns | 0 | Critical findings from the anti-pattern detector on this package |
| Tests collected | 2,893 | `pytest --collect-only` on this repository |
| User-facing capabilities | 55 in 9 families | Things Genesis can do for a person, from the capability catalog. Workflows and integrations are not counted |
| Top-level commands | 22 | `genesis` subcommands, including advanced and legacy ones |
| Registered engines | 19 | Units the decision engine schedules. One engine can serve several capabilities |
| Decision modes | 7 | Plans the decision engine can run, such as recovery and research |
| Gate checks | 9 evaluated, 14 defined | Checks run on a decision session: 2 hard blocks, 7 block-and-ask, 5 warnings |
| Research source registry | 30 sources in 11 tiers | Sources Genesis knows how to classify and rank. Not a list queried on every run |
| MCP tools | 4 read-only | Analysis tools the Genesis MCP server exposes. They do not write files or use the network |

Generated for v9.0.0 from [`data/public-product-facts.json`](https://github.com/maioio/genesis-architect/blob/main/data/public-product-facts.json).

<!-- numbers:end -->

- Engines, gate checks, modes, research sources and tiers are counted from the running package into `ARCHITECTURE_INVARIANTS.json`.
- Capabilities and families are counted from the [capability catalog](/genesis-architect/capabilities/), which is generated from the capability map in the code.
- CI regenerates these files and fails when they drift.
- Genesis runs its own analysis on itself in CI: import cycles and critical anti-patterns must stay at zero.

The mechanism-by-mechanism write-up, including how interface parity was proven across a nine-module split, is the [architecture overview](https://github.com/maioio/genesis-architect/blob/main/docs/architecture/overview.md) in the repository.

## Self-audit

The self-audit inputs (research, pitfalls, roadmap) live in `docs/self-audit/`. CI feeds them to the evidence pack generator, so the tool is tested on a real project: itself.
