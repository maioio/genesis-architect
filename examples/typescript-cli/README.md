# typescript-cli example

These three files are **illustrative samples** showing the format and content
quality Genesis Architect aims for in a real run:

- `RESEARCH.md` - what the research report looks like (5+ analyzed repos, sources, decision rationale)
- `PITFALLS.md` - 4 real pitfalls with live GitHub Issue URLs and mitigations tied back to scaffold files
- `ROADMAP.md` - phased development plan calibrated to the research

## What is *not* here

A full scaffold capture (`src/`, `tests/`, `package.json`, `Dockerfile`, ADR,
CI workflow, etc.). Those are produced by the skill at runtime from the
templates in:

- [`references/architecture-patterns.md`](../../references/architecture-patterns.md) - per-language file structures and snippets
- [`scripts/scaffold_generator.py`](../../scripts/scaffold_generator.py) - the structure generator (run as a smoke test in CI)
- [`assets/RESEARCH.template.md`](../../assets/RESEARCH.template.md), [`assets/PITFALLS.template.md`](../../assets/PITFALLS.template.md), [`assets/ROADMAP.template.md`](../../assets/ROADMAP.template.md) - templates the validator checks against

To see a complete real-world capture, run `genesis init` against your own
project and commit the result.

## Citation verification

Every GitHub Issue URL cited in `PITFALLS.md` here resolves to a live issue.
CI verifies this on every push using `research_validator.py --verify-issues`
(see [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)).
