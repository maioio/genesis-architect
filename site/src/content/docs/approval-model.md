---
title: Approval model
description: What can change your project, and what has to approve it.
---

Analysis is read-only. Writes are separate and gated.

## Rules

- Analysis commands read your project and write nothing to it.
- `--no-commit` skips the approve and commit step entirely.
- Without `--no-commit`, proposed writes are listed and wait for your approval.
- `--yes` auto-approves every write. It exists for CI. Do not use it on a project you have not reviewed.
- `--json` implies `--no-commit`.

## Why

A tool that rewrites code on a guess is worse than no tool. The gate makes the write explicit and reviewable, and the decision log records what was approved.

## Installs

`genesis companion --ui` can install packages with pip. Set `GENESIS_NO_AUTO_INSTALL=1` to disable that.
