# Ordering defect: constraints are evaluated after execution

**Logged:** 2026-08-23 | **Version:** v9.0.0 @ `8e8d5a4` | **Status:** open, unfixed
**Class:** architectural (stage ordering), not a coding error
**Found by:** cognitive-architecture audit, read-only

---

## Summary

Genesis decides **which** gates apply before running anything, but evaluates
**all** of them only after execution has finished. There is no pre-execution
constraint check anywhere in the pipeline. Work is therefore performed first
and judged second, which is the inverse of the intended behavioural model.

---

## Evidence

`decision_engine.py:97-113` - the full session sequence, unedited:

```python
# INTAKE
ctx = self._intake(user_input, resume)

# PLAN
ctx.stage = LifecycleStage.PLAN
plan = build_plan(intent, registry=self.registry)

# EXECUTE
run_plan(plan, ctx, parallel=self.parallel)

# GATE
ctx.stage = LifecycleStage.GATE
gate_report = evaluate_gates(ctx, plan.required_gate_ids)
```

`grep -rn "evaluate_gates(" src/` returns **exactly one** call site:
`decision_engine.py:112`, immediately after `run_plan` on line 108.

Gate *identity* is resolved at plan time - `gde_planner.py:74-82` builds
`required_gates` from universal plus per-mode sets and stores it as
`required_gate_ids`. Gate *evaluation* is entirely post-execution.

`LifecycleStage` confirms the intended order is the implemented one:
`idle, intake, plan, execute, gate, report, approve, commit`.

---

## Expected vs actual

| Stage | Intended behavioural model | Genesis today |
|---|---|---|
| 3 | Context Retrieval | absent as a stage |
| 4 | **Constraint Detection** | **runs at stage 5, after execute** |
| 5 | Task Decomposition | `plan` (runs before execute, correct) |
| 7 | Execution | `execute` |
| 8 | Verification | `gate` - currently doing double duty as both |

Constraint Detection and Verification are distinct stages in the model. Genesis
implements one stage, `gate`, positioned where Verification belongs, and has no
stage where Constraint Detection belongs.

---

## Impact

1. **Work is done before it is authorised.** Every engine in the plan runs to
   completion regardless of whether a constraint would have forbidden the
   session. Cost is incurred, and side effects reachable by engines occur,
   before any gate has an opinion.

2. **The security verdict describes work already performed.** Observed:
   `genesis harden` on a directory containing a live GitHub token reported
   `Risk: none, Gate: PASS, rc=0`. Whatever else is wrong there (see C-2 in the
   architecture audit), the ordering guarantees the verdict can only ever be
   retrospective.

3. **`BLOCK_AND_ASK` cannot prevent, only annul.** Seven of the fourteen gates
   are `BLOCK_AND_ASK`. Asking the user to approve something that has already
   run reduces the gate to a commit-time veto on writes, which is a narrower
   guarantee than the gate table implies.

4. **It compounds C-1.** The hard-gate bypass (`overall` trusted over
   `hard_blocks`) is dangerous precisely because by the time the check runs,
   execution is complete and only the write step remains to be stopped. A
   pre-execution check would fail earlier and cheaper.

---

## What is *not* claimed

- This is **not** the cause of C-2 (the secrets scanner is unwired regardless
  of ordering).
- `run_plan` is **not** asserted to perform writes; writes are staged as
  `pending_write_operations` and executed at `commit`. The impact above is
  about cost, side effects reachable inside engines, and the semantics of the
  gate table - not about unauthorised file writes.
- No claim is made about which specific gates *could* be evaluated
  pre-execution. Several depend on engine output and structurally cannot be.
  **UNKNOWN:** the exact partition of the fourteen gates into pre-executable
  and post-executable. Determining it requires reading each gate's condition in
  `_evaluate_gate`, which this audit did not do.

---

## Direction for the next refactoring cycle

Not implemented, not designed in detail. Recorded so the shape is not lost:

The pipeline needs a constraint stage between `plan` and `execute` that
evaluates the subset of `required_gate_ids` whose conditions depend only on
intent, plan, and project state rather than on engine results. Gates that
genuinely require engine output stay where they are. That partition is the
first piece of work, and it is a reading task before it is a coding task.

A second, cheaper mitigation is available independently: `evaluate_gates` could
be called twice with the same `required_gate_ids`, once before `run_plan` and
once after, with pre-execution evaluation skipping gates whose inputs are not
yet available. This changes no gate semantics and adds no new stage.

---

## Recommended regression tests

1. A session whose constraints are knowable from intent alone MUST NOT execute
   any engine when those constraints fail.
2. `evaluate_gates` MUST have at least one call site preceding `run_plan` in
   `decision_engine.run`.
3. For a gate evaluable pre-execution, a failing session MUST report zero
   `EngineResult` entries.

**Covered by existing tests?** No. The current suite asserts gate *outcomes*,
not the *position* of gate evaluation relative to execution.
