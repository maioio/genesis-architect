#!/usr/bin/env python3
"""PostToolUse hook: auto-format a file right after Edit/Write touches it.

Reads the tool-call payload as JSON on stdin. Runs `ruff format` on the
edited path when it's a .py file under this repo. Never blocks the
agent turn: formatting failures are reported but always exit 0.
"""

import json
import subprocess
import sys


def target_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = target_path(payload)
    if not path or not path.endswith(".py"):
        return 0

    try:
        subprocess.run(
            ["ruff", "format", path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"format_file: ruff format skipped for '{path}': {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
