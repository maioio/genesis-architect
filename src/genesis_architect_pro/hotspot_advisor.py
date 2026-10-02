#!/usr/bin/env python3
"""
hotspot_advisor.py - Genesis Architect PRO

Prescribes one refactoring action per hotspot, with the evidence behind it and
an estimated score delta whose source is named.

A hotspot is a file that changed at least `min_commits` times inside the
window AND sits at a coupling point:
  - production fan-in above the hub-file threshold (HUB_FILE_FAN_IN), or
  - fan-out above the god-class threshold (GOD_CLASS_FAN_OUT), or
  - a change-coupling partner (a file it keeps changing together with) at or
    above `min_confidence`.
Churn without coupling is not a hotspot: a file that changes often but that
nothing depends on is cheap to change. Fan-in counts production importers
only, exactly as the hub-file detector does.

The action is chosen by fixed rules, first match wins:
  hub         fan-in over the threshold, fan-out > 0  -> extract a stable interface
  vocabulary  fan-in over the threshold, fan-out == 0 -> keep it stable, do not split
  god         fan-out over the threshold              -> split it by responsibility
  coupled     a change-coupling partner               -> move the shared contract into one module
A single author for every change adds a knowledge-concentration note; it does
not change the action.

Score delta, in order of preference:
  1. a step of a supplied refactoring plan whose operations name this file
     (its score_impact; the basis names the step id and rule)
  2. the planner's own scoring rule for the action (hub-splitter,
     god-class-splitter), evaluated by the planner code itself
  3. otherwise None, reported as "not derivable": no number is invented.

Tests are neither hotspots nor coupling partners: a test changing with the
code it tests is coverage, not a hidden contract.

Git reports paths from the repository top; the import graph reports them from
the project root. When the project is a subdirectory of its repository, git
paths are rebased onto the project and files outside it are dropped.

Nothing is written except what the analyses write themselves: the import graph
cache (.genesis/import_graph.json) and, with --cache-dir, the git log cache.
Author names never appear in the output, only their count.

Public API
----------
  file_stats(commits) -> dict[str, FileStats]
  find_hotspots(stats, modules, pairs, days, ...) -> list[HotspotAdvice]
  extraction_candidate(root, rel_path) -> Candidate | None
  advise(project_path, days=90, plan=None, modules=None, ...) -> HotspotReport
  format_report(report) -> str

Usage:
  python -m genesis_architect_pro.hotspot_advisor [PATH]
  python -m genesis_architect_pro.hotspot_advisor [PATH] --days 56 --plan plan.json --json
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import NoReturn

from genesis_architect_pro.antipattern_detector import (
    GOD_CLASS_FAN_OUT,
    HUB_FILE_FAN_IN,
    AntiPattern,
)
from genesis_architect_pro.git_analyzer import (
    CHURN_THRESHOLDS,
    CoupledPair,
    _git_log,
    _is_git_repo,
    change_coupling,
)
from genesis_architect_pro.refactoring_planner import (
    RefactoringPlan,
    RefactorStep,
    _graph_modules,
    _rule_god_class_splitter,
    _rule_hub_splitter,
    _suggest_split_path,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HUB = "hub"
VOCABULARY = "vocabulary"
GOD = "god"
COUPLED = "coupled"
ACTIONS = (HUB, VOCABULARY, GOD, COUPLED)

# The planner rule whose step prescribes each action.
_ACTION_RULE = {HUB: "hub-splitter", GOD: "god-class-splitter"}

DEFAULT_DAYS = 90
DEFAULT_TOP = 10
MIN_COMMITS = CHURN_THRESHOLDS["MEDIUM"]["commits"]
MIN_CONFIDENCE = 0.5
MIN_COCHANGES = 3            # same noise floor as the rules engine
_PLACEHOLDER_PREFIX = "["    # "[all importers]" and similar are not paths


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FileStats:
    """Churn for one file inside the window."""
    commits: int
    authors: int


@dataclass
class CoChange:
    """A file the hotspot keeps changing together with."""
    path: str
    cochanges: int
    confidence: float
    imports_between: bool | None   # None when there is no import graph


@dataclass
class Candidate:
    """The largest top-level class of a Python file: the first thing to extract."""
    name: str
    line: int
    lines: int
    file_lines: int


@dataclass
class HotspotAdvice:
    path: str
    days: int
    commits: int
    authors: int
    fan_in: int | None             # production importers; None without a graph
    fan_out: int | None
    action: str                    # hub | vocabulary | god | coupled
    recommendation: str
    partners: list[CoChange] = field(default_factory=list)
    candidate: Candidate | None = None
    score_delta: int | None = None
    delta_basis: str = ""
    notes: list[str] = field(default_factory=list)

    def evidence(self) -> str:
        window = _window(self.days)
        if self.fan_in is None:
            return (f"This file changed {_count(self.commits, 'time')} in {window} and has "
                    f"{_count(self.authors, 'author')}; its fan-in was not measured "
                    "(no import graph).")
        return (f"This file changed {_count(self.commits, 'time')} in {window}, has "
                f"{_count(self.authors, 'author')}, and a fan-in of {self.fan_in}.")

    def delta_text(self) -> str:
        if self.score_delta is None:
            return f"Estimated score delta: {self.delta_basis}."
        return f"Estimated score delta: {self.score_delta:+d} pts ({self.delta_basis})."

    def message(self) -> str:
        return " ".join([self.evidence(), self.recommendation, self.delta_text()])

    def to_dict(self) -> dict:
        data = asdict(self)
        data["message"] = self.message()
        return data


@dataclass
class HotspotReport:
    days: int
    hotspots: list[HotspotAdvice] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_examined: int = 0

    def to_dict(self) -> dict:
        return {
            "days": self.days,
            "files_examined": self.files_examined,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _window(days: int) -> str:
    """'8 weeks' when the window is whole weeks, else '90 days'."""
    if days % 7 == 0:
        return _count(days // 7, "week")
    return _count(days, "day")


def _is_test_path(path: str) -> bool:
    """Same test-module rule as the hub-file detector."""
    p = path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return (
        p.startswith(("tests/", "test/"))
        or "/tests/" in p
        or "/test/" in p
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _production_fan_in(entry: dict) -> int:
    """Production importers, as the hub-file detector counts them."""
    imported_by = entry.get("imported_by") or []
    if imported_by:
        return sum(1 for m in imported_by if not _is_test_path(m))
    value = entry.get("fan_in", 0)
    return value if isinstance(value, int) else 0


def _fan_out(entry: dict) -> int:
    value = entry.get("fan_out", 0)
    return value if isinstance(value, int) else 0


def _imports_between(modules: dict, a: str, b: str) -> bool | None:
    if not modules:
        return None
    ea, eb = modules.get(a) or {}, modules.get(b) or {}
    return b in (ea.get("imports") or []) or a in (eb.get("imports") or [])


def _split_path(path: str, suffix: str) -> str:
    """The planner's split-off path, without a leading './' for top-level files."""
    suggested = _suggest_split_path(path, suffix)
    return suggested[2:] if suggested.startswith("./") else suggested


