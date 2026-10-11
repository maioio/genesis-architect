---
title: Architecture analysis
description: What the score and the anti-pattern detector measure.
---

`genesis recover` and the `genesis_architecture_score` MCP tool use the same analysis.

## Import graph

Genesis builds the import graph of your package and finds strongly connected components. A cycle is two or more modules that import each other, directly or through others.

## Score

The 0 to 100 score combines modularity, coupling, cohesion and layering. Test files do not count as coupling. A shared type vocabulary is not penalised as a hub, and a standalone script is not treated as a god class. Each rule discriminates on evidence from the dependency graph.

## Anti-patterns

The detector reports findings with a severity. The count of critical findings is published in the product facts.

## Limits

The analysis targets Python packages and reads static imports, so dynamic imports are invisible to it. The score is a signal for where to look, not a verdict.

The full mechanism is in the [architecture overview](../architecture/).
