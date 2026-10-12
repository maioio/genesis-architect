---
title: Research and evidence
description: How sources are collected, checked and recorded.
---

Genesis treats a claim without a source as a defect. The research path has three checks.

## Source registry and anchors

The source registry records which sources are trusted for which kind of claim. Source anchors pin each claim to a retrievable URL. The registry recognizes 30 sources in 11 tiers. That is a catalog of sources Genesis knows how to rank, not a list queried on every run.

## Where research comes from

The sources depend on the surface you use.

| Surface | Research sources | Network |
|---|---|---|
| Standalone CLI, `genesis init` | GitHub repositories and issues, plus your configured LLM | Yes |
| Standalone CLI, `genesis research` | Merges, ranks and validates findings you or your agent collected beforehand; with no data it prints a collection guide | No collection of its own |
| Agent skill (`SKILL.md`) | GitHub, plus ecosystem and community search, package registries, security data and video metadata, through whatever web and MCP tools the host agent provides | Through the host agent |
| Genesis MCP server | None. Four read-only analysis tools over a local project | No |

Genesis researches across the software ecosystem using the sources available in the current execution environment. When it runs as an agent skill, its research workflow can combine GitHub with available web and MCP sources, community discussions, package registries, security data and relevant media. Which of these actually run depends on the tools the agent has; a thin result is reported as thin.

Using external MCP tools for research is a skill behavior of the host agent. It is separate from the MCP server Genesis exposes.

## Citation validation

Citations are checked live. A URL that does not resolve fails validation, and the result is recorded rather than hidden.

## Evidence pack

`ARCHITECTURE_EVIDENCE.md` bundles the evidence behind a decision: research quality, repositories scanned, pitfalls found and the mitigation mapped to each. The pack states when it is unsigned, which is normal before you have confirmed an architecture choice.

## Thin evidence

When research is thin, Genesis says so in the pack (`Quality: THIN`) instead of presenting a confident scaffold. Treat a thin pack as a prompt to narrow the description or research further.

The counts for engines, gates and sources are published in [`data/public-product-facts.json`](https://github.com/maioio/genesis-architect/blob/main/data/public-product-facts.json) and generated from the code.
