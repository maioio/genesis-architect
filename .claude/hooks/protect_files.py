#!/usr/bin/env python3
"""PreToolUse hook: block Edit/Write on protected paths.

Reads the tool-call payload as JSON on stdin. Exits 2 (block) if the
target path matches a protected pattern, 0 (allow) otherwise.
"""

import json
import re
import sys

PROTECTED_PATTERNS = [
    r"(^|/)\.env(\.|$)",
    r"(^|/)\.env\.[^.]+$",
    r"(^|/)\.git/",
    r"(^|/)uv\.lock$",
    r"(^|/)poetry\.lock$",
    r"(^|/)package-lock\.json$",
    r"(^|/)pnpm-lock\.yaml$",
    r"(^|/)yarn\.lock$",
]


def target_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = target_path(payload)
    if not path:
        return 0

    normalized = path.replace("\\", "/")
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, normalized):
            print(f"Blocked: '{path}' matches protected pattern '{pattern}'", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
