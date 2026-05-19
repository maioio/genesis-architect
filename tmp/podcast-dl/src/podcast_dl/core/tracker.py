"""
JSON episode state tracker. Records which episode URLs have been downloaded
so repeat runs skip already-downloaded episodes.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def load_state(state_path: Path) -> set[str]:
    """Return set of already-downloaded episode URLs."""
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return set(data.get("downloaded", []))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read state file %s: %s - starting fresh", state_path, exc)
        return set()


def save_state(state_path: Path, downloaded: set[str]) -> None:
    """Persist the set of downloaded episode URLs atomically."""
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"downloaded": sorted(downloaded)}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(state_path)
    log.debug("State saved: %d episodes tracked", len(downloaded))


def is_downloaded(url: str, state: set[str]) -> bool:
    return url in state


def mark_downloaded(url: str, state: set[str]) -> None:
    state.add(url)
