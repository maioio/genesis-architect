#!/usr/bin/env python3
"""
git_analyzer.py - Genesis Architect PRO

Per-module git history analysis:
  - commit frequency (last N days)
  - fix/bug commit ratio
  - last touched date
  - churn level classification (HIGH / MEDIUM / LOW / STALE)
  - change coupling: file pairs that keep changing in the same commit

All operations are read-only subprocess calls to git.
No modifications to project state. The one exception is the opt-in log
cache (`cache_dir=` / `--cache-dir`), which writes only inside the directory
the caller names.

Usage:
  python scripts/git_analyzer.py [project_path]
  python scripts/git_analyzer.py [project_path] --days 90 --json
  python scripts/git_analyzer.py [project_path] --coupling [--json]
"""

import argparse
import itertools
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
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


# Bump when the shape of a _git_log() record changes, so old cache files are
# never read back as if they were current.
_LOG_FORMAT_VERSION = 2
_LOG_CACHE_KEEP = 16

_BRACE_RENAME = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def _unquote_git_path(fname: str) -> str:
    """Undo git's C-style quoting of unusual paths (core.quotePath).

    git prints a non-ASCII name as `"src/\\327\\251.py"`: octal escapes of the
    UTF-8 bytes, inside double quotes.
    """
    if len(fname) < 2 or not (fname.startswith('"') and fname.endswith('"')):
        return fname
    try:
        raw = fname[1:-1].encode("latin-1").decode("unicode_escape")
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return fname[1:-1]


def _normalize_path(fname: str) -> str:
    """Map a --numstat path to the file's current path.

    With rename detection on (git's default), numstat prints a moved file as
    `src/{old.py => new.py}` or `old.py => new.py`. Counting that literal
    string as a file splits one file's history in two and makes the file
    look new, so the post-rename path is kept.
    """
    fname = _unquote_git_path(fname).replace("\\", "/")
    if " => " not in fname:
        return fname
    if "{" in fname:
        fname = _BRACE_RENAME.sub(lambda m: m.group(2), fname)
    else:
        fname = fname.split(" => ", 1)[1]
    while "//" in fname:
        fname = fname.replace("//", "/")
    return fname.strip("/")


def _head_sha(project_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10,
    )
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def _cache_file(cache_dir: Path, head: str, since: str) -> Path:
    return cache_dir / f"gitlog-v{_LOG_FORMAT_VERSION}-{head[:16]}-{since}.json"


