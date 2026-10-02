#!/usr/bin/env python3
"""
score_timeline.py - Genesis Architect PRO

Timeline and ASCII sparkline over the architecture-score history.

Every run of the GDE architecture-scorer engine appends one record to
.genesis/score_history.jsonl (see architecture_scorer.append_score_history).
This module reads that file - it never writes it - and shows how one metric
moved: a one-character-per-record sparkline, first / last / change / low /
high, and the date range covered.

The sparkline is pure ASCII (ramp "_.-=+*#@", low to high) so it survives any
console encoding. git_analyzer.render_sparkline draws Unicode blocks and plots
weekly churn, not scores, so it is not reused here.

Scale:
  auto   - the ramp spans the lowest to the highest value shown, so small
           movements are visible (a flat series draws the middle character)
  fixed  - the ramp spans 0-100, the range every score dimension lives in,
           so the height of a character is comparable across projects

Nothing is dropped silently. load_score_history skips unreadable lines without
a word; this module counts them, and counts records that lack a numeric value
for the chosen metric, and reports both as warnings. Records are shown in file
order, which is write order because the file is only ever appended to.

Exit codes (CLI): 0 when a timeline was drawn, 1 when there was nothing to
draw (no history, or no record carries the metric), 2 on a usage or read error.

Public API
----------
  read_history(project_path) -> (records, malformed_line_count)
  metric_value(record, metric) -> float | None
  render_ascii_sparkline(values, lo=None, hi=None, ramp=RAMP) -> str
  build_timeline(records, metric="total", last=DEFAULT_LAST, scale="auto",
                 lines_malformed=0) -> Timeline
  score_timeline(project_path, metric="total", last=DEFAULT_LAST,
                 scale="auto") -> Timeline
  format_report(timeline) -> str

Usage:
  python -m genesis_architect_pro.score_timeline .
  python -m genesis_architect_pro.score_timeline . --metric coupling --last 20
  python -m genesis_architect_pro.score_timeline . --last 0 --scale fixed --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METRICS = ("total", "modularity", "coupling", "cohesion", "layering")
SCALES = ("auto", "fixed")
RAMP = "_.-=+*#@"
FIXED_RANGE = (0.0, 100.0)
DEFAULT_LAST = 60
HISTORY_RELPATH = ".genesis/score_history.jsonl"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Point:
    """One plotted record: its position in the history and its value."""
    ordinal: int          # 1-based position among the valid records in the file
    timestamp: str        # as recorded; may be empty when the record had none
    value: float

    def to_dict(self) -> dict:
        return {"ordinal": self.ordinal, "timestamp": self.timestamp, "value": self.value}


@dataclass
class Timeline:
    metric: str
    scale: str
    points: list[Point] = field(default_factory=list)
    available: int = 0          # records carrying the metric, before --last
    records_total: int = 0      # valid JSON-object records in the file
    records_skipped: int = 0    # valid records with no usable value for the metric
    lines_malformed: int = 0    # non-empty lines that are not a JSON object
    sparkline: str = ""
    scale_low: float | None = None
    scale_high: float | None = None
    first: float | None = None
    last: float | None = None
    change: float | None = None  # None with fewer than two points: no trend yet
    low: float | None = None
    high: float | None = None
    since: str | None = None     # YYYY-MM-DD of the first plotted point
    until: str | None = None     # YYYY-MM-DD of the last plotted point
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "scale": self.scale,
            "points": [p.to_dict() for p in self.points],
            "available": self.available,
            "records_total": self.records_total,
            "records_skipped": self.records_skipped,
            "lines_malformed": self.lines_malformed,
            "sparkline": self.sparkline,
            "scale_low": self.scale_low,
            "scale_high": self.scale_high,
            "first": self.first,
            "last": self.last,
            "change": self.change,
            "low": self.low,
            "high": self.high,
            "since": self.since,
            "until": self.until,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_history(project_path: str | Path) -> tuple[list[dict], int]:
    """
    Read .genesis/score_history.jsonl without modifying anything.

    Returns (records, malformed): records are the lines that decode to a JSON
    object, in file order; malformed counts the non-empty lines that do not
    (bad UTF-8, bad JSON, or JSON that is not an object). A missing file is
    ([], 0). Raises ValueError when project_path is not a directory or the
    file cannot be read.
    """
    root = Path(project_path)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {project_path}")
    path = root / HISTORY_RELPATH
    if not path.is_file():
        return [], 0
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read {HISTORY_RELPATH}: {exc}") from exc

    records: list[dict] = []
    malformed = 0
    for raw_line in raw.splitlines():
        try:
            line = raw_line.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            malformed += 1
            continue
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            malformed += 1
    return records, malformed


def metric_value(record: dict, metric: str) -> float | None:
    """The record's value for metric as a float, or None when it is absent,
    not a number (booleans included), or not finite."""
    value = record.get(metric)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _date(timestamp: str) -> str | None:
    try:
        return datetime.fromisoformat(timestamp).date().isoformat()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_ascii_sparkline(values: list[float], lo: float | None = None,
                           hi: float | None = None, ramp: str = RAMP) -> str:
    """
    One ramp character per value. lo/hi default to the min/max of values;
    values outside [lo, hi] are clamped. When lo == hi every value draws the
    middle character, so a flat series reads as flat, not as a floor.
    """
    if len(ramp) < 2:
        raise ValueError("ramp needs at least two characters")
    if not values:
        return ""
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    if hi < lo:
        raise ValueError(f"scale low {lo} is above scale high {hi}")
    top = len(ramp) - 1
    if hi == lo:
        return ramp[top // 2] * len(values)
    out = []
    for v in values:
        frac = max(0.0, min(1.0, (v - lo) / (hi - lo)))
        out.append(ramp[int(frac * top + 0.5)])  # half-up, not banker's rounding
    return "".join(out)


def _num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value, 1):g}"


def _signed(value: float | None) -> str:
    if value is None:
        return "n/a"
    value = round(value, 1)
    return "0" if value == 0 else f"{value:+g}"


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def build_timeline(records: list[dict], metric: str = "total",
                   last: int | None = DEFAULT_LAST, scale: str = "auto",
                   lines_malformed: int = 0) -> Timeline:
    """
    Build the timeline for one metric from history records (file order).
    last keeps only the most recent N usable records; None keeps them all.
    """
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r}; choose from {', '.join(METRICS)}")
    if scale not in SCALES:
        raise ValueError(f"Unknown scale {scale!r}; choose from {', '.join(SCALES)}")
    if last is not None and (isinstance(last, bool) or not isinstance(last, int) or last < 1):
        raise ValueError(f"last must be a positive integer or None, got {last!r}")

    t = Timeline(metric=metric, scale=scale, records_total=len(records),
                 lines_malformed=lines_malformed)
    usable: list[Point] = []
    for ordinal, record in enumerate(records, start=1):
        value = metric_value(record, metric)
        if value is None:
            t.records_skipped += 1
            continue
        ts = record.get("timestamp")
        usable.append(Point(ordinal, ts if isinstance(ts, str) else "", value))

    t.available = len(usable)
    t.points = usable if last is None else usable[-last:]

    if lines_malformed:
        t.warnings.append(
            f"{lines_malformed} line(s) in {HISTORY_RELPATH} are not JSON objects "
            f"and were skipped."
        )
    if t.records_skipped:
        t.warnings.append(
            f"{t.records_skipped} record(s) have no numeric '{metric}' value "
            f"and were skipped."
        )
    if not t.points:
        return t

    values = [p.value for p in t.points]
    if scale == "fixed":
        t.scale_low, t.scale_high = FIXED_RANGE
    else:
        t.scale_low, t.scale_high = min(values), max(values)
    t.sparkline = render_ascii_sparkline(values, t.scale_low, t.scale_high)
    t.first, t.last = values[0], values[-1]
    t.low, t.high = min(values), max(values)
    t.since = _date(t.points[0].timestamp)
    t.until = _date(t.points[-1].timestamp)
    if len(values) >= 2:
        t.change = round(values[-1] - values[0], 1)
    else:
        t.warnings.append(
            f"Only one record carries '{metric}': there is no trend to show yet."
        )
    return t


def score_timeline(project_path: str | Path, metric: str = "total",
                   last: int | None = DEFAULT_LAST, scale: str = "auto") -> Timeline:
    """Read the project's score history and build the timeline for metric."""
    records, malformed = read_history(project_path)
    t = build_timeline(records, metric=metric, last=last, scale=scale,
                       lines_malformed=malformed)
    if not records and not malformed:
        exists = (Path(project_path) / HISTORY_RELPATH).is_file()
        state = "is empty" if exists else "does not exist"
        t.warnings.insert(0,
            f"No score history yet: {HISTORY_RELPATH} {state}. History accumulates "
            f"each time the GDE architecture-scorer engine runs on this project."
        )
    return t


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def format_report(t: Timeline) -> str:
    if not t.points:
        lines = [f"Score timeline: {t.metric}  (no records to plot)"]
    else:
        span = f"{t.since or '?'} -> {t.until or '?'}"
        lines = [
            f"Score timeline: {t.metric}  "
            f"({len(t.points)} of {t.available} records, {span})",
            f"  {t.sparkline}",
            f"  scale: '{RAMP[0]}' = {_num(t.scale_low)} ... "
            f"'{RAMP[-1]}' = {_num(t.scale_high)} ({t.scale})",
            f"  first {_num(t.first)}  last {_num(t.last)}  "
            f"change {_signed(t.change)}  low {_num(t.low)}  high {_num(t.high)}",
        ]
    lines.extend(f"  WARNING: {w}" for w in t.warnings)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Score Timeline (read-only)"
    )
    parser.add_argument("path", nargs="?", default=".", help="project root")
    parser.add_argument("--metric", choices=METRICS, default="total")
    parser.add_argument("--last", type=int, default=DEFAULT_LAST,
                        help=f"most recent N records (default {DEFAULT_LAST}); 0 shows all")
    parser.add_argument("--scale", choices=SCALES, default="auto",
                        help="auto: span the values shown; fixed: span 0-100")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.last < 0:
        print(f"Error: --last must be 0 or more, got {args.last}", file=sys.stderr)
        sys.exit(2)
    try:
        t = score_timeline(args.path, metric=args.metric,
                           last=args.last or None, scale=args.scale)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(t.to_dict(), indent=2))
    else:
        print(format_report(t))
    sys.exit(0 if t.points else 1)


if __name__ == "__main__":
    main()
