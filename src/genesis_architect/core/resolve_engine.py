"""Resolve Engine - queries Stack Overflow, caches in vault, respects TTL."""

import urllib.request
import urllib.parse
import json
import time
from typing import Any

from genesis_architect.core import vault as _vault


_SO_API = "https://api.stackexchange.com/2.3"
_STALE_WARNING = (
    "\nWarning: This solution is from the local vault and is over 6 months old. "
    "Could not verify updates due to network issues.\n"
)


def _score_answer(answer: dict) -> int:
    score = 0
    if answer.get("is_accepted"):
        score += 50
    if answer.get("score", 0) >= 10:
        score += 30
    age_days = (time.time() - answer.get("creation_date", 0)) / 86400
    if age_days < 730:  # newer than 2 years
        score += 20
    body = answer.get("body", "")
    if "<code>" in body or "```" in body:
        score += 10
    return score


def _fetch_from_so(query: str) -> dict | None:
    """Fetch best answer from Stack Overflow. Returns None on failure."""
    params = urllib.parse.urlencode({
        "order": "desc", "sort": "relevance",
        "q": query, "site": "stackoverflow",
        "filter": "withbody", "pagesize": 5,
    })
    search_url = f"{_SO_API}/search/advanced?{params}"
    try:
        with urllib.request.urlopen(search_url, timeout=10) as resp:
            questions = json.loads(resp.read()).get("items", [])
        if not questions:
            return None

        best_qid = questions[0]["question_id"]
        ans_params = urllib.parse.urlencode({
            "order": "desc", "sort": "votes", "site": "stackoverflow",
            "filter": "withbody", "pagesize": 5,
        })
        ans_url = f"{_SO_API}/questions/{best_qid}/answers?{ans_params}"
        with urllib.request.urlopen(ans_url, timeout=10) as resp:
            answers = json.loads(resp.read()).get("items", [])
        if not answers:
            return None

        best = max(answers, key=_score_answer)
        return {
            "solution": best.get("body", ""),
            "source_url": f"https://stackoverflow.com/a/{best['answer_id']}",
        }
    except Exception:
        return None


def resolve(query: str, project_root: str = ".") -> tuple[str, str, bool]:
    """
    Resolve a query. Returns (solution, source_url, is_stale_fallback).

    Flow:
    1. Check vault - if fresh, return immediately.
    2. If stale or missing, try Stack Overflow.
    3. If SO succeeds, update vault and return fresh answer.
    4. If SO fails and stale entry exists, return stale with warning.
    5. If nothing found, return empty strings.
    """
    key = query.lower().strip()
    entry = _vault.get(key, project_root)

    if entry and not _vault.is_stale(entry):
        return entry["solution"], entry["source_url"], False

    stale_entry = entry  # may be None

    fresh = _fetch_from_so(query)
    if fresh:
        _vault.put(key, fresh["solution"], fresh["source_url"], project_root)
        return fresh["solution"], fresh["source_url"], False

    if stale_entry:
        return stale_entry["solution"], stale_entry["source_url"], True

    return "", "", False


def resolve_with_output(query: str, project_root: str = ".") -> str:
    """Resolve and format output for CLI display."""
    solution, url, stale = resolve(query, project_root)
    if not solution:
        return f"No solution found for: {query}"
    out = f"Source: {url}\n\n{solution}"
    if stale:
        out = _STALE_WARNING + out
    return out