def _read_log_cache(path: Path) -> list[dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != _LOG_FORMAT_VERSION:
        return None
    commits = data.get("commits")
    return commits if isinstance(commits, list) else None


def _write_log_cache(cache_dir: Path, path: Path, commits: list[dict]) -> None:
    """Best effort: a cache that cannot be written is simply not used."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": _LOG_FORMAT_VERSION, "commits": commits}),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        entries = sorted(cache_dir.glob("gitlog-*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in entries[_LOG_CACHE_KEEP:]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass


def _git_log(project_path: Path, days: int,
             cache_dir: str | Path | None = None) -> list[dict]:
    """
    Run git log with --numstat for the last N days.
    Returns list of {hash, author, subject, date_iso, committed_ts,
                     files: [filename], additions: int, deletions: int}.

    Paths are normalized: renames resolve to the new path, quoted names are
    unquoted, separators are "/".

    cache_dir: opt-in. When given, the parsed log is stored there, keyed by
    HEAD sha + the --since date + the record format. A new commit changes
    HEAD, so a cached log never outlives the history it describes. Anything
    wrong with the cache falls back to a live git call.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    cache_root = Path(cache_dir) if cache_dir is not None else None
    cache_path: Path | None = None
    if cache_root is not None:
        head = _head_sha(project_path)
        if head:
            cache_path = _cache_file(cache_root, head, since)
            cached = _read_log_cache(cache_path)
            if cached is not None:
                return cached

    result = subprocess.run(
        [
            "git", "log",
            f"--since={since}",
            "--format=%H|%an|%aI|%ct|%s",
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
        # Header line: hash | author | ISO author date | committer ts | subject
        parts = line.split("|", 4)
        if (len(parts) >= 2 and len(parts[0]) in (40, 64)
                and all(c in "0123456789abcdef" for c in parts[0])):
            if current is not None:
                commits.append(current)
            try:
                committed_ts = int(parts[3]) if len(parts) > 3 else None
            except ValueError:
                committed_ts = None
            current = {
                "hash": parts[0],
                "author": parts[1] if len(parts) > 1 else "",
                "date_iso": parts[2] if len(parts) > 2 else "",
                "committed_ts": committed_ts,
                "subject": parts[4] if len(parts) > 4 else "",
                "files": [],
                "additions": 0,
                "deletions": 0,
            }
        elif current is not None:
            # numstat line: "<add>\t<del>\tfilename"  (binary shows "-")
            numstat_parts = line.split("\t", 2)
            if len(numstat_parts) == 3:
                add_str, del_str, fname = numstat_parts
                current["files"].append(_normalize_path(fname))
                try:
                    current["additions"] += int(add_str)
                    current["deletions"] += int(del_str)
                except ValueError:
                    pass  # binary file: add/del == "-"
    if current is not None:
        commits.append(current)

    if cache_root is not None and cache_path is not None:
        _write_log_cache(cache_root, cache_path, commits)
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


def per_module_churn(project_path: str | Path, days: int = 90,
                     cache_dir: str | Path | None = None) -> dict[str, dict]:
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

    last_touched_days comes from the same single `git log` call (the newest
    committer timestamp per file) instead of one extra git call per file.
    Every file in the result was touched inside the window, so its newest
    commit is inside the window too. Merge commits are excluded from the log,
    so a file whose last change was a conflict resolution reports the last
    non-merge commit instead.

    cache_dir: see _git_log(); off by default.
    """
    root = Path(project_path).resolve()

    if not _is_git_repo(root):
        return {}

    commits = _git_log(root, days, cache_dir=cache_dir)

    # Per-file counters
    file_commits: dict[str, int] = {}
    file_fix_commits: dict[str, int] = {}
    file_authors: dict[str, set[str]] = {}
    file_last_ts: dict[str, int] = {}

    for commit in commits:
        is_fix = bool(FIX_PATTERNS.search(commit["subject"]))
        author = commit.get("author", "")
        ts = commit.get("committed_ts")
        for f in commit["files"]:
            f = f.replace("\\", "/")
            file_commits[f] = file_commits.get(f, 0) + 1
            if is_fix:
                file_fix_commits[f] = file_fix_commits.get(f, 0) + 1
            if f not in file_authors:
                file_authors[f] = set()
            if author:
                file_authors[f].add(author)
            if isinstance(ts, int) and ts > file_last_ts.get(f, -1):
                file_last_ts[f] = ts

    # Build result
    result: dict[str, dict] = {}
    all_files = set(file_commits.keys())
    now_ts = int(datetime.now(UTC).timestamp())

    for rel_path in all_files:
        n_commits = file_commits.get(rel_path, 0)
        n_fix = file_fix_commits.get(rel_path, 0)
        fix_ratio = n_fix / n_commits if n_commits > 0 else 0.0
        if rel_path in file_last_ts:
            days_since = max(0, (now_ts - file_last_ts[rel_path]) // 86400)
        else:
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


@dataclass
class CoupledPair:
    """Two files that changed in the same commit more than once."""
    file_a: str
    file_b: str
    cochanges: int     # commits touching both files
    commits_a: int     # commits touching file_a
    commits_b: int     # commits touching file_b
    confidence: float  # cochanges / max(commits_a, commits_b), 0..1

    def to_dict(self) -> dict:
        return asdict(self)


def change_coupling(commits: list[dict], top_n: int = 50, min_cochanges: int = 2,
                    max_files_per_commit: int = 30) -> list[CoupledPair]:
    """
    Temporal (change) coupling: file pairs that keep changing together.

    An import graph cannot see this. Two files with no import between them
    that still change in the same commit share a hidden contract (a schema
    and its serializer, a handler and its test fixture).

    commits: output from _git_log().
    confidence = cochanges / max(commits_a, commits_b). With the larger count
        as denominator a pair only scores 1.0 when neither file ever changes
        without the other, so a busy file does not look tightly coupled to
        every file it happened to share one commit with.
    min_cochanges: pairs seen together fewer times are noise and are dropped.
    max_files_per_commit: bulk commits (formatting, renames, vendoring) pair
        everything with everything. A commit touching more files than this is
        left out of the analysis entirely, including the per-file counts.

    Returns at most top_n pairs, strongest first: confidence, then cochanges,
    then path order, so the result is deterministic.
    """
    file_counts: dict[str, int] = {}
    pair_counts: dict[tuple[str, str], int] = {}

    for commit in commits:
        files = sorted({f.replace("\\", "/") for f in commit.get("files", []) if f})
        if not files or len(files) > max_files_per_commit:
            continue
        for f in files:
            file_counts[f] = file_counts.get(f, 0) + 1
        for pair in itertools.combinations(files, 2):
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    pairs: list[CoupledPair] = []
    for (a, b), together in pair_counts.items():
        if together < min_cochanges:
            continue
        ca, cb = file_counts[a], file_counts[b]
        pairs.append(CoupledPair(
            file_a=a, file_b=b, cochanges=together,
            commits_a=ca, commits_b=cb,
            confidence=round(together / max(ca, cb), 3),
        ))

    pairs.sort(key=lambda p: (-p.confidence, -p.cochanges, p.file_a, p.file_b))
    return pairs[:max(top_n, 0)]


def print_coupling_report(pairs: list[CoupledPair]) -> None:
    if not pairs:
        print("No change coupling found (no file pair changed together twice).")
        return
    print(f"\nChange coupling  (top {len(pairs)} pairs)")
    for p in pairs:
        print(f"  {p.confidence:4.2f}  together={p.cochanges:3d}  "
              f"({p.commits_a}/{p.commits_b})  {p.file_a}  <->  {p.file_b}")


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
    parser.add_argument("--coupling", action="store_true",
                        help="Print file pairs that change together (top 50)")
    parser.add_argument("--cache-dir", default=None,
                        help="Opt-in: cache the parsed git log in this directory")
    args = parser.parse_args()

    if args.coupling:
        root = Path(args.project_path).resolve()
        if not _is_git_repo(root):
            print("Not a git repository.")
            return
        pairs = change_coupling(_git_log(root, args.days, cache_dir=args.cache_dir))
        if args.json:
            print(json.dumps([p.to_dict() for p in pairs], indent=2))
        else:
            print_coupling_report(pairs)
        return

    churn = per_module_churn(args.project_path, days=args.days, cache_dir=args.cache_dir)

    if args.json:
        print(json.dumps(churn, indent=2))
    elif args.timeline:
        root = Path(args.project_path).resolve()
        if _is_git_repo(root):
            commits = _git_log(root, args.days, cache_dir=args.cache_dir)
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
