import re
from .exceptions import PatternError


def build_pattern(pattern: str, use_regex: bool = False) -> re.Pattern:
    """Compile a search pattern.

    Always re.escape() user strings unless --regex is explicit.
    Avoids pitfall #1 (raw user input passed to re.sub causing re.error).
    """
    try:
        if use_regex:
            return re.compile(pattern)
        return re.compile(re.escape(pattern))
    except re.error as e:
        raise PatternError(f"Invalid pattern '{pattern}': {e}") from e


def apply_pattern(name: str, pattern: re.Pattern, replacement: str, use_regex: bool = False) -> str:
    """Apply a compiled pattern to a filename stem."""
    repl = replacement if use_regex else replacement
    return pattern.sub(repl, name)
