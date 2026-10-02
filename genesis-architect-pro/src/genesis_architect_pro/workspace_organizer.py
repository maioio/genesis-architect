"""Organize — deterministic routing of loose top-level files into place.

Scans the *top level* of a project (never recursive) for files that a
`.genesis/organize_rules.yaml` rule maps to a target directory, and, only when
explicitly told to, moves them there.

No LLM, no network. Pure filesystem inspection, same deterministic philosophy
as `ephemeral_purge.py` — this module mirrors its safety model on purpose:

  * **Dry-run by default.** `organize()` reports without touching disk unless
    `apply=True` is passed explicitly.
  * **Safe paths are never touched.** Anything in `DEFAULT_SAFE_PATHS`, or
    listed under `safe_paths` in the rules file, is always left alone —
    regardless of whether some rule would otherwise match it.
  * **Files only, top level only.** Directories are never moved and
    subdirectories are never descended into, so this can't reorganize a
    project's actual source tree — only tidy loose files dropped at the root.
  * **Project-scoped.** Every resolved path must sit under project_root.
    Symlinks are resolved before that check, so a link pointing outside is
    refused rather than followed.
  * **Never overwrites.** A file is not moved onto an existing destination:
    the collision is reported in the dry run and refused again at move time.
  * **Fail safe, not fail clean.** A malformed rules file, an unreadable
    entry, a target that would land outside the project — all resolve to
    "protected"/"error", never to "move".
  * **No rule matched is not silence.** A top-level file that nothing routes
    is recorded in `OrganizeReport.protected` with an explicit reason, so the
    output stays a complete account of every file it looked at.
"""

from __future__ import annotations

import fnmatch
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULES_FILENAME = "organize_rules.yaml"

# Never routed anywhere, whatever a rule says — config, VCS, and tooling
# anchors that a misfiled rule must not be able to relocate.
DEFAULT_SAFE_PATHS = frozenset({
    ".git", ".github", ".vscode", ".claude", ".genesis", ".mcp",
    ".gitignore", ".gitattributes", "CLAUDE.md", "README.md", "LICENSE",
    "pyproject.toml", "package.json", "package-lock.json", "poetry.lock",
    "uv.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "ARCHITECTURE_INVARIANTS.json", "node_modules", ".venv", "venv",
    "src", "tests", "docs",
})

# Applied in order; the first pattern that matches a filename wins.
DEFAULT_RULES: list[dict[str, str]] = [
    {"match": "*.log", "target": "logs/"},
    {"match": "*.tmp", "target": ".tmp/"},
    {"match": "*.bak", "target": ".tmp/"},
    {"match": "*_TEMP.md", "target": ".tmp/"},
    {"match": "*.pyc", "target": ".tmp/"},
]

