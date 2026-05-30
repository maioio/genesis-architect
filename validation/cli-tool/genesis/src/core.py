# Architecture note: symlink check + safe_destination before every move
# Avoids: Pitfall 1 - shutil.move follows symlinks and moves target
# Avoids: Pitfall 2 - silent overwrite of existing files

import shutil
from pathlib import Path
from security import get_safe_path

EXTENSION_MAP = {
    "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    "documents": [".pdf", ".doc", ".docx", ".txt", ".md", ".csv"],
    "videos": [".mp4", ".avi", ".mov", ".mkv"],
    "audio": [".mp3", ".wav", ".flac", ".aac"],
    "archives": [".zip", ".tar", ".gz", ".rar"],
    "code": [".py", ".js", ".ts", ".html", ".css", ".json"],
}

def get_category(ext: str) -> str:
    for category, extensions in EXTENSION_MAP.items():
        if ext.lower() in extensions:
            return category
    return "other"

def safe_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    counter = 2
    while True:
        candidate = dest.parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def organize_files(source_dir: str, dry_run: bool = False) -> dict:
    source = Path(source_dir).resolve()
    result = {"moved": {}, "skipped": []}

    for file in source.iterdir():
        if file.is_symlink():
            result["skipped"].append({"file": str(file), "reason": "symlink"})
            continue
        if not file.is_file():
            continue

        category = get_category(file.suffix)
        dest_dir = source / category
        dest = safe_destination(dest_dir / file.name)

        if not dry_run:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(file), str(dest))

        result["moved"][str(file)] = str(dest)

    return result
