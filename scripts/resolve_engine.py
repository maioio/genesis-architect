#!/usr/bin/env python3
"""
resolve_engine.py - Genesis Architect Smart Resolution Engine.

Fetches community-verified solutions from Stack Overflow for detected issues.
No API key required for basic usage (300 requests/day unauthenticated).
Set STACKOVERFLOW_KEY env var to raise the limit to 10,000/day.

Usage:
  python scripts/resolve_engine.py "path traversal python"
  python scripts/resolve_engine.py "csv streaming memory python" --limit 5
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.stackexchange.com/2.3"
RECENCY_CUTOFF_YEARS = 2


@dataclass
class Answer:
    answer_id: int
    score: int
    is_accepted: bool
    body_markdown: str
    link: str
    creation_date: int

    @property
    def is_recent(self) -> bool:
        age_years = (datetime.now(timezone.utc).timestamp() - self.creation_date) / (365.25 * 86400)
        return age_years <= RECENCY_CUTOFF_YEARS


@dataclass
class Question:
    question_id: int
    title: str
    score: int
    answer_count: int
    link: str
    tags: list[str]
    answers: list[Answer]

    @property
    def best_answer(self) -> Answer | None:
        accepted = [a for a in self.answers if a.is_accepted]
        if accepted:
            return accepted[0]
        high_score = sorted(self.answers, key=lambda a: a.score, reverse=True)
        return high_score[0] if high_score else None


def _api_get(path: str, params: dict) -> dict | None:
    key = os.environ.get("STACKOVERFLOW_KEY", "")
    if key:
        params["key"] = key
    params["site"] = "stackoverflow"
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "genesis-architect-resolve/1.0")
    req.add_header("Accept-Encoding", "identity")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print(f"  API quota exceeded. Set STACKOVERFLOW_KEY for higher limits.")
        return None
    except Exception as e:
        print(f"  Network error: {e}")
        return None


def search_questions(query: str, limit: int = 3) -> list[Question]:
    data = _api_get("/search/advanced", {
        "q": query,
        "answers": 1,
        "sort": "votes",
        "order": "desc",
        "pagesize": limit * 2,
        "filter": "withbody",
    })
    if not data:
        return []

    questions = []
    for item in data.get("items", [])[:limit * 2]:
        if item.get("answer_count", 0) == 0:
            continue
        q = Question(
            question_id=item["question_id"],
            title=item["title"],
            score=item["score"],
            answer_count=item["answer_count"],
            link=item["link"],
            tags=item.get("tags", []),
            answers=[],
        )
        questions.append(q)
        if len(questions) >= limit:
            break
    return questions


def fetch_answers(question_ids: list[int]) -> dict[int, list[Answer]]:
    if not question_ids:
        return {}
    ids = ";".join(str(i) for i in question_ids)
    data = _api_get(f"/questions/{ids}/answers", {
        "sort": "votes",
        "order": "desc",
        "filter": "withbody",
        "pagesize": 5,
    })
    if not data:
        return {}
    result: dict[int, list[Answer]] = {}
    for item in data.get("items", []):
        qid = item["question_id"]
        a = Answer(
            answer_id=item["answer_id"],
            score=item["score"],
            is_accepted=item.get("is_accepted", False),
            body_markdown=item.get("body", ""),
            link=f"https://stackoverflow.com/a/{item['answer_id']}",
            creation_date=item.get("creation_date", 0),
        )
        result.setdefault(qid, []).append(a)
    return result


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(r"<pre><code>(.*?)</code></pre>", r"\n```\n\1\n```", text, flags=re.DOTALL)
    text = re.sub(r"<a [^>]*href=[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _truncate(text: str, max_chars: int = 400) -> str:
    text = _strip_html(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " ..."


def _badge(label: str, value: str) -> str:
    return f"[{label}: {value}]"


def _check_vault(query: str) -> list[dict]:
    """Check local vault before hitting external APIs."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from vault import search as vault_search
        parts = query.split()
        language = parts[-1] if parts[-1] in ("python", "typescript", "javascript", "go", "rust") else ""
        topic = query if not language else " ".join(parts[:-1])
        return vault_search(topic, language, project_root=Path.cwd())
    except Exception:
        return []


def resolve(query: str, limit: int = 3) -> None:
    print(f"\nSmart Resolution Engine")
    print(f"Query: {query!r}")

    vault_hits = _check_vault(query)
    if vault_hits:
        print(f"Source: Knowledge Vault ({len(vault_hits)} cached result(s))\n")
        for i, entry in enumerate(vault_hits[:limit], 1):
            print(f"{'=' * 60}")
            print(f"Vault Result {i}: {entry['topic']} ({entry['language']})")
            preview = entry["solution"][:400]
            if len(entry["solution"]) > 400:
                preview += " ..."
            print(f"\n  {preview}")
            if entry.get("source"):
                print(f"\n  Source: {entry['source']}")
        print(f"\n{'=' * 60}")
        print("Vault hit - no external API call needed.")
        print("Use 'python scripts/vault.py save' to add more entries.")
        return

    print(f"Source: Stack Overflow community answers\n")

    questions = search_questions(query, limit)
    if not questions:
        print("No results found. Try a broader query.")
        return

    answer_map = fetch_answers([q.question_id for q in questions])
    for q in questions:
        q.answers = answer_map.get(q.question_id, [])

    for i, q in enumerate(questions, 1):
        print(f"{'=' * 60}")
        print(f"Result {i}: {q.title}")
        print(f"  Score: {q.score}  |  Answers: {q.answer_count}  |  Tags: {', '.join(q.tags[:4])}")
        print(f"  Question: {q.link}")

        best = q.best_answer
        if best:
            tag = "ACCEPTED" if best.is_accepted else "TOP ANSWER"
            recency = "recent" if best.is_recent else "classic"
            print(f"\n  {_badge(tag, f'score {best.score}')}  {_badge('type', recency)}")
            print(f"\n  {_truncate(best.body_markdown)}")
            print(f"\n  Source: {best.link}")
        else:
            print("  No answers available yet.")
        print()

    print(f"{'=' * 60}")
    print("IMPORTANT: Always review community solutions before applying.")
    print("Genesis Architect never patches your code without your confirmation.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python resolve_engine.py <query> [--limit N]")
        sys.exit(1)

    args = sys.argv[1:]
    limit = 3
    if "--limit" in args:
        idx = args.index("--limit")
        try:
            limit = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]
        except (IndexError, ValueError):
            pass

    query = " ".join(args)
    if not query.strip():
        print("Error: query cannot be empty")
        sys.exit(1)

    resolve(query, limit=limit)


if __name__ == "__main__":
    main()
