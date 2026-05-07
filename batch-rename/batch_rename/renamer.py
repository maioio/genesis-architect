from pathlib import Path
import re

from .exceptions import PatternError
from .patterns import build_pattern, apply_pattern
from .sanitizer import sanitize_filename
from .log import write_log


RenameResult = tuple[Path, Path]  # (original, new)


def plan_renames(
    files: list[Path],
    search: str,
    replacement: str,
    use_regex: bool = False,
    prefix: str = "",
    suffix: str = "",
    counter_start: int | None = None,
) -> list[RenameResult]:
    """Compute renames without touching the filesystem (pure function).

    Separates planning from execution - enables dry-run and testing without real files.
    Sanitizes exactly once at final path construction (avoids pitfall #3).
    """
    pattern = build_pattern(search, use_regex) if search else None
    results: list[RenameResult] = []

    for i, path in enumerate(files):
        stem = path.stem
        suffixes = "".join(path.suffixes)  # preserves .en.srt style double extensions

        new_stem = stem
        if pattern:
            new_stem = apply_pattern(new_stem, pattern, replacement, use_regex)

        if prefix:
            new_stem = prefix + new_stem
        if suffix:
            new_stem = new_stem + suffix
        if counter_start is not None:
            new_stem = f"{new_stem}_{counter_start + i:04d}"

        new_name = sanitize_filename(new_stem + suffixes)
        new_path = path.parent / new_name
        results.append((path, new_path))

    return results


def execute_renames(
    plan: list[RenameResult],
    copy: bool = False,
    write_undo_log: bool = True,
) -> list[RenameResult]:
    """Execute a rename plan on the filesystem.

    Avoids pitfall #5: writes undo log before returning.
    Supports --copy mode to preserve originals.
    """
    import shutil

    completed: list[RenameResult] = []
    for src, dst in plan:
        if dst.exists() and src != dst:
            print(f"[skip] Would overwrite existing file: {dst}")
            continue
        if copy:
            shutil.copy2(src, dst)
        else:
            src.rename(dst)
        completed.append((src, dst))

    if completed and write_undo_log:
        log_dir = completed[0][0].parent
        log_path = write_log(completed, log_dir)
        print(f"[log] Undo log written to {log_path}")

    return completed
