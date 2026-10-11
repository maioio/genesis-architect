---
title: Research and evidence
description: How sources are collected, checked and recorded.
---

Genesis treats a claim without a source as a defect. The research path has three checks.

## Source registry and anchors

The source registry records which sources are trusted for which kind of claim. Source anchors pin each claim to a retrievable URL. Research draws on 30 sources in 11 tiers.

## Citation validation

Citations are checked live. A URL that does not resolve fails validation, and the result is recorded rather than hidden.

## Evidence pack

`ARCHITECTURE_EVIDENCE.md` bundles the evidence behind a decision: research quality, repositories scanned, pitfalls found and the mitigation mapped to each. The pack states when it is unsigned, which is normal before you have confirmed an architecture choice.

## Thin evidence

When research is thin, Genesis says so in the pack (`Quality: THIN`) instead of presenting a confident scaffold. Treat a thin pack as a prompt to narrow the description or research further.

The counts for engines, gates and sources are published in [`data/public-product-facts.json`](https://github.com/maioio/genesis-architect/blob/main/data/public-product-facts.json) and generated from the code.
