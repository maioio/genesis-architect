# Architecture Regression Temporal Design

Status: DRAFT v2 — pending approval. No production code has been written
against this document. v2 corrects a current-vs-itself baseline bug found in
v1 before any code was written.

Scope: extend `rules_engine.py` / `.genesis/rules.json` with time-aware
rules. No parallel DSL or framework. Two of the four originally-candidate
rules ship in v1; the other two stay deferred (§10).

## 1. History source

`.genesis/score_history.jsonl`, appended by
`architecture_scorer.append_score_history()` (verified: `architecture_scorer.py:141-159`).
Read by `architecture_scorer.load_score_history()` (verified:
`architecture_scorer.py:162-176`).

## 2. Prior-history semantics (revised)

**v1 bug found before implementation:** `rules_engine` is declared
`requires=["architecture_scorer", "antipattern_detector"]`
(verified: `gde_engine_registration.py:302`), so inside the GDE pipeline
`gde_run_architecture_scorer` always completes — including its
`append_score_history()` call (`gde_engine_adapters.py:110`) — before
`gde_run_rules_engine` runs. Any temporal check that just read
"`score_history.jsonl`'s last entry" at that point would read the **current**
run's own just-appended record, not a prior one. `current == baseline` means
every temporal rule passes trivially, always, regardless of real regression.

The fix is **never** "the last entry in the file." It is:

```
current_snapshot   vs.   last(prior_history)
```

where `prior_history` is everything written to `score_history.jsonl` strictly
**before** the current observation — obtained by timing/construction, never
by comparing values (two legitimate runs can share an identical score, so
equality-based de-duplication would silently drop a real prior observation).

### Dataflow — GDE (orchestrated) path

```
gde_run_architecture_scorer(ctx):
    result        = score_project(project_dir)            # current run
    prior_history = load_score_history(project_dir)        # BEFORE append — new
    append_score_history(project_dir, result)               # unchanged, as today
    history = prior_history + [on_disk_shape(result)]       # unchanged decay-forecast input
    return {
        ...,                      # score, score_label, dimensions — unchanged
        "history": history,       # unchanged: still used only by decay_forecast
        "prior_history": prior_history,   # NEW, additive output key
    }

gde_run_rules_engine(ctx):
    prior_history = ctx.engine_results.get("architecture_scorer", {}).get("prior_history")
    report = run_check(project_dir, prior_history=prior_history)   # NEW optional kwarg
```

### Dataflow — standalone `genesis gate` path

```
main() / run_check(project_dir):
    # no ctx, no prior_history argument supplied -> defaults to None
    run_check(project_dir, prior_history=None)
```

Standalone `genesis gate` never calls `append_score_history` at all (only the
GDE adapter does — verified, `score_project()` itself does not append). So at
the moment this path reads `score_history.jsonl`, nothing from the current
run is in it yet. A fresh `load_score_history(project_path)` read **is**
correct prior history here, by construction, with no extra logic needed.

### The unifying fallback (the actual "smallest integration")

```python
def gather_facts(project_path, prior_history=None):
    ...
    facts["prior_history"] = (
        prior_history if prior_history is not None
        else load_score_history(project_path)
    )
```

One line. The GDE path supplies the pre-append snapshot explicitly; the
standalone path falls through to a direct read that is already correct
because nothing has been appended yet. Both paths converge on the same
meaning — "everything recorded before this evaluation's own observation" —
with no value-equality filtering anywhere.

**v1 limitation, stated explicitly:** `score_history.jsonl` carries no git
SHA or branch identity. "Prior history" means the last recorded **prior
observation**, not necessarily the previous commit — a dev running locally
between commits, or CI runs interleaved with local runs, can make the
baseline older or newer than "the last commit" in wall-clock/commit terms. A
later version may add commit-aware baseline selection; v1 does not.

## 3. Snapshot schema

Unchanged from v1 draft: `max_score_decline` and `max_cycle_count_increase`
use only `total` and `cycle_count`, both already persisted on every record.
No change to `append_score_history()`'s record shape.

`critical_anti_patterns` and `bus_factor` remain out of schema for the
reasons already established (critical-anti-pattern count is computed every
run but never persisted to history — a separate adapter-wiring decision;
bus-factor is a per-file metric with no project-level aggregation anywhere
in the codebase today). Deferred, not dropped — §10.

## 4. CI reproducibility

Unchanged: today, zero. `.genesis/` is gitignored (verified: `.gitignore:14`)
and CI (verified, full `ci.yml` read) never invokes `genesis gate` or any GDE
engine. `rules_engine` reports `INSUFFICIENT_HISTORY` when there is nothing
to compare against rather than manufacturing data; making CI persist history
across runs is the consuming project's operational choice, not something
this change solves.

## 5. Insufficient history (revised)

With current and prior now cleanly separated (§2), the threshold is:

```
len(prior_history) == 0   ->  INSUFFICIENT_HISTORY
len(prior_history) >= 1   ->  evaluate against prior_history[-1]
```

The earlier draft said "fewer than 2 usable records," which was itself a
symptom of the same bug: it assumed the current observation was mixed into
the file and that two records were needed to have one real prior point. Once
`prior_history` excludes the current observation by construction, **one**
prior record is sufficient to evaluate.

## 6. Result representation (new section — requested correction)

A configured temporal rule with no usable baseline must render as neither
"PASS — all gates satisfied" nor a hard failure. Three distinguishable,
machine-readable states are needed: `PASS`, `FAIL`, `INSUFFICIENT_HISTORY`.

