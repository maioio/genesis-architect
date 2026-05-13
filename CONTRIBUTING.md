# Contributing to Genesis Architect

Thanks for your interest. This document covers everything you need to make a useful contribution.

---

## What to work on

Check [open issues](https://github.com/maioio/genesis-architect/issues) first.
Issues labeled `good first issue` are scoped and ready to pick up.

Good contribution types:
- New language templates (Elixir, Java, Ruby, Swift)
- New architecture archetypes (mobile, data pipeline, serverless)
- Improvements to Phase 2 research quality
- Bug fixes with a clear reproduction case
- CI and quality improvements

Not useful without prior discussion:
- Large SKILL.md restructures
- New phases or workflow changes
- Changing the 8-phase structure

---

## Setup

```bash
git clone https://github.com/maioio/genesis-architect.git
cd genesis-architect
pip install pytest
python -m pytest tests/ -q
```

All tests should pass before you start.

---

## Key constraints (enforced in CI)

| Constraint | Check |
|---|---|
| `SKILL.md` under 400 lines | `wc -l SKILL.md` |
| No em dashes (`--` or `-`) | CI grep step |
| All tests pass | `pytest tests/` |
| Eval schema valid | `python scripts/eval_runner.py --mode validate` |
| Scaffold smoke test | CI: all 8 language/tier combos |

---

## Adding a language template

1. Add the file list to `references/folder-structures.toml`
2. Add boilerplate to `references/architecture-patterns.md`
3. Test: `python scripts/scaffold_generator.py --language yourlang --tier minimalist --name test --output /tmp/test`
4. Add a CI smoke test line in `.github/workflows/ci.yml`

Follow the existing Python and TypeScript patterns exactly.

---

## PR checklist

- [ ] `python -m pytest tests/ -q` passes
- [ ] `python scripts/eval_runner.py --mode validate` exits 0
- [ ] SKILL.md under 400 lines (if modified)
- [ ] No em dashes
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

---

## Questions

Open an issue or start a GitHub Discussion.
