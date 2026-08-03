# v8.0.0 - Genesis Architect is now fully free and open source

Genesis used to ship as open-core: a free scaffolder plus a paid,
license-gated `genesis-architect-pro` add-on. That split is gone.

Everything that was behind the paywall is now in the one package, under
AGPL-3.0. No key, no account, nothing gated:

- the Genesis Decision Engine (7 modes, 17 engines, 12-gate approval policy)
- the cross-source Knowledge Graph linking code, CVEs, risks and decisions
- architecture scoring, anti-pattern detection and the fragility risk map
- recovery scan and executable refactoring plans
- STRIDE threat modelling, OWASP checklist and offline secrets scanning
- C4 diagrams including the Level 3 component view
- the Committee Engine, voice Companion and video-to-pitfall extraction

## Install

```bash
pip install genesis-architect
```

## Upgrading from the Pro package

```bash
pip uninstall genesis-architect-pro
pip install -U genesis-architect
```

`genesis-architect-pro` is discontinued. Its modules now live under
`genesis_architect.pro.*`. `genesis license activate` is a friendly no-op and
`GENESIS_PRO_LICENSE` is ignored. The licensing module was deleted rather than
stubbed, and there are regression tests asserting it stays gone.

## Two bugs worth calling out

Both were found by testing the packaged install in Docker instead of the repo
checkout, and neither was visible from a normal `pytest` run.

**`genesis init` was broken for anyone who installed from PyPI.** The
scaffolder loaded its layout catalog by walking up to the repository root, a
path that does not exist inside an installed wheel. Because that read happens
at import time, the module could not even be imported. It now ships as package
data, and CI fails if the file is missing from the built wheel.

**The test suite installed packages into its own environment.** The Companion
launcher called its provisioner unconditionally, so any test reaching that path
ran a real `pip install`. It pulled in `websockets` partway through a run,
which flipped other tests from skipped to failing depending on order, and
inflated the suite to about seven minutes. There is now an opt-out
(`GENESIS_NO_AUTO_INSTALL=1`), a pytest safety net, and guard tests. The suite
runs in 38 seconds, fully offline.

## Licence

AGPL-3.0-or-later, changed from MIT. You can use, modify and redistribute
Genesis freely, including commercially. The one obligation is that if you
modify it and offer it to others over a network, you publish your modified
source under the same licence. Running it on your own code changes nothing.

Releases up to v5.4.1 were published under MIT and remain available under those
terms.

## Verification

2295 tests passing, 5 skipped, against a real `pip install` in a clean
container, plus 11 end-to-end CLI checks.
