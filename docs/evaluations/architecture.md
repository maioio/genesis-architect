# Architecture evaluation

**Measured.** Import cycles, critical anti-patterns, architecture score, engine and gate counts,
and fan-out ceilings, computed by Genesis from its own source.

**Where it lives.**

- Generator: `scripts/architecture_invariants.py` writes
  [`ARCHITECTURE_INVARIANTS.json`](../../ARCHITECTURE_INVARIANTS.json) from the live package.
- Facts: `scripts/public_surface/generate_product_facts.py` writes
  [`data/public-product-facts.json`](../../data/public-product-facts.json), including a
  `provenance` map naming the source of each field.
- Tests: `tests/test_architecture_invariants.py`, `tests/test_import_graph.py`,
  `tests/test_antipattern_detector.py`, `tests/test_architecture_scorer.py`.
- Method and thresholds: [../architecture/overview.md](../architecture/overview.md).

**Fixture.** This repository. The analysis is also exercised on small fixtures inside the tests
and on `demo/fixture/`, a deliberately cyclic toy project.

**Reproduce.**

```bash
python scripts/architecture_invariants.py --check
python scripts/public_surface/generate_product_facts.py --check
python demo/run_recover.py --check
pytest tests/test_architecture_invariants.py tests/test_import_graph.py tests/test_antipattern_detector.py tests/test_architecture_scorer.py -q
```

**Expected.** Every command exits 0. `--check` fails if a committed file no longer matches what
the code reports.

**Limitations.**

- Self-measurement shows the numbers are internally consistent. It does not show that the score
  predicts real-world maintainability.
- Analysis is Python-first. Other languages are not scored by the same engine.
- The score is a heuristic. Compare scores only across runs of the same version; the 9.0.0
  changelog entry explains a rules change that moved scores.
- A metric that could not be measured is reported as `None`, never as 0.
