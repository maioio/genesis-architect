# Clean-room E2E validation

A throwaway container with **nothing pre-provisioned**: no voice packages, no
STT/TTS models, no `~/.genesis`, and no TTY.

That last part is the point. Every developer machine here has the `voice`
extra installed, and that hides a class of bug the test suite cannot see.
`genesis companion --ui` spent months pip-installing 9 packages and
downloading ~1–2 GB of models before it returned — and looked instant
locally, because there was nothing left to fetch. Measured here: the
unpatched launcher was still installing when killed at 150 s, against a
30-minute pip timeout. Two VAD tests had the same shape, importing `numpy`
from the `voice` extra and passing everywhere except a fresh checkout.

Run this before a release. It answers "does this work for someone who does
not already have everything?", which is not a question the suite can ask of
itself.

## Usage

```bash
./run.sh                          # against genesis-architect from PyPI
./run.sh --core /path/to/core     # against a local core checkout
./run.sh --core-version 8.0.1     # pin the PyPI core
./run.sh --keep                   # leave the staged context for inspection
./run.sh --build-only
```

Exit code is 0 only if every phase passed. Requires Docker and bash (Git Bash
works on Windows).

### Which core to test against

`genesis-architect-pro` depends on `genesis-architect`, and the two live in
separate trees.

- **PyPI (default)** — resolves the published dependency, exactly as a user
  installing the Pro package would. This is the release-validation mode.
- **`--core <path>`** — installs a local core checkout instead, for
  validating a core change that is not released yet, or a Pro change that
  depends on one.

Both modes are expected to pass. If PyPI passes and `--core` fails, the local
core has a regression; the reverse means Pro depends on something unreleased.

## What runs

| Phase | Checks |
|---|---|
| 1. pytest | the full suite, capped at 900 s — a run near that ceiling means something is blocking, which is itself the bug |
| 2. CLI smoke | `--help`, `doctor`, `doctor --json`, `engines`, `engines --json`, `purge` (dry-run), each capped at 120 s |
| 3. headless launcher | `companion --ui` returns; installs nothing (package count identical before/after); downloads no models; still writes its UI |
| 4. R1–R6 pipeline | 28 checks across outline → deep → report |

Phase 4 (`r1_r6_e2e.py`) is not a unit test. It drives the outline-driven
research chain through one real project directory in the order a live GDE
session would, and asserts on the seams **between** the six commits rather
than inside any one of them: outline round-trip, adapter surfacing,
`RESEARCH_COVERAGE_LOW` present in the RESEARCH gate list, a thin pass
failing the floor and firing the gate as `BLOCK_AND_ASK`, absent coverage
staying silent rather than reading as zero, a full grid clearing the floor,
and unconfident values withheld from the rendered report.

Skips are expected and honest: the optional extras genuinely are not
installed here, so the tests that need them report skipped rather than
passing on a mock or failing on an import.

## Adding a phase

Add it to `e2e.sh` and set `RC=1` via `fail` on failure — `set -e` is
deliberately off so that one broken phase still lets the rest report. Keep
every command under a `timeout`: turning a hang into a reported failure
instead of a stuck build is most of this harness's value.
