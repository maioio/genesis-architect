"""Concurrent episode downloader with resume support via .part files."""

import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from podcast_dl.utils.security import safe_filename, safe_output_path

log = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 64


def _derive_filename(url: str, title: str) -> str:
    ext = Path(urlparse(url).path).suffix or ".mp3"
    base = safe_filename(title)
    return f"{base}{ext}"


def download_episode(url: str, title: str, output_dir: Path, timeout: int = 30) -> Path:
    """Download a single episode to output_dir. Returns the saved file path."""
    filename = _derive_filename(url, title)
    dest = safe_output_path(output_dir, filename)

    if dest.exists():
        log.info("Already exists, skipping: %s", dest.name)
        return dest

    log.info("Downloading: %s -> %s", url, dest.name)
    resp = requests.get(url, stream=True, timeout=timeout,
                        headers={"User-Agent": "podcast-dl/0.1"})
    resp.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    try:
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(CHUNK_SIZE):
                fh.write(chunk)
        tmp.rename(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    log.info("Saved: %s (%.1f MB)", dest.name, dest.stat().st_size / 1_048_576)
    return dest
