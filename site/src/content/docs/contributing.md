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
- Run `python scripts/public_surface/generate_product_facts.py --check` and `python scripts/architecture_invariants.py --check` before pushing.

Report security problems privately. See [Security](../security/).