DEFAULT_RULES_YAML = """\
# Genesis Architect — organize rules
#
# `genesis organize` routes loose top-level files into place. It never
# recurses into subdirectories and never moves a directory, only files.
#
# safe_paths: file/directory names at the project root that are never
# touched, no matter what a rule below would otherwise match.
safe_paths:
  - .git
  - .github
  - .vscode
  - .claude
  - .genesis
  - .mcp
  - .gitignore
  - .gitattributes
  - CLAUDE.md
  - README.md
  - LICENSE
  - pyproject.toml
  - package.json
  - node_modules
  - .venv
  - venv
  - src
  - tests
  - docs

# rules: applied in order: the first "match" glob that fits a filename wins,
# and the file is moved under "target" (created if it doesn't exist yet).
rules:
  - match: "*.log"
    target: "logs/"
  - match: "*.tmp"
    target: ".tmp/"
  - match: "*.bak"
    target: ".tmp/"
  - match: "*_TEMP.md"
    target: ".tmp/"
  - match: "*.pyc"
    target: ".tmp/"
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class OrganizeCandidate:
    """A file eligible for moving."""

    path: Path
    target: Path
    reason: str


@dataclass
class OrganizeProtected:
    """A file that was examined and deliberately left in place."""

    path: Path
    reason: str


@dataclass
class OrganizeReport:
    dry_run: bool = True
    candidates: list[OrganizeCandidate] = field(default_factory=list)
    protected: list[OrganizeProtected] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.dry_run:
            if not self.candidates:
                return "Nothing to organize. Top level is already tidy."
            return (
                f"{len(self.candidates)} file(s) would move "
                f"({len(self.protected)} left in place). Nothing moved — dry run."
            )
        return (
            f"Moved {len(self.moved)} file(s); "
            f"{len(self.protected)} left in place, {len(self.errors)} error(s)."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _within_root(path: Path, root: Path) -> bool:
    """True only if `path` genuinely resolves inside `root`.

    Resolution happens BEFORE the comparison, so a symlink aimed outside the
    project fails this check instead of being followed.
    """
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == root_resolved or root_resolved in resolved.parents


def _occupied(path: Path) -> bool:
    """True if anything, including a dangling symlink, already sits at `path`.

    `shutil.move` overwrites an existing destination file when `os.rename`
    fails, so the module has to refuse the collision itself.
    """
    return path.exists() or path.is_symlink()


def rules_path_for(project_root: Path) -> Path:
    return Path(project_root) / ".genesis" / RULES_FILENAME


def init_rules(project_root: Path) -> tuple[Path, bool]:
    """Write the default rules file if one doesn't exist yet.

    Never overwrites an existing file. Returns (path, created).
    """
    target = rules_path_for(project_root)
    if target.exists():
        return target, False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEFAULT_RULES_YAML, encoding="utf-8")
    return target, True


def load_rules(project_root: Path) -> tuple[frozenset[str], list[dict[str, str]], list[str]]:
    """Load safe_paths and rules from `.genesis/organize_rules.yaml`.

    Missing file: silently falls back to defaults. Malformed file: falls back
    to defaults too, but records why — a rules file must never be able to
    crash the command or, worse, silently resolve to "no safe paths at all".
    """
    path = rules_path_for(project_root)
    if not path.is_file():
        return DEFAULT_SAFE_PATHS, DEFAULT_RULES, []

    errors: list[str] = []
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad rules file must never crash the run
        errors.append(f"failed to read {path}: {exc}; using built-in defaults")
        return DEFAULT_SAFE_PATHS, DEFAULT_RULES, errors

    if not isinstance(raw, dict):
        errors.append(f"{path}: not a mapping at the top level; using built-in defaults")
        return DEFAULT_SAFE_PATHS, DEFAULT_RULES, errors

    safe_paths = _coerce_safe_paths(raw.get("safe_paths"), path, errors)
    rules = _coerce_rules(raw.get("rules"), path, errors)
    return safe_paths, rules, errors


def _coerce_safe_paths(raw: Any, path: Path, errors: list[str]) -> frozenset[str]:
    if raw is None:
        return DEFAULT_SAFE_PATHS
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        errors.append(f"{path}: 'safe_paths' must be a list of strings; using built-in defaults")
        return DEFAULT_SAFE_PATHS
    # Always union with the built-in defaults — a rules file can only widen
    # protection, never narrow it below the floor this module ships with.
    return frozenset(raw) | DEFAULT_SAFE_PATHS


def _coerce_rules(raw: Any, path: Path, errors: list[str]) -> list[dict[str, str]]:
    if raw is None:
        return DEFAULT_RULES
    if not isinstance(raw, list):
        errors.append(f"{path}: 'rules' must be a list; using built-in defaults")
        return DEFAULT_RULES
    rules: list[dict[str, str]] = []
    for entry in raw:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("match"), str)
            and isinstance(entry.get("target"), str)
        ):
            rules.append({"match": entry["match"], "target": entry["target"]})
        else:
            errors.append(f"{path}: skipping malformed rule entry: {entry!r}")
    return rules or DEFAULT_RULES


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def scan(project_root: Path) -> tuple[list[OrganizeCandidate], list[OrganizeProtected], list[str]]:
    """Match top-level files against rules; never recurse, never touch disk."""
    root = Path(project_root)
    safe_paths, rules, load_errors = load_rules(root)

    candidates: list[OrganizeCandidate] = []
    protected: list[OrganizeProtected] = []

    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        return candidates, protected, load_errors + [f"cannot list {root}: {exc}"]

    for entry in entries:
        name = entry.name
        if not entry.is_file():
            continue  # directories are never routed
        if name in safe_paths:
            protected.append(OrganizeProtected(entry, "listed in safe_paths"))
            continue
        if not _within_root(entry, root):
            # is_file() follows symlinks; report the refusal now so a dry run
            # matches what --apply will actually do.
            protected.append(OrganizeProtected(entry, "symlink resolves outside project root"))
            continue

        matched = False
        for rule in rules:
            if fnmatch.fnmatch(name, rule["match"]):
                target_dir = (root / rule["target"]).resolve()
                destination = target_dir / name
                if not _within_root(target_dir, root):
                    protected.append(
                        OrganizeProtected(entry, f"rule target escapes project root: {rule['target']}")
                    )
                elif _occupied(destination):
                    protected.append(
                        OrganizeProtected(entry, f"destination already exists: {destination}")
                    )
                else:
                    candidates.append(
                        OrganizeCandidate(entry, destination, f"matched rule '{rule['match']}'")
                    )
                matched = True
                break
        if not matched:
            protected.append(OrganizeProtected(entry, "no rule matched — left in place"))

    return candidates, protected, load_errors


# ---------------------------------------------------------------------------
# Organize
# ---------------------------------------------------------------------------


def organize(project_root: Path, *, apply: bool = False) -> OrganizeReport:
    """Scan top-level files for a routing rule; move them only when `apply=True`.

    The default is a dry run: it reports and returns without touching disk.
    """
    root = Path(project_root).expanduser()
    report = OrganizeReport(dry_run=not apply)

    try:
        candidates, protected, errors = scan(root)
    except Exception as exc:  # noqa: BLE001 — a scan must never abort the run
        report.errors.append(f"scan failed: {exc}")
        return report

    report.candidates.extend(candidates)
    report.protected.extend(protected)
    report.errors.extend(errors)

    if not apply:
        return report

    for candidate in report.candidates:
        # Re-verify containment at move time, not just at scan time.
        if not _within_root(candidate.path, root) or not _within_root(candidate.target, root):
            report.errors.append(f"refused (outside root): {candidate.path}")
            continue
        # Re-check the collision too: something may have appeared since the scan.
        if _occupied(candidate.target):
            report.errors.append(f"refused (destination exists): {candidate.target}")
            continue
        try:
            candidate.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidate.path), str(candidate.target))
            report.moved.append(str(candidate.path))
        except OSError as exc:
            report.errors.append(f"{candidate.path}: {exc}")

    return report


def format_report(report: OrganizeReport) -> str:
    """Render an OrganizeReport for the terminal."""
    lines = ["", "  Genesis Organize", ""]

    if report.candidates:
        header = "  Would move:" if report.dry_run else "  Moved:"
        lines.append(header)
        for candidate in report.candidates:
            lines.append(f"    {candidate.path} -> {candidate.target}")
            lines.append(f"    {'':<15} {candidate.reason}")
        lines.append("")

    if report.protected:
        lines.append(f"  Left in place ({len(report.protected)}):")
        for item in report.protected:
            lines.append(f"    {item.path}")
            lines.append(f"    {'':<15} {item.reason}")
        lines.append("")

    if report.moved:
        lines.append(f"  Moved ({len(report.moved)}):")
        for path in report.moved:
            lines.append(f"    {path}")
        lines.append("")

    if report.errors:
        lines.append(f"  Errors ({len(report.errors)}):")
        for err in report.errors:
            lines.append(f"    {err}")
        lines.append("")

    lines.append(f"  {report.summary()}")
    if report.dry_run and report.candidates:
        lines.append("  Nothing was moved. Re-run with --apply to move them.")
    lines.append("")
    return "\n".join(lines)
