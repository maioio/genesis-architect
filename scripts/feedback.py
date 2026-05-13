#!/usr/bin/env python3
"""
feedback.py - Collect feedback on Genesis Architect pitfall relevance.

Stores ratings locally in .genesis/feedback.jsonl.
Used to improve future research quality.

Usage:
  python scripts/feedback.py mark-helpful "path traversal" python
  python scripts/feedback.py mark-irrelevant "csv streaming" python
  python scripts/feedback.py stats
  python scripts/feedback.py list
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_DIR = ".genesis"
FEEDBACK_FILE = "feedback.jsonl"


def _feedback_path(project_root: Path | None = None) -> Path:
    root = project_root or Path.cwd()
    d = root / FEEDBACK_DIR
    d.mkdir(exist_ok=True)
    return d / FEEDBACK_FILE


def _load(project_root: Path | None = None) -> list[dict]:
    path = _feedback_path(project_root)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def record(topic: str, language: str, rating: str, project_root: Path | None = None) -> None:
    if rating not in ("helpful", "irrelevant"):
        raise ValueError(f"Rating must be 'helpful' or 'irrelevant', got: {rating!r}")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "language": language or "any",
        "rating": rating,
    }
    path = _feedback_path(project_root)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Recorded: {rating} - {topic!r} ({language or 'any'})")


def stats(project_root: Path | None = None) -> dict:
    entries = _load(project_root)
    by_rating: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_topic: dict[str, dict] = {}
    for e in entries:
        by_rating[e["rating"]] = by_rating.get(e["rating"], 0) + 1
        lang = e.get("language", "any")
        by_language[lang] = by_language.get(lang, 0) + 1
        topic = e["topic"]
        if topic not in by_topic:
            by_topic[topic] = {"helpful": 0, "irrelevant": 0}
        by_topic[topic][e["rating"]] += 1
    return {
        "total": len(entries),
        "by_rating": by_rating,
        "by_language": by_language,
        "by_topic": by_topic,
    }


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: feedback.py <mark-helpful|mark-irrelevant|stats|list> [topic] [language]")
        sys.exit(1)

    command = args[0]

    if command in ("mark-helpful", "mark-irrelevant"):
        if len(args) < 2:
            print(f"Usage: feedback.py {command} <topic> [language]")
            sys.exit(1)
        topic = args[1]
        language = args[2] if len(args) > 2 else ""
        rating = "helpful" if command == "mark-helpful" else "irrelevant"
        record(topic, language, rating)

    elif command == "stats":
        s = stats()
        print(f"Feedback stats:")
        print(f"  Total entries: {s['total']}")
        if s['by_rating']:
            helpful = s['by_rating'].get('helpful', 0)
            irrelevant = s['by_rating'].get('irrelevant', 0)
            print(f"  Helpful:       {helpful}")
            print(f"  Irrelevant:    {irrelevant}")
        if s['by_language']:
            print(f"  By language:   {s['by_language']}")
        if s['by_topic']:
            print(f"\nTop topics:")
            for topic, counts in sorted(s['by_topic'].items(),
                                        key=lambda x: x[1]['helpful'], reverse=True)[:10]:
                print(f"  {topic}: {counts['helpful']} helpful, {counts['irrelevant']} irrelevant")

    elif command == "list":
        entries = _load()
        if not entries:
            print("No feedback recorded yet.")
            sys.exit(0)
        print(f"{len(entries)} feedback entries:")
        for e in entries[-20:]:
            print(f"  [{e['timestamp'][:10]}] {e['rating']:12} {e['topic']!r} ({e['language']})")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
