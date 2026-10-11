# Demo

Two flows, one rule: nothing here is written by hand. The output in `output/` is produced by
running the CLI and rendering its `--json` result.

## Existing code: `genesis recover`

The fixture in [`fixture/invoice_tool/`](fixture/invoice_tool/) is a four-file Python package
written for this demo. `models.py` and `billing.py` import each other, and `cli.py` has a bare
`except: pass`.

```bash
python demo/run_recover.py --write   # run recover on a temp copy, regenerate output/recover.txt
python demo/run_recover.py --check   # fail if the committed output is stale
```

The script copies the fixture to a temporary directory outside any repository first, because
`recover` writes `.genesis/` and `FRAGILITY_MAP.md` into the project it analyses. It does not
edit source files. Captured result: [`output/recover.txt`](output/recover.txt).

It shows the import cycle, one critical `circular-dep` anti-pattern with its suggested fix, an
architecture score, and which modules are fragile. It also lists what was skipped and why: no git
history in the copy, and no `ANTHROPIC_API_KEY`, so the optional red-team pass did not run.

## New project: `genesis init`

`init` researches GitHub, shows pitfalls with their sources, asks you to choose an architecture,
and scaffolds only after you approve. It needs an LLM key and network access, so its output
depends on live repositories and changes between runs. No captured `init` transcript is
committed, because a hand-edited one would be fabricated.

To record your own:

```bash
pip install genesis-architect
genesis config set LLM_API_KEY <your key>
genesis init "a Python CLI for analyzing log files"
```

For real research output produced by Genesis on its own codebase, see
[`docs/self-audit/`](../docs/self-audit/) (`research.md`, `pitfalls.md`, `roadmap.md`).
