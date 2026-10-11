# Benchmark plan

There is no committed, reproducible performance benchmark, so there is no `BENCHMARKS.md` and no
comparison with other tools. This page records what a fair benchmark would need.

**What exists.** [`validation/VALIDATION_RESULTS.md`](../../validation/VALIDATION_RESULTS.md)
compares a Claude-only build with a Genesis build for three prompts (dated 2026-05-30). It is a
small, hand-reviewed sample of scaffold quality. It is not a speed or accuracy benchmark and
should be cited with its date.

**Candidate measurements (not done).**

| Question | Method | Fixture |
|---|---|---|
| How long does `genesis recover` take as repository size grows? | Time it over repositories of several sizes | Public repos pinned at fixed SHAs |
| Peak memory of the import-graph build | Same runs, record peak memory | Same |
| Wheel size and install time | Build with `docker/Dockerfile.wheel`, record size | This repository |

**Rules before publishing a number.**

1. Pin the input (repository and SHA, or a committed fixture).
2. Commit the script that produces it.
3. State the machine, OS and Python version.
4. Compare with another tool only if it is run the same way on the same input and its version is
   recorded.
