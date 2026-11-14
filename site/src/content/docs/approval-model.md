---
title: Approval model
description: Gate checks, the approval step and dry runs - what can change your project and what has to approve it.
---

Genesis separates analysis from changes. `recover`, `harden` and `decide` run a decision session: the engines analyse the project, gate checks judge the result, and only then are the proposed report files written, after you approve them.

## What is written when

| When | What | Where |
|---|---|---|
| During analysis | Session state, memory and the decision log | `.genesis/` in the project |
| During analysis, when the fragility classifier runs (`recover`, `harden`, and the refactor, gate and committee modes of `decide`) | The fragility map | `FRAGILITY_MAP.md` in the project |
| After you approve | The session's report files, for example `PROJECT_RECOVERY_REPORT.md` or `docs/security/` | The project |
| Never | Your source files | Analysis does not edit them |

## The session, step by step

1. **Analysis.** The decision engine classifies the instruction into a mode and runs that mode's engines.
2. **Gate checks.** The checks the mode asks for run on the result (table below).
   - A **hard block** stops the session. Genesis reports that the session is blocked, executes none of the proposed writes, and exits with code 2.
   - A **block-and-ask** check does not stop the session on its own. It makes the session pending, so it goes to the approval step and you decide.
   - A **warning** is reported and the session continues.
3. **Approval.** When anything is pending, Genesis lists the write operations, each marked reversible or irreversible, and asks: `[A]pprove  [R]eject  [D]efer`. The default is Defer, and so is closing the prompt.
   - Approve writes the pending operations.
   - Reject discards them.
   - Defer writes nothing and keeps the session so you can come back to it with `--resume`.
4. **Commit.** Approved operations are written. If a write fails, Genesis prints `Commit failed` and exits with code 3.

Hard blocks cannot be approved past: the commit step refuses to write while one is present.

## Flags

| Flag | Effect |
|---|---|
| `--no-commit` | Analysis only. The session ends after the gate checks: nothing goes to approval and no proposed report is written. Analysis output is still written: `.genesis/` state and, when the fragility classifier runs (as in `recover` and `harden`), `FRAGILITY_MAP.md`. |
| `--yes` | Approves every pending write without asking. It exists for CI; do not use it on a project you have not reviewed. It does not override a hard block. |
| `--json` | Prints the session report as JSON and implies `--no-commit`. Exit code 2 on a hard block, otherwise 0. |
| `--classify-only` | Prints the mode the instruction maps to, with its confidence and signals, and stops. |
| `--resume` | Continues a deferred session. |

## Gate checks

Gate checks are policy checks on a decision session. They are not the same thing as the MCP server's `genesis_gate` tool, which validates the architecture regression rules in `.genesis/rules.json`.

<!-- gates:start -->
14 gate checks are defined. 9 are evaluated by at least one mode; the other 5 are defined in the policy table but no mode asks for them yet.

| Check | Fires when | What happens | Can be overridden | Evaluated in modes |
|---|---|---|---|---|
| `PLAN_WRITE` | Planned file write blocked | Hard block: the session stops before any proposed write | no | recovery, research, refactor, gate, build, document, committee |
| `RULES_FAIL` | Rules engine hard failure | Hard block: the session stops before any proposed write | no | recovery, research, refactor, gate, build, document, committee |
| `CONFIDENCE_LOW` | Confidence below safe threshold | Block and ask: the session pauses for your decision | yes | recovery, research, refactor, gate, build, document, committee |
| `DRIFT_CRITICAL` | Critical drift detected | Block and ask: the session pauses for your decision | yes | recovery, refactor, committee |
| `SECURITY_RISK` | Security risk in proposed changes | Block and ask: the session pauses for your decision | yes | build |
| `POLICY_VIOLATION` | Policy violation detected | Block and ask: the session pauses for your decision | yes | gate |
| `COMMIT_CONFLICT` | Write conflict with committed model | Block and ask: the session pauses for your decision | yes | none yet (defined only) |
| `RED_TEAM_CRITICAL` | Red-team found a critical vulnerability | Block and ask: the session pauses for your decision | yes | recovery, research, refactor, gate, build, document, committee |
| `RESEARCH_COVERAGE_LOW` | Research coverage below threshold | Block and ask: the session pauses for your decision | yes | research |
| `WRITE_SCOPE` | Write operations pending | Warning: reported, the session continues | yes | refactor, build, committee |
| `REQUIRED_FAILED` | Required engine(s) failed | Warning: reported, the session continues | yes | none yet (defined only) |
| `DEGRADED_MODE` | Session running in degraded mode | Warning: reported, the session continues | yes | none yet (defined only) |
| `NO_ENGINES` | No engines ran for this mode | Warning: reported, the session continues | yes | none yet (defined only) |
| `RESEARCH_STALE` | Research results may be stale | Warning: reported, the session continues | yes | none yet (defined only) |

Generated from [`ARCHITECTURE_INVARIANTS.json`](https://github.com/maioio/genesis-architect/blob/main/ARCHITECTURE_INVARIANTS.json), which is built from the gate policy table and the planner.

<!-- gates:end -->

## Dry runs

- `genesis purge` is a dry run until you pass `--apply`: it reports the expired worktrees and locks it would remove, and `genesis purge --apply` removes them. Two other commands delete and are not dry runs: `genesis telemetry clear` deletes the locally stored telemetry events, and `genesis fetch --discard` removes a fetched skill pack from its sandbox. Both act immediately and only on Genesis's own files.
- `genesis sync` is not a dry run by default: it marks GREEN findings as applied and writes `.genesis/sync_log.jsonl` (and `.genesis/pending.json` for YELLOW findings). `genesis sync --dry-run` writes nothing.
- `genesis fetch` clones into a short-lived sandbox, never into your project.

## Installs

`genesis companion --ui` can install packages with pip. Set `GENESIS_NO_AUTO_INSTALL=1` to disable that.

## Why

A tool that rewrites code on a guess is worse than no tool. Gate checks make the risky cases stop or ask, the approval step makes every write explicit and reviewable, and the decision log (`genesis explain`) records what was approved.
