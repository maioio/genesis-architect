# Genesis Architect 9.0.0 — the architecture release

Genesis analyses architecture for a living. This release is Genesis applied to
itself, and it moved every number it measures.

```
import cycles            4 → 0
critical anti-patterns   7 → 0
unpinned CI actions     21 → 0
architecture score      67 → 89
```

## Read this before you upgrade

**Nothing breaks.** The CLI surface and the `genesis_architect.pro` import
surface are byte-identical to 8.0.1 — verified by diffing a full snapshot of
every subcommand, flag, default and help string after each step of the work.

The major version is about something else: **three analysis rules were wrong,
and fixing them changes what Genesis reports.** A project that changed nothing
may score differently on 9.0.0. That is the correction landing, not a
regression — see "Your scores may change" below.

## Zero import cycles

Registration had no owner. Whichever module first noticed the engine registry
was empty triggered it: the registry imported the registration module on first
call, and the knowledge-graph adapter imported it again when it found its own
dependency missing. A container importing the thing that fills it, and a
descriptor provider importing its sibling.

A composition root now owns registration, and every dependency arrow points one
way. The registry can no longer reach the providers, so the cycle cannot re-form
by someone adding another lazy import — there is an obvious place for that code
to go instead.

The fourth cycle was `recovery_scan` embedding its own rendered report while the
report module called back for data. Composition moved up to the layer that
already depended on the other. The composed output is unchanged.

## The CLI is nine modules, not one file

`gde_cli.py` was **1,974 lines** — the argument parser, ~20 command handlers,
the shared formatting helpers and the dispatcher, importing 31 modules. It is
now a `commands/` package whose widest module imports 9.

Handlers moved **verbatim**: no renames, no signature changes, no logic edits.
That was possible because every project import in the original was
function-local and owned by exactly one handler, so moving a handler moved its
imports with it.

One change was a real refactor rather than a move. `companion --serve` and
`companion --ui` brought the backend up with the same seven imports and the same
seven steps in the same order. Two copies of a startup sequence is a live bug
risk on its own — a fix to one can miss the other — so it is now a shared
module. Their *teardowns* genuinely differ, and that difference was preserved
rather than tidied away.

`gde_cli.py` remains as a compatibility surface. Every existing import path
still works.

## Your scores may change

Three rules were reporting defects that were not defects:

- **hub-file counted test files as coupling.** A test is a leaf — nothing
  depends on it, so a change cannot cascade *through* it. Counting them meant
  **adding tests degraded your architecture score.** Test importers are now
  excluded from the verdict and reported separately.
- **hub-file could not tell a vocabulary from a hub.** A module with high
  fan-in and zero fan-out is a shared type vocabulary. It cannot propagate a
  change it never receives, and the usual advice — extract the stable interface
  — is incoherent when the module already *is* that interface.
- **god-class could not tell a script from a god module.** A file nothing
  imports, living outside any package, is a script; its coupling is terminal.

Each discriminator requires evidence from the dependency graph, not a name or a
path convention.

## Fixes

- **`genesis companion --ui` could hang for up to 30 minutes.** It ran
  first-launch voice provisioning unconditionally — pip for 9 packages, then
  ~1–2 GB of models, behind a 30-minute timeout. On a machine that already has
  the extras it is a fast no-op, which is why it looked fine in development. In
  a clean environment, in CI, or with output piped, nobody can see it or
  interrupt it and the command simply appears to hang. It now provisions only
  when a human is watching, and `GENESIS_NO_AUTO_INSTALL=1` opts out
  explicitly. Nothing is faked when it is skipped.
- **`importlib.reload()` served stale objects** from the lazy package facade,
  indefinitely.
- **A purge test failed intermittently** because its fixture reused a just-freed
  PID, which the OS is free to recycle.
- **Every CI action is pinned to a full commit SHA** — 21 references. Two were
  tracking branches, including the action holding this project's PyPI
  publishing rights.

## Verification

| | |
|---|---|
| Tests | **2,836 passing**, zero failures — after *every* step, not just at the end |
| Cycles / criticals | 0 / 0 |
| CLI surface | byte-identical across all six split steps |
| Lint debt | 19 before, 19 after — none introduced |

Two practices did the real work here and are worth stealing. A **behavioural
oracle** — a 413-line dump of the entire argument surface, captured before the
refactor and diffed after every step — made "did the CLI change?" a fact rather
than a hope. And **`ruff --select F821` after every code move** caught three
defects the full suite passed straight over, because they sat on uncovered
error paths. Tests alone are not sufficient for relocations.

## Install

```bash
pip install --upgrade genesis-architect
```
