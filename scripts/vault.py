#!/usr/bin/env python3
"""
vault.py - Genesis Architect Knowledge Vault.

Stores and retrieves successful solutions locally under .genesis/vault/
so repeated problems don't require external API calls.

Eviction policy:
  - TTL: entries older than 6 months are considered stale.
  - Capacity: max 500 entries per project. When exceeded, the LRU entry is evicted.

Usage:
  python scripts/vault.py save "path traversal" python "Use get_safe_path..." --source https://...
  python scripts/vault.py search "path traversal" python
  python scripts/vault.py list
  python scripts/vault.py stats
  python scripts/vault.py evict          # dry run: show what would be evicted
  python scripts/vault.py evict --apply  # apply eviction now
"""

import json
import sys
import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

VAULT_DIR_NAME = ".genesis/vault"
MAX_ENTRIES = 500
TTL_DAYS = 180  # 6 months


def _vault_dir(project_root: Path) -> Path:
    return project_root / VAULT_DIR_NAME


def _safe_tag(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", text.lower().strip())[:40]


def _entry_id(topic: str, language: str) -> str:
    key = f"{topic.lower().strip()}:{language.lower().strip()}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]  # NOSONAR - non-cryptographic ID only


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _is_stale(entry: dict) -> bool:
    """True if the entry's saved_at is older than TTL_DAYS."""
    try:
        saved = _parse_ts(entry["saved_at"])
        return (datetime.now(timezone.utc) - saved) > timedelta(days=TTL_DAYS)
    except (KeyError, ValueError):
        return True


def _lru_key(entry: dict) -> datetime:
    """Sort key for LRU eviction: least recently used = smallest last_used_at."""
    try:
        return _parse_ts(entry.get("last_used_at") or entry["saved_at"])
    except (KeyError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _load_index(vault: Path) -> dict:
    index_path = vault / "index.json"
    if not index_path.exists():
        return {"entries": []}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("  Warning: vault index.json is corrupted. Starting fresh.")
        return {"entries": []}


def _save_index(vault: Path, index: dict) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    index_path = vault / "index.json"
    tmp_path = vault / "index.json.tmp"
    tmp_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(index_path)


def _enforce_capacity(vault: Path, index: dict) -> dict:
    """Evict LRU entries until len <= MAX_ENTRIES. Mutates and returns index."""
    entries = index["entries"]
    while len(entries) > MAX_ENTRIES:
        # Sort ascending by last use time - first element is least recently used
        entries.sort(key=_lru_key)
        evicted = entries.pop(0)
        entry_file = vault / f"{evicted['id']}.json"
        if entry_file.exists():
            entry_file.unlink()
    index["entries"] = entries
    return index


def save(
    topic: str,
    language: str,
    solution: str,
    source: str = "",
    project_root: Path | None = None,
) -> str:
    root = project_root or Path.cwd()
    vault = _vault_dir(root)
    entry_id = _entry_id(topic, language)
    index = _load_index(vault)

    existing = next((e for e in index["entries"] if e["id"] == entry_id), None)
    now = _now_ts()
    entry = {
        "id": entry_id,
        "topic": topic,
        "language": _safe_tag(language),
        "solution": solution,
        "source": source,
        "saved_at": now,
        "last_used_at": now,
        "use_count": (existing["use_count"] + 1) if existing else 1,
    }

    if existing:
        index["entries"] = [e if e["id"] != entry_id else entry for e in index["entries"]]
    else:
        index["entries"].append(entry)
        index = _enforce_capacity(vault, index)

    _save_index(vault, index)
    vault.mkdir(parents=True, exist_ok=True)
    entry_file = vault / f"{entry_id}.json"
    entry_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry_id


def _touch_last_used(vault: Path, index: dict, entry_id: str) -> None:
    """Update last_used_at without changing saved_at."""
    now = _now_ts()
    for e in index["entries"]:
        if e["id"] == entry_id:
            e["last_used_at"] = now
            e["use_count"] = e.get("use_count", 0) + 1
            break
    _save_index(vault, index)


def search(
    topic: str,
    language: str = "",
    project_root: Path | None = None,
) -> list[dict]:
    """
    Returns matching entries. Stale entries (TTL expired) are flagged with
    `stale: True` so the caller (resolve_engine) can attempt a refresh.
    """
    root = project_root or Path.cwd()
    vault = _vault_dir(root)
    index = _load_index(vault)

    _STOP_WORDS = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "it"}

    topic_lower = topic.lower()
    lang_lower = language.lower()
    query_words = [w for w in topic_lower.split() if w not in _STOP_WORDS and len(w) > 2]

    scored: list[tuple[int, dict]] = []
    for entry in index["entries"]:
        entry_topic = entry["topic"].lower()
        lang_match = not lang_lower or lang_lower in entry["language"]
        if not lang_match:
            continue

        score = 0
        if topic_lower in entry_topic:
            score += 10
        for w in query_words:
            if w in entry_topic:
                score += 1
        score += min(entry.get("use_count", 0), 5)

        if score > 0:
            annotated = dict(entry)
            annotated["stale"] = _is_stale(entry)
            scored.append((score, annotated))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [e for _, e in scored]

    # Update last_used_at for every returned entry
    for e in results:
        _touch_last_used(vault, index, e["id"])

    return results


def list_all(project_root: Path | None = None) -> list[dict]:
    root = project_root or Path.cwd()
    entries = _load_index(_vault_dir(root))["entries"]
    for e in entries:
        e["stale"] = _is_stale(e)
    return entries


def stats(project_root: Path | None = None) -> dict:
    entries = list_all(project_root)
    languages: dict[str, int] = {}
    stale_count = 0
    for e in entries:
        languages[e["language"]] = languages.get(e["language"], 0) + 1
        if e.get("stale"):
            stale_count += 1
    return {
        "total_entries": len(entries),
        "stale_entries": stale_count,
        "capacity_used": f"{len(entries)}/{MAX_ENTRIES}",
        "by_language": languages,
        "total_uses": sum(e["use_count"] for e in entries),
    }


def evict_stale(project_root: Path | None = None, apply: bool = False) -> list[dict]:
    """Return stale entries. If apply=True, remove them from vault."""
    root = project_root or Path.cwd()
    vault = _vault_dir(root)
    index = _load_index(vault)
    stale = [e for e in index["entries"] if _is_stale(e)]
    if apply and stale:
        stale_ids = {e["id"] for e in stale}
        index["entries"] = [e for e in index["entries"] if e["id"] not in stale_ids]
        for e in stale:
            f = vault / f"{e['id']}.json"
            if f.exists():
                f.unlink()
        _save_index(vault, index)
    return stale


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _print_entry(entry: dict, idx: int) -> None:
    stale_tag = " [STALE]" if entry.get("stale") else ""
    print(f"\n  [{idx}] {entry['topic']} ({entry['language']}){stale_tag}")
    print(f"      Used {entry['use_count']} time(s) | saved {entry['saved_at'][:10]}")
    preview = entry["solution"][:200].replace("\n", " ")
    if len(entry["solution"]) > 200:
        preview += " ..."
    print(f"      {preview}")
    if entry.get("source"):
        print(f"      Source: {entry['source']}")


def _cmd_save(argv: list) -> None:
    if len(argv) < 5:
        print('Usage: vault.py save "<topic>" <language> "<solution>" [--source <url>]')
        sys.exit(1)
    topic, language, solution = argv[2], argv[3], argv[4]
    source = ""
    if "--source" in argv:
        idx = argv.index("--source")
        source = argv[idx + 1] if idx + 1 < len(argv) else ""
    entry_id = save(topic, language, solution, source)
    print(f"Saved: {entry_id} ({topic} / {language})")


def _cmd_search(argv: list) -> None:
    if len(argv) < 3:
        print('Usage: vault.py search "<topic>" [language]')
        sys.exit(1)
    topic = argv[2]
    language = argv[3] if len(argv) > 3 else ""
    results = search(topic, language)
    if not results:
        print(f"No vault entries for: {topic!r} {language!r}")
        print("Try: genesis resolve [topic] to fetch from Stack Overflow")
        sys.exit(0)
    print(f"Vault: {len(results)} result(s) for {topic!r}")
    for i, entry in enumerate(results, 1):
        _print_entry(entry, i)


def _cmd_list() -> None:
    entries = list_all()
    if not entries:
        print("Vault is empty. Use 'vault.py save' to add entries.")
        sys.exit(0)
    print(f"Vault: {len(entries)} entries")
    for i, entry in enumerate(entries, 1):
        _print_entry(entry, i)


def _cmd_stats() -> None:
    s = stats()
    print("Vault stats:")
    print(f"  Total entries:    {s['total_entries']}")
    print(f"  Stale (>6 months): {s['stale_entries']}")
    print(f"  Capacity:         {s['capacity_used']}")
    print(f"  Total uses:       {s['total_uses']}")
    print(f"  By language:      {s['by_language']}")


def _cmd_evict(argv: list) -> None:
    apply = "--apply" in argv
    stale = evict_stale(apply=apply)
    if not stale:
        print("No stale entries found.")
        return
    action = "Evicted" if apply else "Would evict (dry run - use --apply to confirm)"
    print(f"{action}: {len(stale)} stale entries")
    for e in stale:
        print(f"  - {e['topic']} ({e['language']}) saved {e['saved_at'][:10]}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python vault.py <save|search|list|stats|evict> [args]")
        sys.exit(1)

    command = sys.argv[1]
    dispatch = {
        "save": lambda: _cmd_save(sys.argv),
        "search": lambda: _cmd_search(sys.argv),
        "list": _cmd_list,
        "stats": _cmd_stats,
        "evict": lambda: _cmd_evict(sys.argv),
    }
    handler = dispatch.get(command)
    if handler is None:
        print(f"Unknown command: {command}")
        sys.exit(1)
    handler()


if __name__ == "__main__":
    main()