def _validate(days: int, min_commits: int, min_confidence: float,
              top_n: int | None) -> None:
    if days < 1:
        raise ValueError(f"days must be at least 1, got {days}")
    if min_commits < 1:
        raise ValueError(f"min_commits must be at least 1, got {min_commits}")
    if not 0 < min_confidence <= 1:
        raise ValueError(f"min_confidence must be in (0, 1], got {min_confidence}")
    if top_n is not None and top_n < 1:
        raise ValueError(f"top must be at least 1, got {top_n}")


# ---------------------------------------------------------------------------
# Git inputs
# ---------------------------------------------------------------------------

def file_stats(commits: list[dict]) -> dict[str, FileStats]:
    """Commits and distinct authors per file, from _git_log() output."""
    counts: dict[str, int] = {}
    authors: dict[str, set[str]] = {}
    for commit in commits:
        author = commit.get("author") or ""
        for f in {f.replace("\\", "/") for f in commit.get("files", []) if f}:
            counts[f] = counts.get(f, 0) + 1
            names = authors.setdefault(f, set())
            if author:
                names.add(author)
    return {f: FileStats(commits=n, authors=len(authors[f])) for f, n in counts.items()}


def _repo_prefix(root: Path) -> str:
    """The project's path inside its repository ('' at the top, else 'sub/dir/')."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-prefix"],
        cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"could not locate {root.name} inside its git repository")
    return result.stdout.strip()


def _rebase(path: str, prefix: str) -> str | None:
    """*path* relative to the project, or None when it lies outside it."""
    p = path.replace("\\", "/")
    if not prefix:
        return p
    return p[len(prefix):] if p.startswith(prefix) else None


def _rebase_commits(commits: list[dict], prefix: str) -> list[dict]:
    """
    Rewrite commit file paths relative to the project. Files outside it are
    dropped, and so are commits left with no files.
    """
    out = []
    for commit in commits:
        files = [r for r in (_rebase(f, prefix) for f in commit.get("files", []) if f)
                 if r is not None]
        if files:
            out.append({**commit, "files": files})
    return out


def _rebase_pairs(pairs: list[CoupledPair], prefix: str) -> list[CoupledPair]:
    """
    Rebase coupled pairs onto the project; drop pairs with a file outside it.

    Coupling is computed on the repository-wide commits first, so the
    bulk-commit filter sees each commit's full file list.
    """
    out = []
    for pair in pairs:
        a, b = _rebase(pair.file_a, prefix), _rebase(pair.file_b, prefix)
        if a is not None and b is not None:
            out.append(CoupledPair(file_a=a, file_b=b, cochanges=pair.cochanges,
                                   commits_a=pair.commits_a, commits_b=pair.commits_b,
                                   confidence=pair.confidence))
    return out


# ---------------------------------------------------------------------------
# Extraction candidate
# ---------------------------------------------------------------------------

def extraction_candidate(root: str | Path, rel_path: str) -> Candidate | None:
    """
    The largest top-level class in a Python file, or None.

    None when the file is not Python, cannot be read or parsed, resolves
    outside *root*, has no class, or holds nothing but that one class
    (extracting the only definition of a module into its own module changes
    nothing). Size is the class's line span; the earlier class wins a tie.
    """
    if not rel_path.endswith(".py"):
        return None
    base = Path(root).resolve()
    try:
        path = (base / rel_path).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return None
        source = path.read_bytes()
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return None
    defs = [n for n in tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in defs if isinstance(n, ast.ClassDef)]
    if not classes or len(defs) < 2:
        return None
    best = max(classes, key=lambda n: ((n.end_lineno or n.lineno) - n.lineno, -n.lineno))
    return Candidate(
        name=best.name,
        line=best.lineno,
        lines=(best.end_lineno or best.lineno) - best.lineno + 1,
        file_lines=len(source.splitlines()),
    )


# ---------------------------------------------------------------------------
# Score delta
# ---------------------------------------------------------------------------

def _step_paths(step: RefactorStep) -> set[str]:
    return {op.path.replace("\\", "/") for op in step.operations
            if op.path and not op.path.startswith(_PLACEHOLDER_PREFIX)}


def _best_step(steps: list[RefactorStep]) -> RefactorStep | None:
    """Highest score_impact, lowest id on a tie."""
    return min(steps, key=lambda s: (-s.score_impact, s.id)) if steps else None


def _plan_steps_for(plan: RefactoringPlan, path: str) -> list[RefactorStep]:
    return [s for s in plan.steps if path in _step_paths(s)]


def _rule_delta(action: str, path: str, fan_in: int | None,
                fan_out: int | None) -> tuple[int, str] | None:
    """Run the planner's own rule for the action, so the number cannot drift."""
    if action == HUB and fan_in is not None:
        pattern = AntiPattern(id="hotspot", type="hub-file", severity="HIGH", file=path,
                              description="", metrics={"fan_in": fan_in})
        steps = _rule_hub_splitter([pattern], 1)
        return steps[0].score_impact, f"planner rule hub-splitter for fan-in {fan_in}"
    if action == GOD and fan_out is not None:
        pattern = AntiPattern(id="hotspot", type="god-class", severity="HIGH", file=path,
                              description="", metrics={"fan_out": fan_out})
        steps = _rule_god_class_splitter([pattern], 1)
        return steps[0].score_impact, f"planner rule god-class-splitter for fan-out {fan_out}"
    return None


