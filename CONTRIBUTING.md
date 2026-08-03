# Contributing to Genesis Architect

Thanks for your interest. This document covers everything you need to make a useful contribution.

---

## What to work on

Check [open issues](https://github.com/maioio/genesis-architect/issues) first.
Issues labeled [`good first issue`](https://github.com/maioio/genesis-architect/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) are scoped, well-defined, and ready to pick up without needing deep context.

If you're opening a new issue and it's small and self-contained, add the `good first issue` label yourself - it helps other contributors find it.

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

## Codebase architecture

Genesis Architect has three layers. Understanding the boundary matters before
you touch anything:

| Layer | Path | Role |
|---|---|---|
| **CLI and research core** | `src/genesis_architect/` | The `genesis` command users install. `cli.py`, `config.py`, and `core/` (github, llm, scaffolder, vault). This runs when a user types `genesis init`. |
| **Engine layer** | `src/genesis_architect/pro/` | The analysis engines: decision engine, knowledge graph, import graph, C4, security, voice, Companion. Formerly the paid `genesis-architect-pro` package, merged in v8.0.0 and free. The name is kept to keep the merge diff reviewable. |
| **Internal toolchain** | `scripts/` | Quality and validation tools that run in CI. NOT part of the installable package. They validate research artifacts, enforce mitigation coverage, and run evals. |

**Rules of thumb:**
- User-facing CLI and research features go in `src/genesis_architect/`
- Analysis engines go in `src/genesis_architect/pro/`
- CI checks and artifact tooling go in `scripts/`
- Never import from `scripts/` inside `src/`, or the other way around
- The engine layer may import from `core/`. The reverse must go through
  `core/pro_bridge.py`, which is the single indirection point.

There is no license gate anywhere, and there must never be one again. Tests in
`tests/test_pro_bridge.py` and `tests/test_gde_production_wiring.py` assert its
absence; treat a failure there as a real regression, not a test to update.

---

## Setup

```bash
git clone https://github.com/maioio/genesis-architect.git
cd genesis-architect
pip install -e ".[dev]"
pytest -q
```

All tests should pass before you start. The suite takes about 40 seconds and
runs fully offline.

To reproduce CI exactly, including the checks that only catch packaging bugs:

```bash
docker build -f Dockerfile.test -t genesis-test .
docker run --rm genesis-test
```

That installs the package the way a user would and then runs the suite plus
end-to-end CLI checks. Bugs like a data file that never made it into the wheel
are invisible from a repo checkout and only show up here.

> **The test suite must never install anything.** `genesis companion --ui` can
> shell out to pip; if a test reaches that path unmocked it will mutate your
> environment mid-run. Auto-provisioning is disabled under pytest and via
> `GENESIS_NO_AUTO_INSTALL=1`. If you add a test that touches the Companion
> launcher, mock the provisioner.

---

## Key constraints (enforced in CI)

| Constraint | Check |
|---|---|
| `SKILL.md` under 400 lines | `wc -l SKILL.md` |
| No em or en dashes in reader-facing docs | CI grep step (README, SKILL, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, docs/) |
| All tests pass on Python 3.11, 3.12, 3.13 | `pytest tests/` matrix |
| Packaged install works | `docker build -f Dockerfile.test` job |
| Required package data ships in the wheel | build-artifacts job |
| Eval schema valid | `python scripts/eval_runner.py --mode validate` |
| Scaffold smoke test | CI: all 8 language/tier combos |

Source comments are exempt from the dash rule: en dashes are correct in numeric
ranges such as `0.0-1.0`.

---

## Adding a language template

1. Add the file list to `references/folder-structures.toml`
2. Copy it to the packaged catalog:
   `cp references/folder-structures.toml src/genesis_architect/core/data/`
3. Add boilerplate to `references/architecture-patterns.md`
4. Test: `python scripts/scaffold_generator.py --language yourlang --tier minimalist --name test --output /tmp/test`
5. Add a CI smoke test line in `.github/workflows/ci.yml`

Step 2 is not optional. `references/` is the human-editable copy, but the
packaged copy under `core/data/` is what actually ships and is read at import
time. A guard test fails if the two drift apart.

Follow the existing Python and TypeScript patterns exactly.

---

## PR checklist

- [ ] `pytest -q` passes
- [ ] `docker run --rm genesis-test` passes (or CI is green on your PR)
- [ ] `python scripts/eval_runner.py --mode validate` exits 0
- [ ] SKILL.md under 400 lines (if modified)
- [ ] No em or en dashes in reader-facing docs
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

---

## Licensing of contributions

Genesis Architect is licensed under **AGPL-3.0-or-later**. Contributions are
accepted inbound under the same license as outbound: by opening a pull request
you agree your contribution is licensed under AGPL-3.0-or-later. There is no
CLA and no copyright assignment.

---

## Code review and feedback

You don't have to write code to contribute. Experienced feedback is just as valuable.

If you read through the codebase and something looks fragile, inconsistent, or wrong - open an issue and explain what you found. That's how nitayk contributed: a careful read, specific findings, clear reasoning.

**What makes a good review issue:**
- Point at the specific file and line
- Explain what the problem is and why it matters
- Suggest a direction if you have one, but it's not required

**Where to start if you want to review:**
- [`src/genesis_architect/core/scaffold_generator.py`](src/genesis_architect/core/scaffold_generator.py) - core output path, most user-visible
- [`src/genesis_architect/core/genesis_subcommands.py`](src/genesis_architect/core/genesis_subcommands.py) - OSV.dev integration, network code
- [`src/genesis_architect/pro/gde_cli.py`](src/genesis_architect/pro/gde_cli.py) - the command surface everything routes through
- [`SKILL.md`](SKILL.md) - the skill definition itself, benefits from fresh eyes

## Questions

Open an issue or start a GitHub Discussion.
