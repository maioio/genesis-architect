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
import sys
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
    )
    return result.returncode == 0


def _git_log(project_path: Path, days: int) -> list[dict]:
    """
    Run git log with --stat for the last N days.
    Returns list of {hash, subject, files_changed: [filename]}.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        [
            "git", "log",
            f"--since={since}",
            "--format=%H|%s",
            "--name-only",
            "--no-merges",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []

    commits: list[dict] = []
    current: dict | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            if current is not None:
                commits.append(current)
                current = None
            continue
        if "|" in line and len(line.split("|", 1)[0]) == 40:
            parts = line.split("|", 1)
            current = {"hash": parts[0], "subject": parts[1] if len(parts) > 1 else "", "files": []}
        elif current is not None:
            current["files"].append(line)
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

    for commit in commits:
        is_fix = bool(FIX_PATTERNS.search(commit["subject"]))
        for f in commit["files"]:
            f = f.replace("\\", "/")
            file_commits[f] = file_commits.get(f, 0) + 1
            if is_fix:
                file_fix_commits[f] = file_fix_commits.get(f, 0) + 1

    # Build result
    result: dict[str, dict] = {}
    all_files = set(file_commits.keys())

    for rel_path in all_files:
        n_commits = file_commits.get(rel_path, 0)
        n_fix = file_fix_commits.get(rel_path, 0)
        fix_ratio = n_fix / n_commits if n_commits > 0 else 0.0
        days_since = _last_touched(root, rel_path)

        result[rel_path] = {
            "commits": n_commits,
            "fix_commits": n_fix,
            "fix_ratio": round(fix_ratio, 3),
            "last_touched_days": days_since,
            "churn_level": _classify_churn(n_commits, fix_ratio, days_since),
        }

    return result


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
            print(f"  {d['churn_level']:6s}  commits={d['commits']:3d}  "
                  f"fix_ratio={d['fix_ratio']:.2f}  {f}")

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
    args = parser.parse_args()

    churn = per_module_churn(args.project_path, days=args.days)

    if args.json:
        print(json.dumps(churn, indent=2))
    else:
        print_churn_report(churn)


if __name__ == "__main__":
    main()