def _score_delta(action: str, path: str, fan_in: int | None, fan_out: int | None,
                 plan: RefactoringPlan | None) -> tuple[int | None, str]:
    """
    (delta, basis). Only a source that scores the prescribed action counts:
    a plan step for another rule on the same file is mentioned, never used.
    """
    steps = _plan_steps_for(plan, path) if plan is not None else []
    rule = _ACTION_RULE.get(action)
    step = _best_step([s for s in steps if s.rule == rule])
    if step is not None:
        return step.score_impact, f"plan step {step.id}, {step.rule}"
    computed = _rule_delta(action, path, fan_in, fan_out)
    if computed is not None:
        return computed
    if action == VOCABULARY:
        basis = ("not derivable: the planner does not score a shared vocabulary, "
                 "and splitting one is not advised")
    else:
        basis = "not derivable: no planner rule scores this action"
    other = _best_step(steps)
    if other is not None:
        basis += (f"; plan step {other.id} ({other.rule}, {other.score_impact:+d} pts) "
                  "also changes this file")
    return None, basis


# ---------------------------------------------------------------------------
# Advice
# ---------------------------------------------------------------------------

def _partners(pairs: list[CoupledPair], modules: dict, min_confidence: float,
              present: set[str] | None) -> dict[str, list[CoChange]]:
    out: dict[str, list[CoChange]] = {}
    for pair in pairs:
        if pair.confidence < min_confidence:
            continue
        if _is_test_path(pair.file_a) or _is_test_path(pair.file_b):
            continue
        if present is not None and (pair.file_a not in present or pair.file_b not in present):
            continue
        between = _imports_between(modules, pair.file_a, pair.file_b)
        for this, other in ((pair.file_a, pair.file_b), (pair.file_b, pair.file_a)):
            out.setdefault(this, []).append(
                CoChange(path=other, cochanges=pair.cochanges,
                         confidence=pair.confidence, imports_between=between))
    for items in out.values():
        items.sort(key=lambda c: (-c.confidence, -c.cochanges, c.path))
    return out


