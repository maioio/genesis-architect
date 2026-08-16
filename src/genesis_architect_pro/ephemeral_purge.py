"""Auto-Purge — deterministic cleanup of expired ephemeral resources.

Finds three kinds of debris inside a project and, only when explicitly told
to, removes them:

  1. Ephemeral directories  — marked by an `.ephemeral.json` manifest
  2. Orphaned git worktrees — stale by inactivity TTL
  3. Stale lock/PID files   — whose owning process is gone

No LLM, no network. Pure filesystem + git inspection, same deterministic
philosophy as every other analysis engine here.

Safety model — this module deletes things, so the rules are strict:

  * **Dry-run by default.** `purge()` reports without touching disk unless
    `apply=True` is passed explicitly.
  * **Opt-in only.** A directory is ephemeral solely by virtue of carrying an
    `.ephemeral.json` manifest. Nothing is inferred from names or locations,
    so an unmarked directory can never be swept up by accident.
  * **Project-scoped.** Every resolved path must sit under project_root.
    Symlinks are resolved before that check, so a link pointing outside is
    refused rather than followed.
  * **Fail safe, not fail clean.** Unreadable manifest, undeterminable PID,
    git command that errors — all resolve to "protected", never to "delete".
  * **`git worktree remove`, never `rm -rf`.** Removing a worktree by
    filesystem delete leaves stale metadata in `.git/worktrees/`; and the
    `--force` variant discards uncommitted work, which is precisely how a
    widely-reported incident destroyed 29 active worktrees in one command.
    This module never passes `--force`, and refuses any worktree with
    uncommitted changes.

Every refusal is recorded in `PurgeReport.protected` with its reason, so the
safety behaviour is visible in the output rather than implied by silence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = ".ephemeral.json"

# Branches never removed alongside a worktree, whatever their age.
PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "trunk", "release"})

# Lock/PID files older than this with a dead owner are considered stale.
DEFAULT_LOCK_TTL_HOURS = 1.0
# Worktrees with no activity for this long are purge candidates.
DEFAULT_WORKTREE_TTL_HOURS = 24.0 * 7


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PurgeCandidate:
    """A resource eligible for removal."""

    path: Path
    kind: str          # "ephemeral_dir" | "worktree" | "stale_lock"
    age_hours: float
    reason: str
    branch: str = ""   # worktrees only


@dataclass
class ProtectedItem:
    """A resource that was examined and deliberately NOT removed."""

    path: Path
    kind: str
    reason: str


@dataclass
class PurgeReport:
    dry_run: bool = True
    candidates: list[PurgeCandidate] = field(default_factory=list)
    protected: list[ProtectedItem] = field(default_factory=list)
    purged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def expired_count(self) -> int:
        return len(self.candidates)

    def summary(self) -> str:
        if self.dry_run:
            if not self.candidates:
                return "Nothing expired. Environment is clean."
            return (
                f"{len(self.candidates)} expired resource(s) found "
                f"({len(self.protected)} protected). Nothing deleted — dry run."
            )
        return (
            f"Removed {len(self.purged)} resource(s); "
            f"{len(self.protected)} protected, {len(self.errors)} error(s)."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _age_hours(moment: datetime) -> float:
    return (_now() - moment).total_seconds() / 3600.0


def _mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _pid_alive(pid: int) -> bool:
    """Is this PID running? Unknown answers count as alive (fail safe)."""
    if pid <= 0:
        return True  # nonsense PID — refuse to treat the file as stale
    if os.name == "nt":
        try:
            import ctypes

            # PROCESS_QUERY_LIMITED_INFORMATION — enough to test existence
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return True  # couldn't tell → assume alive
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return True
    return True


def _git(args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a git command. Returns (ok, output). Never raises."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()
    return True, (proc.stdout or "").strip()


# ---------------------------------------------------------------------------
# Detector 1 — ephemeral directories (.ephemeral.json)
# ---------------------------------------------------------------------------


def read_manifest(directory: Path) -> dict | None:
    """Parse a directory's `.ephemeral.json`. None if absent or unusable."""
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _manifest_expiry(data: dict) -> tuple[datetime, float] | None:
    """Return (created_at, ttl_hours), or None if the manifest is unusable."""
    raw_created = data.get("created_at")
    raw_ttl = data.get("ttl_hours")
    if not isinstance(raw_created, str) or raw_ttl is None:
        return None
    try:
        created = datetime.fromisoformat(raw_created)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    try:
        ttl = float(raw_ttl)
    except (TypeError, ValueError):
        return None
    if ttl <= 0:
        return None
    return created, ttl


