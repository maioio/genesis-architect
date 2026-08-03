#!/usr/bin/env bash
# End-to-end smoke test: proves a fresh install actually works, not just that
# the unit tests pass. Every command below is one a real user would run.
#
# Exits non-zero on the first failure so CI stops at the broken step.
set -euo pipefail

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Unit + integration suite"
pytest -q --no-header -p no:cacheprovider

step "CLI is installed and dispatches"
genesis --help > /dev/null 2>&1 || fail "genesis --help"
pass "genesis --help"

step "Nothing is license-gated"
# The gate used to exit 2 here. Anything non-zero means a paywall came back.
genesis decide --classify-only "diagnose the project and identify drift" > /dev/null \
  || fail "engine command was blocked (paywall regression?)"
pass "engine commands run without a license"

out="$(genesis license 2>&1)"
grep -qi "free" <<<"$out" || fail "genesis license should say it is free"
grep -qi "open source" <<<"$out" || fail "genesis license should say open source"
pass "genesis license reports free/open source"

python - <<'PY' || exit 1
import importlib, sys
try:
    importlib.import_module("genesis_architect.pro.license")
except ModuleNotFoundError:
    sys.exit(0)
print("FAIL: licensing module still present", file=sys.stderr)
sys.exit(1)
PY
pass "licensing module is gone, not merely bypassed"

step "Engine layer imports"
python -c "
import genesis_architect
from genesis_architect.core import pro_bridge
from genesis_architect.pro import GenesisDecisionEngine
assert pro_bridge.pro_installed() is True
assert pro_bridge.get_pro_module('import_graph').__name__ == 'genesis_architect.pro.import_graph'
GenesisDecisionEngine()
" || fail "engine layer import"
pass "engines import and instantiate"

step "Real analysis on a real project"
work="$(mktemp -d)"
mkdir -p "$work/sample/src/app"
cat > "$work/sample/src/app/main.py" <<'PY'
from app import core

def run():
    return core.compute()
PY
cat > "$work/sample/src/app/core.py" <<'PY'
def compute():
    return 42
PY
touch "$work/sample/src/app/__init__.py"
cat > "$work/sample/pyproject.toml" <<'TOML'
[project]
name = "sample"
version = "0.1.0"
TOML
(cd "$work/sample" && git init -q && git add -A && git commit -qm "init")

genesis recover "$work/sample" --classify-only > /dev/null || fail "genesis recover"
pass "genesis recover"

genesis harden "$work/sample" --classify-only > /dev/null || fail "genesis harden"
pass "genesis harden"

# save=True persists .genesis/import_graph.json, which the C4 generator reads.
# This mirrors the real pipeline order (import graph engine, then C4).
python -c "
from genesis_architect.pro.import_graph import build_graph
g = build_graph('$work/sample', save=True)
assert g['module_count'] >= 2, g
assert g['edge_count'] >= 1, 'import edge between main.py and core.py not detected'
" || fail "import graph did not resolve real edges"
pass "import graph resolves real edges"

python -c "
from genesis_architect.pro.c4_generator import generate_c4_doc
doc = generate_c4_doc('$work/sample')
assert 'C4Context' in doc, 'Level 1 missing'
assert 'C4Container' in doc, 'Level 2 missing'
assert 'C4Component' in doc, 'Level 3 (formerly Pro-only) missing'
assert 'core.py' in doc, 'real module absent from component diagram'
" || fail "C4 generation"
pass "C4 diagram includes formerly-Pro Level 3"

# build_from_project is deliberately additive and never invents nodes, so it
# is fed real engine output (the modules resolved by the import graph above).
python -c "
from genesis_architect.pro.import_graph import load_or_build
from genesis_architect.pro.knowledge_graph import build_from_project, load_graph

modules = sorted(load_or_build('$work/sample')['modules'])
g = build_from_project('$work/sample', architecture={'modules': modules})
assert g.stats()['nodes'] >= len(modules), g.stats()

# it must survive a round-trip to disk, which is how other engines read it
reloaded = load_graph('$work/sample')
assert reloaded.stats()['nodes'] == g.stats()['nodes'], 'graph did not persist'
assert reloaded.query(['module']), 'no module nodes after reload'
" || fail "knowledge graph"
pass "knowledge graph builds and persists"

genesis doctor > /dev/null || fail "genesis doctor reported not ready"
pass "genesis doctor: ready"

rm -rf "$work"
printf '\n\033[32mAll smoke tests passed.\033[0m\n\n'
