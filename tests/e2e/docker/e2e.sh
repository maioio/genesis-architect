#!/usr/bin/env bash
# Genesis Architect Pro — clean-room E2E validation.
#
# Four phases, each fatal on its own. Nothing here is pre-provisioned: no
# voice packages, no STT/TTS models, no ~/.genesis, no TTY. That is the
# environment `genesis companion --ui` used to hang in.
set -uo pipefail

RC=0
hr() { printf '\n%s\n' "======================================================================"; }
phase() { hr; printf '  %s\n' "$1"; hr; }
fail() { printf '\n  >>> FAILED: %s\n' "$1"; RC=1; }

printf 'python   : %s\n' "$(python --version 2>&1)"
printf 'genesis  : %s\n' "$(python -c 'import genesis_architect_pro as p; print(p.__version__)' 2>&1)"
printf 'tty      : stdin=%s stdout=%s\n' \
  "$(python -c 'import sys; print(sys.stdin.isatty())')" \
  "$(python -c 'import sys; print(sys.stdout.isatty())')"

# ---------------------------------------------------------------------------
phase "PHASE 1/4 — full pytest suite"
# A 15-minute cap, not a guess: the suite runs in ~2 minutes. Anything near
# this ceiling means something is blocking, which is the bug under test.
timeout 900 python -m pytest -q -p no:cacheprovider --tb=short
case $? in
  0)   printf '\n  pytest: PASS\n' ;;
  124) fail "pytest exceeded 900s — something is blocking" ;;
  *)   fail "pytest reported failures" ;;
esac

# ---------------------------------------------------------------------------
phase "PHASE 2/4 — CLI smoke tests"
smoke() {
  local label="$1"; shift
  printf '\n--- %s ---\n' "$label"
  # 120s is generous for a command that should answer in under a second; it
  # exists to turn a hang into a reported failure instead of a stuck build.
  timeout 120 "$@"
  local rc=$?
  if [ $rc -eq 124 ]; then
    fail "$label hung (>120s)"
  elif [ $rc -ne 0 ]; then
    fail "$label exited $rc"
  else
    printf '  [ok] %s\n' "$label"
  fi
}

smoke "genesis --help"          genesis --help
smoke "genesis doctor"          genesis doctor
smoke "genesis doctor --json"   genesis doctor --json
smoke "genesis engines"         genesis engines
smoke "genesis engines --json"  genesis engines --json

# purge must be inspected in dry-run: without --apply it reports what it
# would remove and touches nothing, which is what belongs in a smoke test.
mkdir -p /tmp/purge-probe && (cd /tmp/purge-probe && git init -q . 2>/dev/null || true)
smoke "genesis purge (dry-run)" genesis purge --dir /tmp/purge-probe

# ---------------------------------------------------------------------------
phase "PHASE 3/4 — companion --ui must not provision headlessly"
# The regression: with no TTY, `--ui` used to pip-install the voice extras and
# download ~1-2 GB of models before returning. In this image none of that is
# present, so an unfixed build blocks here until the timeout.
mkdir -p /tmp/companion-probe
BEFORE=$(pip freeze | wc -l)
timeout 120 genesis companion --ui --no-browser --dir /tmp/companion-probe
rc=$?
AFTER=$(pip freeze | wc -l)

if [ $rc -eq 124 ]; then
  fail "genesis companion --ui hung (>120s) — the provisioning gate is not holding"
elif [ $rc -ne 0 ]; then
  fail "genesis companion --ui exited $rc"
else
  printf '  [ok] returned without blocking\n'
fi

if [ "$BEFORE" != "$AFTER" ]; then
  fail "companion --ui mutated the environment ($BEFORE -> $AFTER packages)"
else
  printf '  [ok] environment unchanged (%s packages before and after)\n' "$BEFORE"
fi

if [ -d "$HOME/.genesis/models" ] && [ -n "$(ls -A "$HOME/.genesis/models" 2>/dev/null)" ]; then
  fail "companion --ui downloaded models into ~/.genesis/models"
else
  printf '  [ok] no models downloaded\n'
fi

if [ -f /tmp/companion-probe/.genesis/ui/companion.html ]; then
  printf '  [ok] UI still written (degrades honestly, not silently)\n'
else
  fail "companion --ui produced no UI file"
fi

# ---------------------------------------------------------------------------
phase "PHASE 4/4 — R1-R6 pipeline E2E (outline -> deep -> report)"
timeout 300 python /usr/local/bin/r1_r6_e2e.py
case $? in
  0)   : ;;
  124) fail "R1-R6 E2E exceeded 300s" ;;
  *)   fail "R1-R6 E2E reported failing checks" ;;
esac

# ---------------------------------------------------------------------------
hr
if [ $RC -eq 0 ]; then
  printf '  E2E VALIDATION: ALL PHASES PASSED\n'
else
  printf '  E2E VALIDATION: FAILURES ABOVE\n'
fi
hr
exit $RC
