#!/usr/bin/env python3
"""
git_analyzer.py - Genesis Architect PRO

Per-module git history analysis:
  - commit frequency (last N days)
  - fix/bug commit ratio
  - last touched date
  - churn level classification (HIGH / MEDIUM / LOW / STALE)

All operations are read-only subprocess calls to git.
No modifications to project state.

Usage:
  python scripts/git_analyzer.py [project_path]
  python scripts/git_analyzer.py [project_path] --days 90 --json
"""

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Commit message patterns that indicate a fix / bug
FIX_PATTERNS = re.compile(
    r"\b(fix|bug|patch|hotfix|repair|regression|revert|crash|error|fail|broken|issue)\b",
    re.IGNORECASE,
)

CHURN_THRESHOLDS = {
    "HIGH":   {"commits": 20, "fix_ratio": 0.40},
    "MEDIUM": {"commits": 8,  "fix_ratio": 0.25},
    "LOW":    {"commits": 3,  "fix_ratio": 0.0},
    "STALE":  {"max_days_since_touch": 90},  # no commit in 90 days
}


def _is_git_repo(project_path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(project_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


@dataclass
class WeeklySnapshot:
    """Per-week project activity summary."""
    week_start: str       # ISO date of Monday (YYYY-MM-DD)
    commits: int = 0
    churn_lines: int = 0  # additions + deletions from --numstat
    active_files: int = 0


def _to_monday(dt: datetime) -> str:
    """Return the ISO date string of the Monday for the week containing dt."""
    monday = dt.date() - timedelta(days=dt.weekday())
    return monday.isoformat()


def _git_log(project_path: Path, days: int) -> list[dict]:
    """
    Run git log with --numstat for the last N days.
    Returns list of {hash, author, subject, date_iso, files: [filename],
                     additions: int, deletions: int}.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        [
            "git", "log",
            f"--since={since}",
            "--format=%H|%an|%aI|%s",
            "--numstat",
            "--no-merges",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        return []

    commits: list[dict] = []
    current: dict | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            # git separates the header from its --numstat block with a blank
            # line; keep `current` open so those numstat lines are attributed.
            continue
        # Header line: 40-char hash | author | ISO date | subject
        parts = line.split("|", 3)
        if len(parts) >= 2 and len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
            if current is not None:
                commits.append(current)
            current = {
                "hash": parts[0],
                "author": parts[1] if len(parts) > 1 else "",
                "date_iso": parts[2] if len(parts) > 2 else "",
                "subject": parts[3] if len(parts) > 3 else "",
                "files": [],
                "additions": 0,
                "deletions": 0,
            }
        elif current is not None:
            # numstat line: "<add>\t<del>\tfilename"  (binary shows "-")
            numstat_parts = line.split("\t", 2)
            if len(numstat_parts) == 3:
                add_str, del_str, fname = numstat_parts
                current["files"].append(fname)
                try:
                    current["additions"] += int(add_str)
                    current["deletions"] += int(del_str)
                except ValueError:
                    pass  # binary file: add/del == "-"
    if current is not None:
        commits.append(current)
    return commits


def _last_touched(project_path: Path, rel_path: str) -> int | None:
    """Days since last commit touching this file. Returns None if not in git."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", rel_path],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        ts = int(result.stdout.strip())
        now_ts = int(datetime.now(UTC).timestamp())
        return (now_ts - ts) // 86400
    except ValueError:
        return None


def _classify_churn(commits: int, fix_ratio: float, days_since_touch: int | None) -> str:
    if days_since_touch is not None and days_since_touch > CHURN_THRESHOLDS["STALE"]["max_days_since_touch"]:
        return "STALE"
    if commits >= CHURN_THRESHOLDS["HIGH"]["commits"] or fix_ratio >= CHURN_THRESHOLDS["HIGH"]["fix_ratio"]:
        return "HIGH"
    if commits >= CHURN_THRESHOLDS["MEDIUM"]["commits"] or fix_ratio >= CHURN_THRESHOLDS["MEDIUM"]["fix_ratio"]:
        return "MEDIUM"
    if commits > 0:
        return "LOW"
    return "STALE"


def per_module_churn(project_path: str | Path, days: int = 90) -> dict[str, dict]:
    """
    Returns per-module statistics:
    {
      "src/app.py": {
        "commits": 47,
        "fix_commits": 23,
        "fix_ratio": 0.49,
        "last_touched_days": 3,
        "churn_level": "HIGH"
      }, ...
    }
    """
    root = Path(project_path).resolve()

    if not _is_git_repo(root):
        return {}

    commits = _git_log(root, days)

    # Per-file counters
    file_commits: dict[str, int] = {}
    file_fix_commits: dict[str, int] = {}
    file_authors: dict[str, set[str]] = {}

    for commit in commits:
        is_fix = bool(FIX_PATTERNS.search(commit["subject"]))
        author = commit.get("author", "")
        for f in commit["files"]:
            f = f.replace("\\", "/")
            file_commits[f] = file_commits.get(f, 0) + 1
            if is_fix:
                file_fix_commits[f] = file_fix_commits.get(f, 0) + 1
            if f not in file_authors:
                file_authors[f] = set()
            if author:
                file_authors[f].add(author)

    # Build result
    result: dict[str, dict] = {}
    all_files = set(file_commits.keys())

    for rel_path in all_files:
        n_commits = file_commits.get(rel_path, 0)
        n_fix = file_fix_commits.get(rel_path, 0)
        fix_ratio = n_fix / n_commits if n_commits > 0 else 0.0
        days_since = _last_touched(root, rel_path)
        authors = sorted(file_authors.get(rel_path, set()))

        result[rel_path] = {
            "commits": n_commits,
            "fix_commits": n_fix,
            "fix_ratio": round(fix_ratio, 3),
            "last_touched_days": days_since,
            "churn_level": _classify_churn(n_commits, fix_ratio, days_since),
            "authors": authors,
            "bus_factor": len(authors),
        }

    return result


def build_timeline(commits: list[dict], period_weeks: int = 12) -> list[WeeklySnapshot]:
    """
    Build a week-by-week activity timeline.

    Fills every week in the period with zero entries so there are no gaps.
    Weeks are sorted ascending by week_start.

    commits: output from _git_log()
    period_weeks: number of most-recent weeks to include
    """
    now = datetime.now(UTC)
    # Generate all weeks in the period (Monday dates), most recent last
    weeks: list[str] = []
    for i in range(period_weeks - 1, -1, -1):
        week_dt = now - timedelta(weeks=i)
        weeks.append(_to_monday(week_dt))
    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered_weeks: list[str] = []
    for w in weeks:
        if w not in seen:
            seen.add(w)
            ordered_weeks.append(w)

    snap: dict[str, WeeklySnapshot] = {w: WeeklySnapshot(week_start=w) for w in ordered_weeks}

    for commit in commits:
        date_iso = commit.get("date_iso", "")
        if not date_iso:
            continue
        try:
            # ISO 8601 with timezone: "2026-06-01T14:32:00+03:00"
            commit_dt = datetime.fromisoformat(date_iso)
        except ValueError:
            continue
        week_key = _to_monday(commit_dt)
        if week_key not in snap:
            continue  # outside the requested window
        s = snap[week_key]
        s.commits += 1
        s.churn_lines += commit.get("additions", 0) + commit.get("deletions", 0)
        s.active_files += len(commit.get("files", []))

    return [snap[w] for w in ordered_weeks]


def render_sparkline(snapshots: list[WeeklySnapshot], metric: str = "commits",
                     width: int = 20) -> str:
    """
    Render an ASCII sparkline for the given metric over the snapshot list.

    metric: "commits" | "churn_lines" | "active_files"
    width: number of characters in the output (one per time bucket)
    Returns a single-line string using Unicode block elements.
    """
    _BLOCKS = " ▁▂▃▄▅▆▇█"

    if not snapshots:
        return " " * width

    values = [getattr(s, metric, 0) for s in snapshots]

    # Resample to `width` buckets
    n = len(values)
    if n == width:
        buckets = values
    elif n < width:
        # Stretch: repeat each value proportionally
        buckets = []
        for i in range(width):
            src_idx = int(i * n / width)
            buckets.append(values[src_idx])
    else:
        # Compress: average groups
        buckets = []
        for i in range(width):
            start = int(i * n / width)
            end = int((i + 1) * n / width)
            group = values[start:end] if start < end else [values[start]]
            buckets.append(sum(group) / len(group))

    max_val = max(buckets) if buckets else 0
    chars = []
    for v in buckets:
        if max_val == 0:
            chars.append(_BLOCKS[0])
        else:
            idx = int(round(v / max_val * (len(_BLOCKS) - 1)))
            chars.append(_BLOCKS[idx])
    return "".join(chars)


def print_churn_report(churn: dict[str, dict]) -> None:
    if not churn:
        print("No git history found or project is not a git repository.")
        return

    high = [(f, d) for f, d in churn.items() if d["churn_level"] == "HIGH"]
    stale = [(f, d) for f, d in churn.items() if d["churn_level"] == "STALE"]

    print(f"\nGit Churn Report  ({len(churn)} files analysed)")
    print(f"  HIGH churn:  {len(high)}")
    print(f"  STALE:       {len(stale)}")

    if high:
        print("\nHigh-churn files (most fragile):")
        for f, d in sorted(high, key=lambda x: -x[1]["fix_ratio"])[:10]:
            bus = d.get("bus_factor", len(d.get("authors", [])))
            print(f"  {d['churn_level']:6s}  commits={d['commits']:3d}  "
                  f"fix_ratio={d['fix_ratio']:.2f}  bus={bus}  {f}")

    if stale:
        print(f"\nStale files (not touched in 90+ days): {len(stale)} files")
        for f, d in stale[:5]:
            days = d.get("last_touched_days")
            days_str = f"{days}d ago" if days is not None else "unknown"
            print(f"  {f}  (last touched: {days_str})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Git History Analyzer"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeline", action="store_true",
                        help="Print weekly commit timeline with sparkline")
    args = parser.parse_args()

    churn = per_module_churn(args.project_path, days=args.days)

    if args.json:
        print(json.dumps(churn, indent=2))
    elif args.timeline:
        root = Path(args.project_path).resolve()
        if _is_git_repo(root):
            commits = _git_log(root, args.days)
            timeline = build_timeline(commits, period_weeks=min(args.days // 7, 12))
            sparkline = render_sparkline(timeline)
            print(f"\nWeekly commit timeline (last {args.days} days):")
            print(f"  {sparkline}")
            for snap in timeline[-8:]:
                print(f"  {snap.week_start}  commits={snap.commits:3d}  "
                      f"churn={snap.churn_lines:5d}  files={snap.active_files:3d}")
        else:
            print("Not a git repository.")
    else:
        print_churn_report(churn)


if __name__ == "__main__":
    main()
