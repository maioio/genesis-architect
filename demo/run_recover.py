"""Run `genesis recover` on the demo fixture and render a stable summary.

The numbers and findings come from a real run of the CLI, read from its
--json output. Nothing is typed by hand. Session ids, temp paths and
timestamps are left out so the file is reproducible.

    python demo/run_recover.py --write    # regenerate demo/output/recover.txt
    python demo/run_recover.py --check    # exit 1 if the committed file differs
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "output" / "recover.txt"


def run_recover() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "invoice-tool"
        shutil.copytree(HERE / "fixture", work)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "GENESIS_NO_AUTO_INSTALL": "1", "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            [sys.executable, "-m", "genesis_architect.cli_entry", "recover", ".", "--json"],
            cwd=work, env=env, capture_output=True, text=True, encoding="utf-8",
            stdin=subprocess.DEVNULL, timeout=180,
        )
        if proc.returncode != 0:
            sys.exit(f"recover failed ({proc.returncode}):\n{proc.stderr[-800:]}")
        written = sorted(p.name for p in work.iterdir() if p.name not in {"invoice_tool", ".gitignore"})
        data = json.loads(proc.stdout)
        data["_written"] = written
        return data


def render(data: dict) -> str:
    eng = data["report"]["engine_results"]
    lines = ["$ cd demo/fixture   # a four-file Python package, written for this demo",
             "$ genesis recover . --json", ""]
    lines.append(f"Genesis {data['version']}  mode={data['report']['mode']}")
    lines.append("")
    lines.append("Import graph")
    for cyc in eng["import_graph"]["output"]["cycles"]:
        lines.append("  cycle: " + " -> ".join(cyc))
    lines.append("")
    ap = eng["antipattern_detector"]["output"]
    lines.append(f"Anti-patterns ({ap['critical_count']} critical, {ap['high_count']} high)")
    for p in ap["patterns"]:
        lines.append(f"  [{p['severity']}] {p['type']} in {p['file']}")
        lines.append(f"    basis: {p['basis']}")
        lines.append(f"    fix:   {p['suggested_fix'].split(' Cycle:')[0]}")
    lines.append("")
    sc = eng["architecture_scorer"]["output"]
    dims = ", ".join(f"{k} {v:g}" for k, v in sc["dimensions"].items())
    lines.append(f"Architecture score: {sc['score']} / 100  ({dims})")
    lines.append("")
    lines.append("Fragility")
    for m in eng["fragility_classifier"]["output"]["fragility_map"]:
        lines.append(f"  {m['status']:<8} {m['module']}  ({m['go_hold_rewrite']})")
    lines.append("")
    lines.append("Skipped, and why")
    for name, res in eng.items():
        for w in res.get("warnings") or []:
            if "no git history" in w or "ANTHROPIC_API_KEY" in w:
                lines.append(f"  {name}: {w.replace(chr(0x2014), '-').replace(chr(0xfffd), '-')}")
    lines.append("")
    lines.append("Files written next to the project: " + ", ".join(data["_written"]))
    lines.append("Source files edited: none")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render(run_recover())
    if args.write:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    current = OUT.read_text(encoding="utf-8").replace("\r\n", "\n") if OUT.exists() else ""
    if current != text:
        print("demo/output/recover.txt is stale: run `python demo/run_recover.py --write`")
        return 1
    print("demo output is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
