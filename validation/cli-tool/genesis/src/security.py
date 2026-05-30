# Architecture note: resolve+assert pattern - user input never trusted for filesystem ops
# Avoids: Pitfall 3 - path traversal via ../../ or malformed filenames

from pathlib import Path

def get_safe_path(base: Path, target: str) -> Path:
    base_resolved = base.resolve()
    target_resolved = Path(target).resolve()
    if not str(target_resolved).startswith(str(base_resolved)):
        raise ValueError(
            f"Path '{target}' resolves outside base '{base_resolved}'. "
            "This may be a path traversal attempt."
        )
    return target_resolved
