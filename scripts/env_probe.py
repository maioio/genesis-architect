#!/usr/bin/env python3
"""
env_probe.py - Genesis Architect

Phase 0 environment probe. Detects OS, Python version, available package
managers, and (on Windows) the Python Scripts directory. Returns JSON so the
skill can consume the result deterministically instead of re-running detection
inline every time.

Usage:
  python scripts/env_probe.py
  python scripts/env_probe.py --pretty       # human-readable indent
  python scripts/env_probe.py --self-check   # assert required keys are present (for CI)
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys


# Order matters: the first available manager is the one most projects in this
# environment are likely to use. uv before pip (uv is a superset for Python),
# pnpm/yarn before npm (they're explicit choices when present).
PYTHON_PACKAGE_MANAGERS = ["uv", "pip"]
NODE_PACKAGE_MANAGERS = ["pnpm", "yarn", "npm"]


def detect_os() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    if system == "Windows":
        return "windows"
    return system.lower()


def detect_wsl() -> bool:
    """True if running inside WSL on Windows. Reliable across WSL1 and WSL2."""
    if detect_os() != "linux":
        return False
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def detect_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def detect_package_managers() -> dict:
    """Return the first available manager per ecosystem (or null if none found)."""
    return {
        "python": next((m for m in PYTHON_PACKAGE_MANAGERS if shutil.which(m)), None),
        "node": next((m for m in NODE_PACKAGE_MANAGERS if shutil.which(m)), None),
    }


def detect_windows_scripts_path() -> str | None:
    """
    Returns the Python Scripts directory on Windows (where pip-installed CLIs
    land). SKILL.md Phase 0 uses this to fix PATH after `pip install -e .`.
    Returns null on non-Windows systems.
    """
    if detect_os() != "windows":
        return None
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import sysconfig; print(sysconfig.get_path('scripts'))"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def probe() -> dict:
    return {
        "os": detect_os(),
        "wsl": detect_wsl(),
        "python_version": detect_python_version(),
        "package_managers": detect_package_managers(),
        "windows_scripts_path": detect_windows_scripts_path(),
    }


REQUIRED_KEYS = ["os", "wsl", "python_version", "package_managers", "windows_scripts_path"]


def self_check(report: dict) -> list[str]:
    """Return a list of validation errors. Empty list = pass."""
    errors = []
    for key in REQUIRED_KEYS:
        if key not in report:
            errors.append(f"missing key: {key}")
    if "os" in report and report["os"] not in {"macos", "linux", "windows"}:
        errors.append(f"unexpected os value: {report['os']!r}")
    if "package_managers" in report:
        pm = report["package_managers"]
        if not isinstance(pm, dict) or set(pm.keys()) != {"python", "node"}:
            errors.append(f"package_managers must have keys python+node, got {pm!r}")
    if report.get("os") == "windows" and report.get("windows_scripts_path") is None:
        errors.append("windows_scripts_path must be set when os=windows")
    if report.get("os") != "windows" and report.get("windows_scripts_path") is not None:
        errors.append("windows_scripts_path must be null when os!=windows")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis Architect - Phase 0 environment probe")
    parser.add_argument("--pretty", action="store_true", help="indent the JSON output")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="validate the report shape and exit non-zero on failure (used by CI)",
    )
    args = parser.parse_args()

    report = probe()

    if args.self_check:
        errors = self_check(report)
        if errors:
            print("env_probe self-check FAILED:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print("env_probe self-check OK", file=sys.stderr)

    print(json.dumps(report, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
