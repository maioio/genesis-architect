"""
Core logic module.
Architecture note: pure functions only - no Click imports, no side effects.
Inspired by pallets/click ecosystem - avoids tight coupling (see PITFALLS.md #1)
"""
from pathlib import Path
from .utils.security import get_safe_path


def process_file(input_path: str, output_path: str | None = None) -> dict:
    """Process input file and return result summary."""
    base = Path.cwd()
    safe_input = get_safe_path(base, input_path)
    if not safe_input.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    content = safe_input.read_text(encoding="utf-8")
    lines = content.splitlines()
    result = {
        "lines": len(lines),
        "chars": len(content),
        "words": len(content.split()),
    }
    if output_path:
        safe_output = get_safe_path(base, output_path)
        safe_output.write_text(str(result), encoding="utf-8")
    return result
