import os
import shutil
from pathlib import Path

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

def organize_files(source_dir: str, dry_run: bool = False) -> dict:
    source = Path(source_dir)
    moved = {}

    for file in source.iterdir():
        if not file.is_file():
            continue
        category = get_category(file.suffix)
        dest_dir = source / category
        dest = dest_dir / file.name

        if not dry_run:
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(file), str(dest))

        moved[str(file)] = str(dest)

    return moved