def _coupled_text(partners: list[CoChange]) -> str:
    top = partners[0]
    more = f" (and {_count(len(partners) - 1, 'other file')})" if len(partners) > 1 else ""
    head = (f"It changed together with `{top.path}` in {top.cochanges} commits "
            f"(confidence {top.confidence:.2f}){more}")
    if top.imports_between is False:
        return (f"{head} with no import between them, so they share a hidden contract. "
                "Move that contract into one module both import, or co-locate the two files.")
    if top.imports_between is True:
        return (f"{head}, and one imports the other. Narrow the interface between them so "
                "a change to one stops forcing a change to the other.")
    return (f"{head}. Check whether they share a hidden contract; if so, move it into one "
            "module both import, or co-locate the two files.")


def _recommendation(action: str, path: str, fan_in: int | None, fan_out: int | None,
                    partners: list[CoChange], candidate: Candidate | None) -> str:
    name = Path(path).name
    if action == HUB:
        interface = _split_path(path, "interface")
        if candidate is not None:
            return (f"Extract `{candidate.name}` ({candidate.lines} of {candidate.file_lines} "
                    f"lines) into its own module behind a stable interface (`{interface}`), "
                    f"then point the {fan_in} importers at the interface.")
        return (f"Extract a stable interface from {name} into `{interface}` and point its "
                f"{fan_in} importers at it.")
    if action == VOCABULARY:
        return ("It imports nothing itself: it is a shared vocabulary, not a hub, so "
                "splitting it would only duplicate it. Keep it stable and review every "
                "change to it as an interface change.")
    if action == GOD:
        lead = f"It imports {fan_out} modules (the god-class threshold is {GOD_CLASS_FAN_OUT})."
        if candidate is not None:
            return (f"{lead} Split it by responsibility: start by moving `{candidate.name}` "
                    f"({candidate.lines} of {candidate.file_lines} lines) into its own "
                    f"module, then reduce {name} to a thin coordinator.")
        return (f"{lead} Split it by responsibility into `{_split_path(path, 'core')}` and "
                f"`{_split_path(path, 'utils')}`, and reduce {name} to a thin coordinator.")
    return _coupled_text(partners)