def scan_ephemeral_dirs(project_root: Path) -> tuple[list[PurgeCandidate], list[ProtectedItem]]:
    """Find directories carrying an expired `.ephemeral.json` manifest."""
    candidates: list[PurgeCandidate] = []
    protected: list[ProtectedItem] = []

    try:
        manifests = list(project_root.rglob(MANIFEST_NAME))
    except (OSError, RuntimeError):
        return candidates, protected

    for manifest_path in manifests:
        directory = manifest_path.parent

        if not _within_root(directory, project_root):
            protected.append(ProtectedItem(
                path=directory, kind="ephemeral_dir",
                reason="resolves outside the project root",
            ))
            continue

        if directory.resolve() == project_root.resolve():
            protected.append(ProtectedItem(
                path=directory, kind="ephemeral_dir",
                reason="is the project root itself",
            ))
            continue

        data = read_manifest(directory)
        if data is None:
            protected.append(ProtectedItem(
                path=directory, kind="ephemeral_dir",
                reason="manifest missing or unreadable — refusing to guess",
            ))
            continue

        parsed = _manifest_expiry(data)
        if parsed is None:
            protected.append(ProtectedItem(
                path=directory, kind="ephemeral_dir",
                reason="manifest lacks a usable created_at/ttl_hours pair",
            ))
            continue

        created, ttl = parsed
        age = _age_hours(created)
        if age < ttl:
            protected.append(ProtectedItem(
                path=directory, kind="ephemeral_dir",
                reason=f"still within TTL ({age:.1f}h of {ttl:.1f}h)",
            ))
            continue

        candidates.append(PurgeCandidate(
            path=directory, kind="ephemeral_dir", age_hours=age,
            reason=f"TTL expired ({age:.1f}h old, TTL {ttl:.1f}h)",
        ))

    return candidates, protected


# ---------------------------------------------------------------------------
# Detector 2 — orphaned git worktrees
# ---------------------------------------------------------------------------


def _parse_worktree_list(output: str) -> list[dict]:
    """Parse `git worktree list --porcelain` into dicts."""
    entries: list[dict] = []
    current: dict = {}
    for line in output.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": line[len("worktree "):].strip()}
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            current["branch"] = ref.rsplit("/", 1)[-1]
        elif line.strip() == "bare":
            current["bare"] = True
        elif line.strip() == "detached":
            current["detached"] = True
    if current:
        entries.append(current)
    return entries


def scan_worktrees(
    project_root: Path,
    ttl_hours: float = DEFAULT_WORKTREE_TTL_HOURS,
) -> tuple[list[PurgeCandidate], list[ProtectedItem]]:
    """Find stale git worktrees, refusing any that still hold live work."""
    candidates: list[PurgeCandidate] = []
    protected: list[ProtectedItem] = []

    ok, output = _git(["worktree", "list", "--porcelain"], project_root)
    if not ok:
        return candidates, protected  # not a git repo, or git unavailable

    entries = _parse_worktree_list(output)
    if not entries:
        return candidates, protected

    # The first entry is always the main worktree.
    main_path = Path(entries[0]["path"]).resolve() if entries else None

    for entry in entries:
        raw_path = entry.get("path", "")
        if not raw_path:
            continue
        path = Path(raw_path)

        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            protected.append(ProtectedItem(
                path=path, kind="worktree", reason="path could not be resolved",
            ))
            continue

        if main_path is not None and resolved == main_path:
            protected.append(ProtectedItem(
                path=path, kind="worktree", reason="is the main worktree",
            ))
            continue

        if resolved == project_root.resolve():
            protected.append(ProtectedItem(
                path=path, kind="worktree", reason="is the current working tree",
            ))
            continue

        if not _within_root(path, project_root):
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason="lives outside the project root",
            ))
            continue

        if entry.get("bare"):
            protected.append(ProtectedItem(
                path=path, kind="worktree", reason="is a bare repository",
            ))
            continue

        branch = entry.get("branch", "")
        if branch in PROTECTED_BRANCHES:
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason=f"checked out on protected branch {branch!r}",
            ))
            continue

        if not path.is_dir():
            # Registered but gone from disk — metadata-only, safe to prune.
            candidates.append(PurgeCandidate(
                path=path, kind="worktree", age_hours=float("inf"), branch=branch,
                reason="registered worktree directory no longer exists",
            ))
            continue

        # Uncommitted work is an absolute veto.
        ok_status, status = _git(["status", "--porcelain"], path)
        if not ok_status:
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason="could not read git status — refusing to act blind",
            ))
            continue
        if status.strip():
            changed = len(status.strip().splitlines())
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason=f"has {changed} uncommitted change(s)",
            ))
            continue

        age = _worktree_idle_hours(path)
        if age is None:
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason="activity time could not be determined",
            ))
            continue
        if age < ttl_hours:
            protected.append(ProtectedItem(
                path=path, kind="worktree",
                reason=f"active {age:.1f}h ago (TTL {ttl_hours:.1f}h)",
            ))
            continue

        candidates.append(PurgeCandidate(
            path=path, kind="worktree", age_hours=age, branch=branch,
            reason=f"idle {age:.1f}h with a clean tree (TTL {ttl_hours:.1f}h)",
        ))

    return candidates, protected


