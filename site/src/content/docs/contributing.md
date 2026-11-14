---
title: Contributing
description: How to propose a change.
---

The authoritative guide is [CONTRIBUTING.md](https://github.com/maioio/genesis-architect/blob/main/CONTRIBUTING.md). In short:

```bash
git clone https://github.com/maioio/genesis-architect
cd genesis-architect
pip install -e ".[dev]"
pytest
```

- Open an issue before a large change.
- Keep claims sourced. Numbers in public text come from `data/public-product-facts.json`.
- Before pushing, run the same drift checks CI runs, with `PYTHONPATH=src`:
  - `python scripts/architecture_invariants.py --check`
  - `python scripts/public_surface/generate_capability_catalog.py --check`
  - `python scripts/public_surface/generate_product_facts.py --check`
  - `python scripts/public_surface/sync_readme_facts.py --check`
  - `python scripts/public_surface/validate_public_claims.py`
- If a check fails, rerun that generator with `--write` and commit the result. Never edit a generated block by hand.

Report security problems privately. See [Security](../security/).
