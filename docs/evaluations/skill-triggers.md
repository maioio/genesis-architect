# Skill trigger accuracy

**Measured.** Whether the Genesis skill should activate on a given natural-language request.

**Dataset.** [`evals/test_queries.json`](../../evals/test_queries.json): a labelled set of
should-trigger and should-not-trigger queries. The runner validates the file's schema in CI.
Scoring against a live agent is manual.

**Reproduce.**

```bash
python scripts/eval_runner.py --mode validate   # schema check
python scripts/eval_runner.py --mode report     # checklist to fill in by hand
```

**Expected.** `validate` prints "Schema valid". The documented target is above 90% on both the
trigger and the false-positive sets.

**Limitations.** The target is a goal, not a result. No completed manual scoring run is committed,
so no current accuracy figure is claimed.
