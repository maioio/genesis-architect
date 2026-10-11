# Research evaluation

**Measured.** The deterministic parts of the research pipeline: URL and host handling, pitfall
scoring, de-duplication, ranking, and validation of research output files.

**Covered by tests** (fixtures; none of these need the network).

| Behavior | Tests |
|---|---|
| Pitfall scoring, de-duplication, ranking | `tests/test_pitfall_ranker.py` |
| Research output validation (repos, issue URLs, safe paths) | `tests/test_research_validator.py` |
| Orchestration across sources | `tests/test_research_orchestrator.py` |
| GitHub rate-limit handling | `tests/test_github_rate_limit.py` |
| Source registry | `tests/test_source_registry.py` |

**Reproduce.**

```bash
GENESIS_NO_AUTO_INSTALL=1 pytest tests/test_pitfall_ranker.py tests/test_research_validator.py tests/test_research_orchestrator.py tests/test_github_rate_limit.py tests/test_source_registry.py -q
```

**Expected.** All pass.

**Manual rubric.** [`evals/quality_rubric.md`](../../evals/quality_rubric.md) is a human checklist
(repos exist, issue URLs return 200, star counts plausible). It is applied by hand to real runs.
No aggregate scores are committed.

**Limitations.**

- No measurement of recall (were the failures that matter found) or precision (were the surfaced
  pitfalls relevant). Live research depends on GitHub and other third-party sources, so results
  vary by run.
- Weak evidence is reported as `THIN` by design. There is no benchmark of how often that call is
  right.
