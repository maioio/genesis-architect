"""
Security utilities: safe file access.
All file I/O using user-supplied paths must go through get_safe_path.
"""
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a path escapes the allowed base directory."""


def get_safe_path(base: Path, user_input: str) -> Path:
    """Resolve a user-supplied path and verify it stays inside base."""
    if not user_input:
        raise ValueError("Path must not be empty")
    if "\x00" in user_input:
        raise PathTraversalError("Null byte detected in path")
    resolved = (base / user_input).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise PathTraversalError(
            f"Path traversal blocked: {user_input!r} escapes {base}"
        )
    return resolved