def _choose_action(fan_in: int | None, fan_out: int | None, has_partners: bool,
                   fan_in_threshold: int, fan_out_threshold: int) -> str | None:
    if fan_in is not None and fan_in > fan_in_threshold:
        return VOCABULARY if fan_out == 0 else HUB
    if fan_out is not None and fan_out > fan_out_threshold:
        return GOD
    if has_partners:
        return COUPLED
    return None


def find_hotspots(stats: dict[str, FileStats], modules: dict, pairs: list[CoupledPair],
                  days: int, plan: RefactoringPlan | None = None,
                  present: set[str] | None = None,
                  candidate_for: Callable[[str], Candidate | None] | None = None,
                  min_commits: int = MIN_COMMITS,
                  min_confidence: float = MIN_CONFIDENCE,
                  fan_in_threshold: int = HUB_FILE_FAN_IN,
                  fan_out_threshold: int = GOD_CLASS_FAN_OUT,
                  top_n: int | None = None) -> list[HotspotAdvice]:
    """
    Advice for every hotspot, most-changed first.

    stats:   file_stats() output, paths relative to the project root.
    modules: the import graph's module map ({} when there is no graph; then
             only change-coupling hotspots can be found).
    present: when given, files outside it (deleted since, or never on disk)
             are neither hotspots nor partners.
    candidate_for: looks up an extraction candidate for a hub or god file.
    """
    _validate(days, min_commits, min_confidence, top_n)
    partners = _partners(pairs, modules, min_confidence, present)
    advice: list[HotspotAdvice] = []

    for path, st in stats.items():
        if st.commits < min_commits or _is_test_path(path):
            continue
        if present is not None and path not in present:
            continue
        entry = modules.get(path) if modules else None
        fan_in = _production_fan_in(entry) if isinstance(entry, dict) else None
        fan_out = _fan_out(entry) if isinstance(entry, dict) else None
        if modules and entry is None:
            fan_in = fan_out = 0     # the graph exists but nothing imports or is imported
        mine = partners.get(path, [])
        action = _choose_action(fan_in, fan_out, bool(mine), fan_in_threshold,
                                fan_out_threshold)
        if action is None:
            continue

        candidate = None
        if action in (HUB, GOD) and candidate_for is not None:
            candidate = candidate_for(path)
        delta, basis = _score_delta(action, path, fan_in, fan_out, plan)

        notes = []
        if st.authors == 1:
            notes.append("Every change came from one author: review or pair on changes "
                         "to it so the knowledge is shared.")
        if action != COUPLED and mine:
            top = mine[0]
            notes.append(f"It also changes together with `{top.path}` "
                         f"(confidence {top.confidence:.2f}).")

        advice.append(HotspotAdvice(
            path=path, days=days, commits=st.commits, authors=st.authors,
            fan_in=fan_in, fan_out=fan_out, action=action,
            recommendation=_recommendation(action, path, fan_in, fan_out, mine, candidate),
            partners=mine, candidate=candidate,
            score_delta=delta, delta_basis=basis, notes=notes,
        ))

    advice.sort(key=lambda a: (-a.commits, -(a.fan_in or 0), -(a.fan_out or 0), a.path))
    return advice if top_n is None else advice[:top_n]


