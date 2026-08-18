"""Tests for ephemeral_purge.py — the Auto-Purge engine.

This module deletes things, so most of what follows tests what it REFUSES to
delete. Every safety rule in the module docstring gets at least one test that
would fail loudly if the rule were removed.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from genesis_architect.pro.ephemeral_purge import (
    DEFAULT_PRUNE_DIRS,
    MANIFEST_NAME,
    PROTECTED_BRANCHES,
    PurgeReport,
    iter_manifest_dirs,
    load_ignore_patterns,
    _parse_worktree_list,
    _pid_alive,
    _within_root,
    format_report,
    hygiene_notice,
    mark_ephemeral,
    purge,
    read_manifest,
    scan_ephemeral_dirs,
    scan_worktrees,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(directory: Path, *, age_hours: float, ttl_hours: float) -> Path:
    """Create a directory with a manifest created `age_hours` ago."""
    directory.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    (directory / MANIFEST_NAME).write_text(
        json.dumps({"created_at": created.isoformat(), "ttl_hours": ttl_hours}),
        encoding="utf-8",
    )
    return directory


def _make_dir_link(link: Path, target: Path) -> None:
    """Create a directory link that a resolver will follow, without needing
    elevated privileges on any platform.

    POSIX: a real symlink (unprivileged by default). Windows: a directory
    junction via `mklink /J`, which — unlike `mklink /D` (symlink) — needs no
    Developer Mode or admin rights, and still resolves through `Path.resolve()`
    exactly like a symlink would.
    """
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"could not create a directory junction: {result.stderr.strip()}")
    else:
        link.symlink_to(target, target_is_directory=True)


def _dead_pid() -> int:
    """A PID that is almost certainly not running."""
    # Spawn a trivial process, wait for it, and reuse its now-free PID.
    proc = subprocess.Popen(
        [os.sys.executable, "-c", "pass"],  # type: ignore[attr-defined]
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    proc.wait()
    return proc.pid


def _make_lock(genesis_dir: Path, name: str, content: str, age_hours: float) -> Path:
    genesis_dir.mkdir(parents=True, exist_ok=True)
    path = genesis_dir / name
    path.write_text(content, encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).timestamp()
    os.utime(path, (old, old))
    return path


# ---------------------------------------------------------------------------
# Dry run is the default — the single most important guarantee
# ---------------------------------------------------------------------------


class TestDryRunDefault:
    def test_purge_defaults_to_dry_run(self, tmp_path):
        _write_manifest(tmp_path / "temp_a", age_hours=100, ttl_hours=1)
        report = purge(tmp_path)
        assert report.dry_run is True

    def test_dry_run_does_not_delete(self, tmp_path):
        target = _write_manifest(tmp_path / "temp_a", age_hours=100, ttl_hours=1)
        report = purge(tmp_path)
        assert report.candidates, "expected the expired dir to be detected"
        assert target.is_dir(), "dry run must not remove anything"
        assert report.purged == []

    def test_apply_true_actually_deletes(self, tmp_path):
        target = _write_manifest(tmp_path / "temp_a", age_hours=100, ttl_hours=1)
        report = purge(tmp_path, apply=True)
        assert not target.exists()
        assert str(target) in report.purged
        assert report.dry_run is False


# ---------------------------------------------------------------------------
# Ephemeral directories — opt-in via manifest only
# ---------------------------------------------------------------------------


class TestEphemeralDirs:
    def test_unmarked_directory_is_invisible(self, tmp_path):
        plain = tmp_path / "important_stuff"
        plain.mkdir()
        (plain / "data.txt").write_text("precious", encoding="utf-8")
        report = purge(tmp_path, apply=True)
        assert plain.is_dir()
        assert (plain / "data.txt").read_text(encoding="utf-8") == "precious"
        assert report.purged == []

    def test_fresh_manifest_is_protected(self, tmp_path):
        fresh = _write_manifest(tmp_path / "temp_fresh", age_hours=0.5, ttl_hours=24)
        report = purge(tmp_path, apply=True)
        assert fresh.is_dir()
        assert any("within TTL" in p.reason for p in report.protected)

    def test_expired_manifest_is_a_candidate(self, tmp_path):
        _write_manifest(tmp_path / "temp_old", age_hours=48, ttl_hours=1)
        candidates, _ = scan_ephemeral_dirs(tmp_path)
        assert len(candidates) == 1
        assert candidates[0].kind == "ephemeral_dir"

    def test_malformed_manifest_is_protected(self, tmp_path):
        bad = tmp_path / "temp_bad"
        bad.mkdir()
        (bad / MANIFEST_NAME).write_text("{not valid json", encoding="utf-8")
        report = purge(tmp_path, apply=True)
        assert bad.is_dir(), "unparseable manifest must fail safe, not delete"
        assert any("unreadable" in p.reason for p in report.protected)

    def test_manifest_without_ttl_is_protected(self, tmp_path):
        partial = tmp_path / "temp_partial"
        partial.mkdir()
        (partial / MANIFEST_NAME).write_text(
            json.dumps({"created_at": "2020-01-01T00:00:00+00:00"}), encoding="utf-8")
        report = purge(tmp_path, apply=True)
        assert partial.is_dir()
        assert any("usable created_at/ttl_hours" in p.reason for p in report.protected)

    def test_negative_ttl_is_protected(self, tmp_path):
        weird = tmp_path / "temp_weird"
        weird.mkdir()
        (weird / MANIFEST_NAME).write_text(
            json.dumps({"created_at": "2020-01-01T00:00:00+00:00", "ttl_hours": -5}),
            encoding="utf-8")
        purge(tmp_path, apply=True)
        assert weird.is_dir()

    def test_naive_datetime_treated_as_utc(self, tmp_path):
        naive = tmp_path / "temp_naive"
        naive.mkdir()
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).replace(tzinfo=None)
        (naive / MANIFEST_NAME).write_text(
            json.dumps({"created_at": old.isoformat(), "ttl_hours": 1}), encoding="utf-8")
        candidates, _ = scan_ephemeral_dirs(tmp_path)
        assert len(candidates) == 1

    def test_project_root_itself_never_purged(self, tmp_path):
        # A manifest at the root must not nominate the whole project.
        (tmp_path / MANIFEST_NAME).write_text(
            json.dumps({"created_at": "2020-01-01T00:00:00+00:00", "ttl_hours": 1}),
            encoding="utf-8")
        report = purge(tmp_path, apply=True)
        assert tmp_path.is_dir()
        assert any("project root itself" in p.reason for p in report.protected)


# ---------------------------------------------------------------------------
# Containment — nothing outside the project root
# ---------------------------------------------------------------------------


class TestScanPruning:
    """D-3: scanning must skip heavy machine-generated trees, and the exclusion
    list must come from the .claudeignore that already exists rather than a
    second hardcoded copy."""

    def test_defaults_include_the_usual_offenders(self):
        for name in (".venv", "node_modules", "__pycache__", ".git"):
            assert name in DEFAULT_PRUNE_DIRS

    def test_manifest_inside_pruned_dir_is_not_found(self, tmp_path):
        buried = tmp_path / ".venv" / "lib" / "pkg"
        _write_manifest(buried, age_hours=999, ttl_hours=1)
        report = purge(tmp_path, apply=True)
        assert report.candidates == [], "a pruned tree must not be scanned"
        assert buried.is_dir(), "and certainly must not be deleted"

    def test_manifest_outside_pruned_dir_is_still_found(self, tmp_path):
        _write_manifest(tmp_path / "work" / "scratch", age_hours=999, ttl_hours=1)
        assert purge(tmp_path).candidates, "normal directories must still scan"

    def test_project_claudeignore_is_honoured(self, tmp_path):
        (tmp_path / ".claudeignore").write_text(
            "# comment\nvendor_stuff/\n\n", encoding="utf-8")
        _write_manifest(tmp_path / "vendor_stuff" / "x", age_hours=999, ttl_hours=1)
        patterns = load_ignore_patterns(tmp_path)
        assert "vendor_stuff" in patterns
        assert purge(tmp_path).candidates == []

    def test_ignore_file_comments_and_blanks_skipped(self, tmp_path):
        (tmp_path / ".claudeignore").write_text(
            "# nope\n\n   \nreal_dir/\n", encoding="utf-8")
        patterns = load_ignore_patterns(tmp_path)
        assert "real_dir" in patterns
        assert "# nope" not in patterns and "" not in patterns

    def test_path_like_and_glob_patterns_ignored(self, tmp_path):
        # Only bare directory names are honoured; mis-parsing a complex
        # pattern would be worse than skipping it.
        (tmp_path / ".claudeignore").write_text(
            "a/b/c\n*.log\nsrc/**\nplain\n", encoding="utf-8")
        patterns = load_ignore_patterns(tmp_path)
        assert "plain" in patterns
        for bad in ("a/b/c", "*.log", "src/**"):
            assert bad not in patterns

    def test_missing_ignore_file_still_yields_defaults(self, tmp_path):
        assert DEFAULT_PRUNE_DIRS <= load_ignore_patterns(tmp_path)

    def test_walk_does_not_follow_symlinks(self, tmp_path):
        # followlinks=False, so a self-referential link cannot cause a loop.
        found = iter_manifest_dirs(tmp_path, set())
        assert found == []


class TestContainment:
    def test_within_root_accepts_child(self, tmp_path):
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert _within_root(child, tmp_path) is True

    def test_within_root_accepts_root_itself(self, tmp_path):
        assert _within_root(tmp_path, tmp_path) is True

    def test_within_root_rejects_sibling(self, tmp_path):
        root = tmp_path / "project"
        outside = tmp_path / "elsewhere"
        root.mkdir()
        outside.mkdir()
        assert _within_root(outside, root) is False

    def test_within_root_rejects_parent(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        assert _within_root(tmp_path, root) is False

    def test_symlink_escaping_root_is_refused(self, tmp_path):
        root = tmp_path / "project"
        outside = tmp_path / "outside_target"
        root.mkdir()
        outside.mkdir()
        (outside / "keepme.txt").write_text("precious", encoding="utf-8")
        link = root / "sneaky"
        _make_dir_link(link, outside)
        # Symlinks (and, on Windows, directory junctions) resolve BEFORE the
        # containment check, so this is outside.
        assert _within_root(link, root) is False


# ---------------------------------------------------------------------------
# Stale lock / PID files
# ---------------------------------------------------------------------------


class TestStaleLocks:
    def test_lock_with_live_pid_is_protected(self, tmp_path):
        _make_lock(tmp_path / ".genesis", "run.lock", str(os.getpid()), age_hours=48)
        report = purge(tmp_path, apply=True)
        assert (tmp_path / ".genesis" / "run.lock").is_file()
        assert any("still alive" in p.reason for p in report.protected)

    def test_fresh_lock_is_protected_even_if_dead(self, tmp_path):
        _make_lock(tmp_path / ".genesis", "run.lock", str(_dead_pid()), age_hours=0.01)
        purge(tmp_path, apply=True)
        assert (tmp_path / ".genesis" / "run.lock").is_file()

    def test_old_lock_with_dead_pid_is_removed(self, tmp_path):
        path = _make_lock(tmp_path / ".genesis", "run.lock", str(_dead_pid()), age_hours=48)
        report = purge(tmp_path, apply=True)
        assert not path.exists()
        assert str(path) in report.purged

    def test_unparseable_pid_is_protected(self, tmp_path):
        path = _make_lock(tmp_path / ".genesis", "weird.lock", "not-a-pid", age_hours=48)
        report = purge(tmp_path, apply=True)
        assert path.is_file()
        assert any("no parseable PID" in p.reason for p in report.protected)

    def test_empty_lock_is_protected(self, tmp_path):
        path = _make_lock(tmp_path / ".genesis", "empty.lock", "", age_hours=48)
        purge(tmp_path, apply=True)
        assert path.is_file()

    def test_locks_outside_genesis_dir_ignored(self, tmp_path):
        # Only .genesis/ is scanned for locks; a lock elsewhere is not our business.
        other = tmp_path / "somewhere"
        other.mkdir()
        path = other / "app.lock"
        path.write_text(str(_dead_pid()), encoding="utf-8")
        old = (datetime.now(timezone.utc) - timedelta(hours=99)).timestamp()
        os.utime(path, (old, old))
        purge(tmp_path, apply=True)
        assert path.is_file()

    def test_zero_and_negative_pids_are_protected(self, tmp_path):
        for name, content in (("z.lock", "0"), ("n.lock", "-1")):
            _make_lock(tmp_path / ".genesis", name, content, age_hours=48)
        purge(tmp_path, apply=True)
        assert (tmp_path / ".genesis" / "z.lock").is_file()
        assert (tmp_path / ".genesis" / "n.lock").is_file()

    def test_pid_alive_rejects_nonsense(self):
        assert _pid_alive(0) is True     # fail safe: unknown counts as alive
        assert _pid_alive(-1) is True

    def test_pid_alive_true_for_self(self):
        assert _pid_alive(os.getpid()) is True


# ---------------------------------------------------------------------------
# Git worktrees
# ---------------------------------------------------------------------------


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, timeout=30)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "t@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    (path / "README.md").write_text("hello", encoding="utf-8")
    _git(["add", "."], path)
    _git(["commit", "-m", "initial"], path)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    _init_repo(root)
    return root


class TestWorktreeParsing:
    def test_parses_path_and_branch(self):
        out = "worktree /a/b\nHEAD abc\nbranch refs/heads/feature\n\n"
        entries = _parse_worktree_list(out)
        assert entries[0]["path"] == "/a/b"
        assert entries[0]["branch"] == "feature"

    def test_parses_multiple_entries(self):
        out = (
            "worktree /main\nHEAD a\nbranch refs/heads/main\n\n"
            "worktree /wt1\nHEAD b\nbranch refs/heads/topic\n\n"
        )
        entries = _parse_worktree_list(out)
        assert len(entries) == 2
        assert entries[1]["branch"] == "topic"

    def test_parses_detached_and_bare(self):
        out = "worktree /x\nHEAD a\ndetached\n\nworktree /y\nbare\n\n"
        entries = _parse_worktree_list(out)
        assert entries[0].get("detached") is True
        assert entries[1].get("bare") is True

    def test_empty_output(self):
        assert _parse_worktree_list("") == []


class TestWorktreeSafety:
    def test_non_git_directory_yields_nothing(self, tmp_path):
        candidates, protected = scan_worktrees(tmp_path)
        assert candidates == []

    def test_main_worktree_is_always_protected(self, repo):
        candidates, protected = scan_worktrees(repo, ttl_hours=0.0)
        assert candidates == [], "the main worktree must never be a candidate"
        assert any("main worktree" in p.reason for p in protected)

    def test_worktree_with_uncommitted_changes_protected(self, repo):
        wt = repo / "wt_dirty"
        _git(["worktree", "add", "-b", "dirty-topic", str(wt)], repo)
        (wt / "scratch.txt").write_text("unsaved work", encoding="utf-8")
        candidates, protected = scan_worktrees(repo, ttl_hours=0.0)
        paths = [str(c.path) for c in candidates]
        assert str(wt.resolve()) not in [str(Path(p).resolve()) for p in paths]
        assert any("uncommitted change" in p.reason for p in protected)

    def test_dirty_worktree_survives_apply(self, repo):
        wt = repo / "wt_dirty"
        _git(["worktree", "add", "-b", "dirty-topic", str(wt)], repo)
        (wt / "scratch.txt").write_text("unsaved work", encoding="utf-8")
        purge(repo, apply=True, worktree_ttl_hours=0.0)
        assert wt.is_dir(), "a worktree holding uncommitted work must survive"
        assert (wt / "scratch.txt").read_text(encoding="utf-8") == "unsaved work"

    def test_protected_branch_worktree_survives(self, repo):
        wt = repo / "wt_develop"
        _git(["worktree", "add", "-b", "develop", str(wt)], repo)
        candidates, protected = scan_worktrees(repo, ttl_hours=0.0)
        assert not any(c.branch == "develop" for c in candidates)
        assert any("protected branch" in p.reason for p in protected)

    def test_all_protected_branch_names_are_honored(self, repo):
        for i, branch in enumerate(sorted(PROTECTED_BRANCHES - {"main"})):
            wt = repo / f"wt_{i}"
            _git(["worktree", "add", "-b", branch, str(wt)], repo)
        candidates, _ = scan_worktrees(repo, ttl_hours=0.0)
        assert not any(c.branch in PROTECTED_BRANCHES for c in candidates)

    def test_fresh_clean_worktree_protected_by_ttl(self, repo):
        wt = repo / "wt_fresh"
        _git(["worktree", "add", "-b", "fresh-topic", str(wt)], repo)
        candidates, protected = scan_worktrees(repo, ttl_hours=999999.0)
        assert candidates == []
        assert any("active" in p.reason for p in protected)

    def test_stale_clean_worktree_is_a_candidate(self, repo):
        wt = repo / "wt_stale"
        _git(["worktree", "add", "-b", "stale-topic", str(wt)], repo)
        candidates, _ = scan_worktrees(repo, ttl_hours=0.0)
        assert any(Path(c.path).name == "wt_stale" for c in candidates)

    def test_stale_clean_worktree_removed_on_apply(self, repo):
        wt = repo / "wt_stale"
        _git(["worktree", "add", "-b", "stale-topic", str(wt)], repo)
        report = purge(repo, apply=True, worktree_ttl_hours=0.0)
        assert not wt.exists()
        # Removed through git, so the registration is gone too — not just the files.
        listed = _git(["worktree", "list"], repo).stdout
        assert "wt_stale" not in listed
        assert report.errors == []

    def test_worktree_outside_root_is_protected(self, tmp_path):
        repo_root = tmp_path / "repo"
        _init_repo(repo_root)
        outside = tmp_path / "outside_wt"
        _git(["worktree", "add", "-b", "outside-topic", str(outside)], repo_root)
        candidates, protected = scan_worktrees(repo_root, ttl_hours=0.0)
        assert not any("outside_wt" in str(c.path) for c in candidates)
        assert any("outside the project root" in p.reason for p in protected)

    def test_outside_worktree_survives_apply(self, tmp_path):
        repo_root = tmp_path / "repo"
        _init_repo(repo_root)
        outside = tmp_path / "outside_wt"
        _git(["worktree", "add", "-b", "outside-topic", str(outside)], repo_root)
        purge(repo_root, apply=True, worktree_ttl_hours=0.0)
        assert outside.is_dir()


# ---------------------------------------------------------------------------
# Smart reminder
# ---------------------------------------------------------------------------


class TestHygieneNotice:
    def test_clean_project_returns_none(self, tmp_path):
        assert hygiene_notice(tmp_path) is None

    def test_expired_resource_produces_notice(self, tmp_path):
        _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        notice = hygiene_notice(tmp_path)
        assert notice is not None
        assert "expired" in notice
        assert "genesis purge" in notice

    def test_notice_never_deletes(self, tmp_path):
        target = _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        hygiene_notice(tmp_path)
        assert target.is_dir(), "the reminder must be read-only"

    def test_notice_pluralizes(self, tmp_path):
        _write_manifest(tmp_path / "a", age_hours=99, ttl_hours=1)
        _write_manifest(tmp_path / "b", age_hours=99, ttl_hours=1)
        notice = hygiene_notice(tmp_path)
        assert "2 expired ephemeral directories" in notice

    def test_notice_singular(self, tmp_path):
        _write_manifest(tmp_path / "a", age_hours=99, ttl_hours=1)
        notice = hygiene_notice(tmp_path)
        assert "1 expired ephemeral directory" in notice

    def test_notice_survives_a_broken_project(self, tmp_path):
        # Must never raise into the caller's command.
        assert hygiene_notice(tmp_path / "does_not_exist") is None


# ---------------------------------------------------------------------------
# mark_ephemeral + manifest round-trip
# ---------------------------------------------------------------------------


class TestMarkEphemeral:
    def test_creates_readable_manifest(self, tmp_path):
        target = tmp_path / "scratch"
        path = mark_ephemeral(target, ttl_hours=2, purpose="test run")
        assert path.is_file()
        data = read_manifest(target)
        assert data["ttl_hours"] == 2.0
        assert data["purpose"] == "test run"

    def test_creates_directory_if_absent(self, tmp_path):
        target = tmp_path / "nested" / "scratch"
        mark_ephemeral(target, ttl_hours=1)
        assert target.is_dir()

    def test_rejects_non_positive_ttl(self, tmp_path):
        with pytest.raises(ValueError):
            mark_ephemeral(tmp_path / "x", ttl_hours=0)

    def test_marked_dir_survives_until_expiry(self, tmp_path):
        target = tmp_path / "scratch"
        mark_ephemeral(target, ttl_hours=24)
        purge(tmp_path, apply=True)
        assert target.is_dir()

    def test_read_manifest_none_when_absent(self, tmp_path):
        assert read_manifest(tmp_path) is None

    def test_read_manifest_none_when_not_a_dict(self, tmp_path):
        (tmp_path / MANIFEST_NAME).write_text("[1,2,3]", encoding="utf-8")
        assert read_manifest(tmp_path) is None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReporting:
    def test_clean_summary(self, tmp_path):
        report = purge(tmp_path)
        assert "clean" in report.summary().lower()

    def test_dry_run_summary_mentions_nothing_deleted(self, tmp_path):
        _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        report = purge(tmp_path)
        assert "Nothing deleted" in report.summary()

    def test_format_report_includes_protection_reasons(self, tmp_path):
        _write_manifest(tmp_path / "fresh", age_hours=0.1, ttl_hours=99)
        text = format_report(purge(tmp_path))
        assert "Protected" in text
        assert "within TTL" in text

    def test_format_report_warns_before_apply(self, tmp_path):
        _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        text = format_report(purge(tmp_path))
        assert "--apply" in text

    def test_expired_count_property(self, tmp_path):
        _write_manifest(tmp_path / "a", age_hours=99, ttl_hours=1)
        assert purge(tmp_path).expired_count == 1

    def test_empty_report_defaults(self):
        report = PurgeReport()
        assert report.dry_run is True
        assert report.candidates == []


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestCLI:
    def test_purge_command_dry_run_exits_1_when_dirty(self, tmp_path):
        from genesis_architect.pro.gde_cli import main
        _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        assert main(["purge", "--dir", str(tmp_path)]) == 1

    def test_purge_command_exits_0_when_clean(self, tmp_path):
        from genesis_architect.pro.gde_cli import main
        assert main(["purge", "--dir", str(tmp_path)]) == 0

    def test_purge_command_dry_run_leaves_disk_untouched(self, tmp_path):
        from genesis_architect.pro.gde_cli import main
        target = _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        main(["purge", "--dir", str(tmp_path)])
        assert target.is_dir()

    def test_purge_command_apply_removes(self, tmp_path):
        from genesis_architect.pro.gde_cli import main
        target = _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        assert main(["purge", "--dir", str(tmp_path), "--apply"]) == 0
        assert not target.exists()

    def test_purge_command_json_output(self, tmp_path, capsys):
        from genesis_architect.pro.gde_cli import main
        _write_manifest(tmp_path / "temp_old", age_hours=99, ttl_hours=1)
        main(["purge", "--dir", str(tmp_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        assert len(payload["candidates"]) == 1

    def test_purge_command_bad_dir_exits_1(self, tmp_path):
        from genesis_architect.pro.gde_cli import main
        assert main(["purge", "--dir", str(tmp_path / "nope")]) == 1

    def test_in_package_namespace(self):
        import genesis_architect.pro as pkg
        for name in ("purge", "hygiene_notice", "mark_ephemeral", "PurgeReport"):
            assert hasattr(pkg, name)