def _worktree_idle_hours(path: Path) -> float | None:
    """Hours since the worktree last showed ANY sign of life.

    Takes the most recent of (last commit, directory mtime): if either says
    "recently touched", the worktree counts as active.
    """
    signals: list[datetime] = []

    ok, out = _git(["log", "-1", "--format=%cI"], path)
    if ok and out:
        try:
            committed = datetime.fromisoformat(out.strip())
            if committed.tzinfo is None:
                committed = committed.replace(tzinfo=timezone.utc)
            signals.append(committed)
        except ValueError:
            pass

    mtime = _mtime_utc(path)
    if mtime is not None:
        signals.append(mtime)

    if not signals:
        return None
    return _age_hours(max(signals))


# ---------------------------------------------------------------------------
# Detector 3 — stale lock / PID files
# ---------------------------------------------------------------------------

_LOCK_PATTERNS = ("*.lock", "*.pid")


def scan_stale_locks(
    project_root: Path,
    ttl_hours: float = DEFAULT_LOCK_TTL_HOURS,
) -> tuple[list[PurgeCandidate], list[ProtectedItem]]:
    """Find lock/PID files whose owning process is provably gone."""
    candidates: list[PurgeCandidate] = []
    protected: list[ProtectedItem] = []

    genesis_dir = project_root / ".genesis"
    if not genesis_dir.is_dir():
        return candidates, protected

    paths: list[Path] = []
    for pattern in _LOCK_PATTERNS:
        try:
            paths.extend(genesis_dir.rglob(pattern))
        except (OSError, RuntimeError):
            continue

    for path in paths:
        if not path.is_file():
            continue
        if not _within_root(path, project_root):
            protected.append(ProtectedItem(
                path=path, kind="stale_lock",
                reason="resolves outside the project root",
            ))
            continue

        mtime = _mtime_utc(path)
        if mtime is None:
            protected.append(ProtectedItem(
                path=path, kind="stale_lock",
                reason="mtime unreadable — refusing to guess",
            ))
            continue

        age = _age_hours(mtime)
        if age < ttl_hours:
            protected.append(ProtectedItem(
                path=path, kind="stale_lock",
                reason=f"only {age:.2f}h old (TTL {ttl_hours:.2f}h)",
            ))
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            protected.append(ProtectedItem(
                path=path, kind="stale_lock", reason="file unreadable",
            ))
            continue

        # A lock with no parseable PID is ambiguous — leave it alone.
        try:
            pid = int(raw.split()[0]) if raw.split() else 0
        except (ValueError, IndexError):
            protected.append(ProtectedItem(
                path=path, kind="stale_lock",
                reason="no parseable PID — cannot prove the owner is gone",
            ))
            continue

        if _pid_alive(pid):
            protected.append(ProtectedItem(
                path=path, kind="stale_lock",
                reason=f"owning process {pid} is still alive",
            ))
            continue

        candidates.append(PurgeCandidate(
            path=path, kind="stale_lock", age_hours=age,
            reason=f"owner PID {pid} is gone, file {age:.1f}h old",
        ))

    return candidates, protected


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------


def _remove_worktree(candidate: PurgeCandidate, project_root: Path) -> tuple[bool, str]:
    """Remove via `git worktree remove` — never `rm -rf`, never `--force`."""
    ok, err = _git(["worktree", "remove", str(candidate.path)], project_root)
    if ok:
        return True, ""
    # A directory already gone from disk only needs its metadata pruned.
    if not candidate.path.exists():
        pruned, prune_err = _git(["worktree", "prune"], project_root)
        if pruned:
            return True, ""
        return False, prune_err or "worktree prune failed"
    return False, err or "git worktree remove failed"