`RuleResult` (verified current shape: `rule, passed: bool, expected, actual,
message` — `rules_engine.py:80-86`) gains one additive field:

```python
@dataclass
class RuleResult:
    rule: str
    passed: bool
    expected: object
    actual: object
    message: str
    status: str = ""   # NEW. "pass" | "fail" | "insufficient_history"

    def __post_init__(self):
        if not self.status:
            self.status = "pass" if self.passed else "fail"
```

Every existing call site that builds a `RuleResult` without knowing about
`status` keeps working unchanged (`__post_init__` derives it from `passed`).
A temporal rule with no baseline is constructed as
`RuleResult(..., passed=True, status="insufficient_history", ...)` —
`passed=True` so it never flips `CheckReport.passed` to `False` and never
produces a `hard_failure` (not a hard policy failure in v1, per the brief),
while `status` carries the distinguishing signal for `format_report()` and
`--json` output, which switch on `status` for display rather than on the raw
`passed` bool. `CheckReport.hard_failure` / `hard_failure_reason`
(`rules_engine.py:107-118`) are **unchanged** — insufficient-history results
never reach them any differently than a shadow-mode-style non-escalating
result does today.

## 7. Corrupted history (revised)

Per-line corruption is already handled inside `load_score_history()`
(verified: `architecture_scorer.py:162-176`, skips malformed individual
lines). Not handled anywhere today: whole-file unreadability (`read_text()`
raising on a binary/non-UTF-8/truncated file) — this is latent in the
**existing** caller (`score_project()`'s confidence calc) too, not just new
code.

Since §2's dataflow adds `load_score_history()` as the shared mechanism for
both the GDE pre-append capture and the standalone fallback, the one-line fix
belongs **inside `load_score_history()` itself** (not duplicated at each call
site): wrap the `read_text()` call in the same tolerance philosophy it
already applies per-line — on any whole-file read failure, return `[]`. This
fixes the latent gap for every current and future caller at once, and an
unreadable file then behaves identically to a missing file:
`INSUFFICIENT_HISTORY`, never a crash, never a silent pass.

## 8. Temporal rule vocabulary

Unchanged: `max_score_decline` (number) and `max_cycle_count_increase`
(integer), following the existing `max_*`/`min_*`/`allow_*` naming
convention. Both optional; absent = not checked, same as all 11 existing
keys. Nothing else is added to the vocabulary.

## 9. Backward compatibility (revised wording)

Not "JSON output shape unaffected" — **backward-compatible additive
output**:

- `RuleResult` gains `status` (defaulted via `__post_init__`); existing
  `passed`/`expected`/`actual`/`message` fields and their meaning are
  unchanged.
- `run_check()` / `gather_facts()` gain an optional `prior_history=None`
  parameter; every existing call site that omits it behaves exactly as
  before (standalone fallback path).
- `gde_run_architecture_scorer`'s returned dict gains `prior_history`
  alongside the existing `history` key, which keeps its current shape and
  current only consumer (decay forecast).
- `load_score_history()` gains whole-file-failure tolerance; its existing
  contract (return a list, skip bad lines, `[]` if nothing usable) is
  extended, not changed, for its existing caller.
- Non-temporal rules, `DEFAULT_RULES`, shadow mode, and `genesis gate`'s exit
  codes are all unaffected.

## 10. V1 implementation scope (for the follow-up code change — not this document)

**Ships now:** `max_score_decline`, `max_cycle_count_increase`,
prior-history-vs-current dataflow as corrected in §2, `INSUFFICIENT_HISTORY`
status per §5-6, whole-file corruption tolerance in `load_score_history()`,
tests for pass / fail / insufficient-history / corrupted-history, plus a
regression test asserting the GDE path's `prior_history` excludes the
current run's own score (the exact bug this revision fixes).

**Still deferred, ledgered, not dropped:** critical-anti-pattern-count
temporal rule, bus-factor temporal rule — both for the reasons in §3.

## Assumptions ledger

| ID | Assumption | Basis | Blast radius if wrong | Checked at |
|----|-----------|-------|------------------------|------------|
| A1 | Baseline = last **prior** observation only, no rolling window, no branch/commit filter | Smallest comparison that's still meaningful; no SHA/branch field exists to do better | A baseline can be older or newer than "the previous commit" in commit terms | First real false positive/negative report |
| A2 | CI reproducibility is the consuming project's responsibility, not solved inside `rules_engine` | Avoids a much larger git-replay or CI-caching feature in this pass | CI never enforces temporal rules until a project opts in to persisting history | This repo's own CI behavior post-ship |
| A3 | Critical-anti-pattern and bus-factor temporal rules deferred out of v1 | Both need a persistence or aggregation decision beyond `rules_engine.py` alone | Only 2 of the 4 originally-candidate rules ship now | Next, explicitly scheduled design pass |
| A4 | The fix's correctness depends on `rules_engine`'s `requires=["architecture_scorer", ...]` declaration continuing to force scorer-before-rules ordering in the GDE scheduler | Reuses the existing topological-sort guarantee instead of inventing a new sequencing mechanism | If that `requires` entry is ever removed, `prior_history` could be read before the scorer step populates it, silently reintroducing the v1 bug | Any future change to `gde_engine_registration.py`'s `rules_engine` descriptor — should be covered by a test asserting the dependency is present |
