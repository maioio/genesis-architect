#!/usr/bin/env python3
"""
vault.py - Genesis Architect Knowledge Vault.

Stores and retrieves successful solutions locally under .genesis/vault/
so repeated problems don't require external API calls.

Usage:
  python scripts/vault.py save "path traversal" python "Use get_safe_path..." --source https://...
  python scripts/vault.py search "path traversal" python
  python scripts/vault.py list
  python scripts/vault.py stats
"""

import json
import sys
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

VAULT_DIR_NAME = ".genesis/vault"


def _vault_dir(project_root: Path) -> Path:
    return project_root / VAULT_DIR_NAME


def _safe_tag(text: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", text.lower().strip())[:40]


def _entry_id(topic: str, language: str) -> str:
    key = f"{topic.lower().strip()}:{language.lower().strip()}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]  # NOSONAR - non-cryptographic ID only


def _load_index(vault: Path) -> dict:
    index_path = vault / "index.json"
    if not index_path.exists():
        return {"entries": []}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"  Warning: vault index.json is corrupted. Starting fresh.")
        return {"entries": []}


def _save_index(vault: Path, index: dict) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    index_path = vault / "index.json"
    tmp_path = vault / "index.json.tmp"
    tmp_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(index_path)


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
    entry = {
        "id": entry_id,
        "topic": topic,
        "language": _safe_tag(language),
        "solution": solution,
        "source": source,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "use_count": (existing["use_count"] + 1) if existing else 1,
    }

    if existing:
        index["entries"] = [e if e["id"] != entry_id else entry for e in index["entries"]]
    else:
        index["entries"].append(entry)

    _save_index(vault, index)
    vault.mkdir(parents=True, exist_ok=True)
    entry_file = vault / f"{entry_id}.json"
    entry_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry_id


def search(topic: str, language: str = "", project_root: Path | None = None) -> list[dict]:
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
        # Exact phrase match scores highest
        if topic_lower in entry_topic:
            score += 10
        # Each meaningful word match adds 1
        for w in query_words:
            if w in entry_topic:
                score += 1
        # Popularity boost
        score += min(entry.get("use_count", 0), 5)

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored]


def list_all(project_root: Path | None = None) -> list[dict]:
    root = project_root or Path.cwd()
    return _load_index(_vault_dir(root))["entries"]


def stats(project_root: Path | None = None) -> dict:
    entries = list_all(project_root)
    languages: dict[str, int] = {}
    for e in entries:
        languages[e["language"]] = languages.get(e["language"], 0) + 1
    return {
        "total_entries": len(entries),
        "by_language": languages,
        "total_uses": sum(e["use_count"] for e in entries),
    }


def _print_entry(entry: dict, index: int) -> None:
    print(f"\n  [{index}] {entry['topic']} ({entry['language']})")
    print(f"      Used {entry['use_count']} time(s) | saved {entry['saved_at'][:10]}")
    preview = entry["solution"][:200].replace("\n", " ")
    if len(entry["solution"]) > 200:
        preview += " ..."
    print(f"      {preview}")
    if entry.get("source"):
        print(f"      Source: {entry['source']}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python vault.py <save|search|list|stats> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        if len(sys.argv) < 5:
            print('Usage: vault.py save "<topic>" <language> "<solution>" [--source <url>]')
            sys.exit(1)
        topic, language, solution = sys.argv[2], sys.argv[3], sys.argv[4]
        source = ""
        if "--source" in sys.argv:
            idx = sys.argv.index("--source")
            source = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        entry_id = save(topic, language, solution, source)
        print(f"Saved: {entry_id} ({topic} / {language})")

    elif command == "search":
        if len(sys.argv) < 3:
            print('Usage: vault.py search "<topic>" [language]')
            sys.exit(1)
        topic = sys.argv[2]
        language = sys.argv[3] if len(sys.argv) > 3 else ""
        results = search(topic, language)
        if not results:
            print(f"No vault entries for: {topic!r} {language!r}")
            print("Try: genesis resolve [topic] to fetch from Stack Overflow")
            sys.exit(0)
        print(f"Vault: {len(results)} result(s) for {topic!r}")
        for i, entry in enumerate(results, 1):
            _print_entry(entry, i)

    elif command == "list":
        entries = list_all()
        if not entries:
            print("Vault is empty. Use 'vault.py save' to add entries.")
            sys.exit(0)
        print(f"Vault: {len(entries)} entries")
        for i, entry in enumerate(entries, 1):
            _print_entry(entry, i)

    elif command == "stats":
        s = stats()
        print(f"Vault stats:")
        print(f"  Total entries: {s['total_entries']}")
        print(f"  Total uses:    {s['total_uses']}")
        print(f"  By language:   {s['by_language']}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
