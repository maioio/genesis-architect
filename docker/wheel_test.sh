#!/usr/bin/env bash
# Acceptance test for the built wheel: does the thing a user downloads work?
#
# Runs with no source tree, no references/, no tests directory. Anything that
# passes here passes for a real `pip install genesis-architect`.
set -euo pipefail

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Sanity: we are NOT running from a source checkout"
[ ! -d /work/src ] || fail "a source tree is present, this test proves nothing"
[ ! -d /work/references ] || fail "references/ is present, the fallback path would mask bugs"
pass "clean environment, wheel only"

step "Package metadata"
version=$(python -c "import genesis_architect; print(genesis_architect.__version__)")
[ "$version" = "8.0.0" ] || fail "expected version 8.0.0, got $version"
pass "version $version"

license=$(python -c "import genesis_architect; print(genesis_architect.__license__)")
[ "$license" = "AGPL-3.0-or-later" ] || fail "unexpected license: $license"
pass "license $license"

step "Package data actually shipped"
# These are read at import time. If they are missing the module is unimportable
# and the CLI dies, which is the bug this whole file exists to prevent.
python - <<'PY' || fail "package data missing from the wheel"
from pathlib import Path
from genesis_architect.core.scaffold_generator import _TOML_PATH, STRUCTURES
assert _TOML_PATH.is_file(), f"missing: {_TOML_PATH}"
assert STRUCTURES, "layout catalog parsed empty"
assert "python" in STRUCTURES, sorted(STRUCTURES)
from genesis_architect.pro.source_registry import _PACKAGE_DATA
assert _PACKAGE_DATA.is_file(), f"missing: {_PACKAGE_DATA}"
PY
pass "layout catalog + source registry present and parseable"

step "CLI entry point resolves"
command -v genesis >/dev/null || fail "genesis not on PATH"
genesis --help >/dev/null 2>&1 || fail "genesis --help"
pass "genesis --help"

step "Nothing is license-gated"
genesis decide --classify-only "diagnose the project and identify drift" >/dev/null \
  || fail "engine command blocked (paywall regression)"
pass "engine commands run freely"

out="$(genesis license 2>&1)"
grep -qi "free" <<<"$out" || fail "genesis license should report free"
pass "genesis license reports free"

python - <<'PY' || fail "licensing module is back"
import importlib, sys
try:
    importlib.import_module("genesis_architect.pro.license")
except ModuleNotFoundError:
    sys.exit(0)
sys.exit(1)
PY
pass "no licensing module in the distribution"

step "Scaffolding works from the wheel"
# This is the exact path that used to be dead on a real install.
python -m genesis_architect.core.scaffold_generator \
  --language python --tier minimalist --name demo --output /work/demo >/dev/null 2>&1 \
  || python -c "
from genesis_architect.core.scaffold_generator import create_structure
create_structure('/work/demo', 'python', 'minimalist', 'demo')
" || fail "scaffold generation"
[ -f /work/demo/pyproject.toml ] || fail "scaffold produced no pyproject.toml"
pass "scaffold generated real files"

step "Analysis engines on a real project"
mkdir -p /work/sample/src/app
printf 'from app import core\n\ndef run():\n    return core.compute()\n' > /work/sample/src/app/main.py
printf 'def compute():\n    return 42\n' > /work/sample/src/app/core.py
touch /work/sample/src/app/__init__.py
printf '[project]\nname = "sample"\nversion = "0.1.0"\n' > /work/sample/pyproject.toml
(cd /work/sample && git init -q && git add -A && git commit -qm init)

genesis recover /work/sample --classify-only >/dev/null || fail "genesis recover"
pass "genesis recover"
genesis harden /work/sample --classify-only >/dev/null || fail "genesis harden"
pass "genesis harden"
genesis doctor >/dev/null || fail "genesis doctor"
pass "genesis doctor"

python - <<'PY' || fail "engine pipeline"
from genesis_architect.pro.import_graph import build_graph
from genesis_architect.pro.c4_generator import generate_c4_doc
from genesis_architect.pro.knowledge_graph import build_from_project

g = build_graph("/work/sample", save=True)
assert g["module_count"] >= 2 and g["edge_count"] >= 1, g

doc = generate_c4_doc("/work/sample")
for level in ("C4Context", "C4Container", "C4Component"):
    assert level in doc, f"missing {level}"

kg = build_from_project("/work/sample",
                        architecture={"modules": sorted(g["modules"])})
assert kg.stats()["nodes"] >= g["module_count"], kg.stats()
PY
pass "import graph, C4 (all 3 levels), knowledge graph"

printf '\n\033[32mWheel acceptance test passed. This artifact is shippable.\033[0m\n\n'