def purge(
    project_root: Path,
    *,
    apply: bool = False,
    worktree_ttl_hours: float = DEFAULT_WORKTREE_TTL_HOURS,
    lock_ttl_hours: float = DEFAULT_LOCK_TTL_HOURS,
) -> PurgeReport:
    """Scan for expired resources; delete them only when `apply=True`.

    The default is a dry run: it reports and returns without touching disk.
    """
    root = Path(project_root).expanduser()
    report = PurgeReport(dry_run=not apply)

    for scan in (
        lambda: scan_ephemeral_dirs(root),
        lambda: scan_worktrees(root, ttl_hours=worktree_ttl_hours),
        lambda: scan_stale_locks(root, ttl_hours=lock_ttl_hours),
    ):
        try:
            found, safe = scan()
        except Exception as exc:  # noqa: BLE001 — a detector must never abort the run
            report.errors.append(f"detector failed: {exc}")
            continue
        report.candidates.extend(found)
        report.protected.extend(safe)

    if not apply:
        return report

    for candidate in report.candidates:
        # Re-verify containment at delete time, not just at scan time.
        if candidate.kind != "worktree" and not _within_root(candidate.path, root):
            report.errors.append(f"refused (outside root): {candidate.path}")
            continue
        try:
            if candidate.kind == "worktree":
                ok, err = _remove_worktree(candidate, root)
                if not ok:
                    report.errors.append(f"{candidate.path}: {err}")
                    continue
            elif candidate.kind == "ephemeral_dir":
                shutil.rmtree(candidate.path)
            elif candidate.kind == "stale_lock":
                candidate.path.unlink()
            else:
                report.errors.append(f"unknown kind {candidate.kind!r}")
                continue
            report.purged.append(str(candidate.path))
        except OSError as exc:
            report.errors.append(f"{candidate.path}: {exc}")

    return report


# ---------------------------------------------------------------------------
# Smart reminder — surfaces debris without ever removing it
# ---------------------------------------------------------------------------


def hygiene_notice(project_root: Path) -> str | None:
    """One-line notice when expired resources exist, else None.

    Read-only by construction: it calls `purge()` in dry-run mode and cannot
    delete anything. Meant for the end of a normal session, so stale
    resources surface on their own instead of waiting to be remembered.
    """
    try:
        report = purge(Path(project_root))
    except Exception:  # noqa: BLE001 — a hygiene hint must never break a session
        return None
    if not report.candidates:
        return None

    by_kind: dict[str, int] = {}
    for candidate in report.candidates:
        by_kind[candidate.kind] = by_kind.get(candidate.kind, 0) + 1

    # Explicit plurals — appending "s" would produce "directorys".
    labels = {
        "ephemeral_dir": ("ephemeral directory", "ephemeral directories"),
        "worktree": ("worktree", "worktrees"),
        "stale_lock": ("stale lock file", "stale lock files"),
    }
    parts = []
    for kind, count in sorted(by_kind.items()):
        singular, plural = labels.get(kind, (kind, f"{kind}s"))
        parts.append(f"{count} expired {singular if count == 1 else plural}")
    return (
        f"Notice: {', '.join(parts)} found. "
        f"Run `genesis purge` to review, or `genesis purge --apply` to clean."
    )


# ---------------------------------------------------------------------------
# Manifest authoring
# ---------------------------------------------------------------------------


def mark_ephemeral(
    directory: Path,
    ttl_hours: float,
    purpose: str = "",
) -> Path:
    """Write an `.ephemeral.json` manifest marking a directory as temporary."""
    if ttl_hours <= 0:
        raise ValueError("ttl_hours must be positive")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": _now().isoformat(),
                "ttl_hours": float(ttl_hours),
                "purpose": purpose,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def format_report(report: PurgeReport) -> str:
    """Render a PurgeReport for the terminal."""
    lines = ["", "  Genesis Auto-Purge", ""]

    if report.candidates:
        header = "  Expired (would remove):" if report.dry_run else "  Expired:"
        lines.append(header)
        for candidate in report.candidates:
            branch = f" [{candidate.branch}]" if candidate.branch else ""
            lines.append(f"    {candidate.kind:<15} {candidate.path}{branch}")
            lines.append(f"    {'':<15} {candidate.reason}")
        lines.append("")

    if report.protected:
        lines.append(f"  Protected ({len(report.protected)}):")
        for item in report.protected:
            lines.append(f"    {item.kind:<15} {item.path}")
            lines.append(f"    {'':<15} {item.reason}")
        lines.append("")

    if report.purged:
        lines.append(f"  Removed ({len(report.purged)}):")
        for path in report.purged:
            lines.append(f"    {path}")
        lines.append("")

    if report.errors:
        lines.append(f"  Errors ({len(report.errors)}):")
        for err in report.errors:
            lines.append(f"    {err}")
        lines.append("")

    lines.append(f"  {report.summary()}")
    if report.dry_run and report.candidates:
        lines.append("  Nothing was deleted. Re-run with --apply to remove them.")
    lines.append("")
    return "\n".join(lines)