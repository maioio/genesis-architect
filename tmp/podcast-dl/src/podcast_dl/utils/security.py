"""
Security utilities: safe filename derivation and path guard.

# Architecture note: all output paths must go through safe_filename()
# Avoids: PITFALLS.md #4 (path traversal via enclosure URL)
#         PITFALLS.md #5 (non-ASCII titles corrupt filenames on Windows)
"""

import re
import unicodedata
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a derived path escapes the allowed output directory."""


def safe_filename(raw: str, max_length: int = 200) -> str:
    """
    Derive a filesystem-safe filename from a raw string (episode title or URL basename).

    Steps:
    1. Normalize Unicode to NFKD then encode to ASCII ignoring unmappable chars.
    2. Strip characters illegal on Windows or Unix.
    3. Collapse whitespace and truncate to max_length.
    4. Return a non-empty fallback if result is empty.
    """
    if not raw:
        return "episode"
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r'[\\/:*?"<>|\x00]', "_", normalized)
    cleaned = re.sub(r"[\s_]+", "_", cleaned).strip("_")
    cleaned = cleaned[:max_length]
    return cleaned or "episode"


def safe_output_path(output_dir: Path, filename: str) -> Path:
    """
    Resolve output_dir/filename and verify it stays inside output_dir.
    Raises PathTraversalError if the resolved path escapes.
    """
    resolved = (output_dir / filename).resolve()
    try:
        resolved.relative_to(output_dir.resolve())
    except ValueError:
        raise PathTraversalError(
            f"Derived path {resolved!r} escapes output directory {output_dir!r}"
        )
    return resolved
