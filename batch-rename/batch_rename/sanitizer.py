import re
from pathlib import Path

# Characters illegal on Windows; also strip leading/trailing dots and spaces
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str) -> str:
    """Replace illegal characters and strip unsafe edges.

    Called exactly once, at final path construction - never in intermediate steps.
    Avoids pitfall #3 (duplicate sanitization causing double-extension corruption).
    """
    stem = Path(name).stem
    suffix = "".join(Path(name).suffixes)  # preserves double extensions like .en.srt

    clean_stem = _ILLEGAL.sub("_", stem).strip(". ")
    if not clean_stem or clean_stem.upper() in _RESERVED:
        clean_stem = "_" + clean_stem

    return clean_stem + suffix
