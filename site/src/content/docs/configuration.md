---
title: Configuration
description: API keys, environment variables and defaults.
---

## API keys

Keys are stored in `~/.genesis/config.json`.

```bash
genesis config set LLM_API_KEY <your-key>
genesis config set GITHUB_TOKEN <your-token>
genesis config show
```

`config show` prints only the first characters of each value.

| Key | Used by | Required |
|---|---|---|
| `LLM_API_KEY` | `genesis init` | Yes, for `init` |
| `GITHUB_TOKEN` | GitHub search | Recommended, for rate limits |

`recover`, `harden`, `deps` and `doctor` need no keys.

## Environment variables

| Variable | Effect |
|---|---|
| `GENESIS_NO_AUTO_INSTALL=1` | Disable pip installs by the Companion |
| `GENESIS_COMPANION_MUTE` | Silence the Companion voice |
| `GENESIS_MCP_CONFIG` | Path to MCP configuration used by `advise` |
| `GENESIS_PSR_OUTPUT_DIR` | Output directory for PSR artifacts |

## Telemetry

Telemetry is off by default and opt-in. `genesis telemetry` shows and changes the consent record.

## Optional extras

`pip install "genesis-architect[all]"` adds the voice, Companion and committee subsystems. They pull heavy native packages and are not needed for analysis.
