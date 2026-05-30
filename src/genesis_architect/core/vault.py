"""Local Knowledge Vault - caches SO solutions with TTL + LRU eviction."""

import json
import time
from pathlib import Path

_MAX_ENTRIES = 500
_TTL_SECONDS = 60 * 60 * 24 * 180  # 6 months


def _vault_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".genesis" / "vault" / "index.json"


def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _evict_lru(data: dict) -> dict:
    if len(data) <= _MAX_ENTRIES:
        return data
    # sort by last_accessed ascending, drop oldest
    sorted_keys = sorted(data, key=lambda k: data[k].get("last_accessed", 0))
    for key in sorted_keys[:len(data) - _MAX_ENTRIES]:
        del data[key]
    return data


def get(key: str, project_root: str | Path = ".") -> dict | None:
    """Return cached entry or None. Updates last_accessed on hit."""
    path = _vault_path(project_root)
    data = _load(path)
    entry = data.get(key)
    if entry is None:
        return None
    entry["last_accessed"] = time.time()
    data[key] = entry
    _save(path, data)
    return entry


def put(key: str, solution: str, source_url: str, project_root: str | Path = ".") -> None:
    """Store a solution. Evicts LRU if over capacity."""
    path = _vault_path(project_root)
    data = _load(path)
    now = time.time()
    data[key] = {
        "solution": solution,
        "source_url": source_url,
        "created_at": now,
        "last_accessed": now,
    }
    data = _evict_lru(data)
    _save(path, data)


def is_stale(entry: dict) -> bool:
    return (time.time() - entry.get("created_at", 0)) > _TTL_SECONDS


def stats(project_root: str | Path = ".") -> dict:
    data = _load(_vault_path(project_root))
    stale = sum(1 for e in data.values() if is_stale(e))
    return {"total": len(data), "stale": stale, "capacity": _MAX_ENTRIES}
