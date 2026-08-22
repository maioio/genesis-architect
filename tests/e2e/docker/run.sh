#!/usr/bin/env bash
# Build and run the clean-room E2E validation. See README.md.
#
#   ./run.sh                        # against genesis-architect from PyPI
#   ./run.sh --core /path/to/core   # against a local core checkout
#   ./run.sh --core-version 8.0.1   # pin the PyPI core
#   ./run.sh --keep                 # leave the staged context for inspection
#   ./run.sh --build-only
#
# Docker cannot read outside its build context, and the two halves of this
# product live in separate trees, so the context is staged here rather than
# pointed at the repo root.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
IMAGE="${GENESIS_E2E_IMAGE:-genesis-pro-e2e}"

CORE_PATH=""
CORE_VERSION=""
KEEP=0
BUILD_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --core)         CORE_PATH="${2:?--core needs a path}"; shift 2 ;;
    --core-version) CORE_VERSION="${2:?--core-version needs a version}"; shift 2 ;;
    --keep)         KEEP=1; shift ;;
    --build-only)   BUILD_ONLY=1; shift ;;
    -h|--help)      sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

CTX="$(mktemp -d)"
cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo "staged context kept at: $CTX"
  else
    rm -rf "$CTX"
  fi
}
trap cleanup EXIT

stage() {  # stage <src-root> <dest> <paths...>
  local src="$1" dest="$2"; shift 2
  mkdir -p "$dest"
  for path in "$@"; do
    [ -e "$src/$path" ] || { echo "missing from $src: $path" >&2; exit 1; }
    cp -r "$src/$path" "$dest/"
  done
  # Stale bytecode and editable-install metadata point at host paths and can
  # shadow what we actually want to test.
  find "$dest" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "$dest" -name "*.egg-info" -type d -prune -exec rm -rf {} + 2>/dev/null || true
}

# The working tree, not `git archive HEAD` — the point is to validate what is
# on disk right now, including changes not yet committed.
stage "$REPO" "$CTX/pro" pyproject.toml README.md src tests

if [ -n "$CORE_PATH" ]; then
  [ -d "$CORE_PATH" ] || { echo "no such core checkout: $CORE_PATH" >&2; exit 1; }
  CORE_SOURCE=local
  stage "$CORE_PATH" "$CTX/core" pyproject.toml README.md src
  echo "core: local checkout at $CORE_PATH"
else
  CORE_SOURCE=pypi
  # COPY needs the directory to exist even when nothing is installed from it.
  mkdir -p "$CTX/core" && touch "$CTX/core/.keep"
  echo "core: PyPI ${CORE_VERSION:-(latest)}"
fi

cp "$HERE/Dockerfile" "$HERE/e2e.sh" "$HERE/r1_r6_e2e.py" "$CTX/"

docker build \
  --build-arg "CORE_SOURCE=$CORE_SOURCE" \
  --build-arg "CORE_VERSION=$CORE_VERSION" \
  -t "$IMAGE" "$CTX"

[ "$BUILD_ONLY" -eq 1 ] && { echo "built $IMAGE"; exit 0; }

# No -t on purpose: the run must be headless, because "does this hang without
# a terminal?" is one of the things under test.
docker run --rm "$IMAGE"
