---
title: Security
description: What Genesis does with your code, and how to report a vulnerability.
---

## What Genesis does

- It never executes code from a repository it analyzes.
- Its secrets scanner redacts every value it finds. It must never write an unredacted secret to disk or to a report.
- Path handling: scaffolding and analysis write into user-supplied directories, and traversal outside the target root is a vulnerability.
- Telemetry is off by default.

## Reporting a vulnerability

Do not open a public issue. Use the private advisory form on GitHub:
[Report a vulnerability](https://github.com/maioio/genesis-architect/security/advisories/new).

The full policy, supported versions and scope are in [SECURITY.md](https://github.com/maioio/genesis-architect/blob/main/SECURITY.md).

## Generated scaffolds

Projects created by `genesis init` include secret scanning, SAST, a quality gate, a path traversal guard, a non-root Dockerfile and a strict `.gitignore`.