def advise(project_path: str | Path, days: int = DEFAULT_DAYS,
           plan: RefactoringPlan | None = None, modules: dict | None = None,
           language: str | None = None, min_commits: int = MIN_COMMITS,
           min_confidence: float = MIN_CONFIDENCE, top_n: int | None = DEFAULT_TOP,
           cache_dir: str | Path | None = None) -> HotspotReport:
    """
    Read git history and the import graph for *project_path* and advise.

    Raises ValueError when the path is not a directory or not inside a git
    repository: without history there is nothing to evaluate, and that is
    reported as an error, never as "no hotspots".
    """
    _validate(days, min_commits, min_confidence, top_n)
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {project_path}")
    if not _is_git_repo(root):
        raise ValueError(f"not a git repository: {root.name}")

    prefix = _repo_prefix(root)
    raw = _git_log(root, days, cache_dir=cache_dir)
    commits = _rebase_commits(raw, prefix)
    stats = file_stats(commits)
    report = HotspotReport(days=days, files_examined=len(stats))
    if not commits:
        report.warnings.append(f"No commits touched this project in the last {days} days: "
                               "nothing to evaluate.")
        return report

    graph: dict = modules if modules is not None else _graph_modules(root, language)
    if not graph:
        report.warnings.append("No import graph: fan-in and fan-out were not measured, "
                               "so only change-coupling hotspots can be found.")

    pairs = _rebase_pairs(change_coupling(raw, top_n=100_000, min_cochanges=MIN_COCHANGES),
                          prefix)
    present = {p for p in stats if _inside(root, p)}
    report.hotspots = find_hotspots(
        stats, graph, pairs, days, plan=plan, present=present,
        candidate_for=lambda rel: extraction_candidate(root, rel),
        min_commits=min_commits, min_confidence=min_confidence, top_n=top_n,
    )
    return report


def _inside(root: Path, rel: str) -> bool:
    """True for an existing file that resolves inside *root*."""
    try:
        path = (root / rel).resolve()
        return path.is_relative_to(root) and path.is_file()
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_report(report: HotspotReport) -> str:
    lines = [f"\nHotspot Advisor  (last {_window(report.days)}, "
             f"{report.files_examined} changed file(s) examined)"]
    if not report.hotspots:
        lines.append("  No hotspots: no file combines churn with coupling in this window.")
    for n, h in enumerate(report.hotspots, 1):
        lines.append(f"\n  {n}. {h.path}  [{h.action}]")
        lines.append(f"     {h.evidence()}")
        lines.append(f"     {h.recommendation}")
        for note in h.notes:
            lines.append(f"     Note: {note}")
        lines.append(f"     {h.delta_text()}")
    for w in report.warnings:
        lines.append(f"  WARNING: {w}")
    return "\n".join(lines)


def _fail(message: str) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(2)


def _emit(text: str) -> None:
    """Print *text*, or exit 2 with advice when the console cannot encode it."""
    try:
        print(text)
    except UnicodeEncodeError:
        _fail(f"the output has characters the console encoding ({sys.stdout.encoding}) "
              "cannot represent; use --json.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Hotspot Advisor"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help=f"show at most this many hotspots (default {DEFAULT_TOP})")
    parser.add_argument("--min-commits", type=int, default=MIN_COMMITS)
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                        help="change-coupling confidence that counts as coupling")
    parser.add_argument("--plan", default=None,
                        help="refactoring plan JSON; its steps supply the score deltas")
    parser.add_argument("--language", default=None)
    parser.add_argument("--cache-dir", default=None,
                        help="Opt-in: cache the parsed git log in this directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plan = None
    if args.plan:
        from genesis_architect_pro.prompt_export import plan_from_dict
        try:
            plan = plan_from_dict(json.loads(Path(args.plan).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            _fail(f"could not load the plan {Path(args.plan).name}: {exc}")

    try:
        report = advise(args.project_path, days=args.days, plan=plan,
                        language=args.language, min_commits=args.min_commits,
                        min_confidence=args.min_confidence, top_n=args.top,
                        cache_dir=args.cache_dir)
    except ValueError as exc:
        _fail(str(exc))

    if args.json:
        _emit(json.dumps(report.to_dict(), indent=2))
    else:
        _emit(format_report(report))


if __name__ == "__main__":
    main()
