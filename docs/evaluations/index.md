# Evaluation coverage

What Genesis measures about itself, how to reproduce each measurement, and where there is no
measurement yet. This page carries no counts: the current numbers live in
[`data/public-product-facts.json`](../../data/public-product-facts.json).

| Area | Page | Status |
|---|---|---|
| Architecture analysis | [architecture.md](architecture.md) | Checked in CI on every change |
| Security behavior | [security.md](security.md) | Unit-tested; no adversarial benchmark |
| Research and pitfall ranking | [research.md](research.md) | Unit-tested with fixtures; no recall or precision measurement |
| Decision consistency | [decision-consistency.md](decision-consistency.md) | Gate logic is unit-tested; consistency is not measured |
| Skill trigger accuracy | [skill-triggers.md](skill-triggers.md) | Query set exists; scoring is manual |
| Scaffold quality, Claude-only vs Genesis | [VALIDATION_RESULTS.md](../../validation/VALIDATION_RESULTS.md) | Historical (2026-05-30), three benchmarks, hand-reviewed |
| Benchmarks (speed, memory, size) | [benchmark-plan.md](benchmark-plan.md) | Not measured; plan only |

## Evidence versus marketing

- A number is evidence only if a command in this folder reproduces it.
- Historical results carry their date and are not restated as current.
- The root [ARCHITECTURE_EVIDENCE.md](../../ARCHITECTURE_EVIDENCE.md) is a generated pack
  produced by `scripts/evidence_pack.py`. It records the research behind Genesis's own design at
  the time stamped in its header. It is not a live metric source.

## Reproduce everything at once

```bash
pip install -e ".[dev]"
export GENESIS_NO_AUTO_INSTALL=1
pytest -q
python scripts/architecture_invariants.py --check
python scripts/public_surface/generate_product_facts.py --check
python scripts/public_surface/validate_public_claims.py
python demo/run_recover.py --check
python scripts/eval_runner.py --mode validate
```
