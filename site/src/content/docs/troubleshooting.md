---
title: Troubleshooting
description: Fixes for the problems people hit first.
---

## `genesis` fails with `ModuleNotFoundError: genesis_architect_pro`

An old install left a stale `genesis` launcher behind. Reinstall:

```bash
pip uninstall genesis-architect-pro genesis-architect
pip install genesis-architect
```

The separate `genesis-architect-pro` package is discontinued. Its code is part of `genesis-architect`.

## `No LLM API key found`

`genesis init` needs a key: `genesis config set LLM_API_KEY <your-key>`.

## GitHub rate limit errors

Set a token: `genesis config set GITHUB_TOKEN <your-token>`.

## Research quality is THIN

Few comparable repositories were found. Shorten the description or name the domain more plainly, then run again.

## Check the install

```bash
genesis doctor
```

Still stuck? Open an issue with the output of `genesis doctor --json`.
