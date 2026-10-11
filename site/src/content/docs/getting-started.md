---
title: Getting started
description: Install Genesis Architect and run your first command in under two minutes.
---

Genesis Architect is a Python package with one command, `genesis`. It has two entry points:

- `genesis init "..."` researches before you build a new project.
- `genesis recover .` diagnoses a project that already exists.

## Install

Requires Python 3.11 or newer.

```bash
pip install genesis-architect
genesis doctor
```

`genesis doctor` checks the install and reports which optional dependencies are present. It changes nothing.

## First run on existing code

```bash
cd your-project
genesis recover . --no-commit
```

`--no-commit` runs the analysis only. Nothing is written to your project. The report covers drift, broken imports, anti-patterns and fragile modules.

## First run on a new idea

```bash
genesis config set LLM_API_KEY <your-key>
genesis init a Python CLI for analyzing log files
```

`init` needs an LLM key and, for higher GitHub rate limits, a `GITHUB_TOKEN`. See [Configuration](../configuration/).

## Next

- [New projects](../new-projects/)
- [Existing projects](../existing-projects/)
- [Commands](../commands/)
