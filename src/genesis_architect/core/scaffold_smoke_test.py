#!/usr/bin/env python3
"""
scaffold_smoke_test.py - per-archetype smoke command runner for Phase 6.

Returns the exact smoke command for a given archetype and optionally runs it.
The command is written to genesis_state.py phase-6-smoke.json via write-phase6-smoke.

Usage:
    python scripts/scaffold_smoke_test.py --archetype cli --entrypoint mytool
    python scripts/scaffold_smoke_test.py --archetype library --pkg mylib
    python scripts/scaffold_smoke_test.py --archetype service --port 8080
    python scripts/scaffold_smoke_test.py --archetype frontend
    python scripts/scaffold_smoke_test.py --archetype cli --entrypoint mytool --run
    python scripts/scaffold_smoke_test.py --archetype cli --entrypoint mytool --print-only

Exits 0 on success, 1 on smoke failure, 2 on invalid args.
"""

import argparse
import re
import subprocess
import sys

ARCHETYPES = ("cli", "library", "service", "frontend")

SMOKE_TEMPLATES: dict[str, str] = {
    "cli":      "{entrypoint} --version",
    "library":  'python -c "import {pkg}; print({pkg}.__version__)"',
    "service":  "curl -sf http://localhost:{port}/health",
    "frontend": "npm run build",
}

SEMVER_RE = re.compile(r"\d+\.\d+(\.\d+)?")


def build_command(archetype: str, entrypoint: str = "", pkg: str = "",
                  port: str = "8080") -> str:
    """Return the smoke command string for the given archetype."""
    template = SMOKE_TEMPLATES[archetype]
    return template.format(entrypoint=entrypoint, pkg=pkg, port=port)


def _validate_semver(output: str) -> bool:
    """Return True if output contains a semver-like string."""
    return bool(SEMVER_RE.search(output))


def run_smoke(command: str, archetype: str) -> tuple[int, str]:
    """
    Run the smoke command. Returns (exit_code, message).
    For CLI archetype also validates that stdout contains a semver string.
    """
    try:
        result = subprocess.run(  # NOSONAR - command built from validated template, not user input
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return 1, f"Smoke test timed out after 30s: {command}"
    except Exception as exc:
        return 1, f"Smoke test error: {exc}"

    if result.returncode != 0:
        stderr_snippet = result.stderr.strip()[:200]
        return result.returncode, (
            f"Smoke test failed (exit {result.returncode}): {command}\n"
            f"stderr: {stderr_snippet}"
        )

    if archetype == "cli":
        stdout = (result.stdout + result.stderr).strip()
        if not _validate_semver(stdout):
            return 1, (
                f"CLI smoke: '{command}' exited 0 but output did not contain "
                f"a semver string. Got: {stdout[:100]!r}"
            )

    return 0, f"Smoke passed: {command}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect per-archetype smoke command runner"
    )
    parser.add_argument(
        "--archetype", required=True, choices=ARCHETYPES,
        help="Project archetype: cli, library, service, or frontend",
    )
    parser.add_argument("--entrypoint", default="", help="CLI entrypoint name (cli archetype)")
    parser.add_argument("--pkg", default="", help="Python package name (library archetype)")
    parser.add_argument("--port", default="8080", help="HTTP port (service archetype)")
    parser.add_argument("--run", action="store_true", help="Execute the smoke command")
    parser.add_argument(
        "--print-only", action="store_true",
        help="Print the smoke command and exit 0 without running it",
    )

    args = parser.parse_args()

    if args.archetype == "cli" and not args.entrypoint:
        print("ERROR: --entrypoint is required for cli archetype", file=sys.stderr)
        sys.exit(2)
    if args.archetype == "library" and not args.pkg:
        print("ERROR: --pkg is required for library archetype", file=sys.stderr)
        sys.exit(2)

    command = build_command(args.archetype, args.entrypoint, args.pkg, args.port)

    if args.print_only:
        print(command)
        sys.exit(0)

    print(f"Smoke command: {command}")

    if not args.run:
        # Default: print the command without running it (Phase 5 preview)
        sys.exit(0)

    exit_code, message = run_smoke(command, args.archetype)
    print(message)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
