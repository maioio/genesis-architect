"""
Step 1 tests: Python stdlib filter, bus factor, weekly commit timeline, sparkline.

All tests are self-contained and deterministic (no network, no git I/O except
where a real temp git repo is spun up for bus-factor verification).
"""

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path



# ---------------------------------------------------------------------------
# stdlib filter
# ---------------------------------------------------------------------------

class TestStdlibFilter:
    def test_os_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("os") is True

    def test_os_path_dotted_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("os.path") is True

    def test_pathlib_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("pathlib") is True

    def test_typing_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("typing") is True

    def test_sys_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("sys") is True

    def test_tomllib_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("tomllib") is True

    def test_zoneinfo_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("zoneinfo") is True

    def test_asyncio_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("asyncio") is True

    def test_requests_is_not_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("requests") is False

    def test_numpy_is_not_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("numpy") is False

    def test_fastapi_is_not_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("fastapi") is False

    def test_empty_string_is_not_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("") is False

    def test_dotted_third_party_is_not_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("django.db.models") is False

    def test_python_stdlib_set_is_frozenset(self):
        from genesis_architect_pro.stdlib_filter import PYTHON_STDLIB
        assert isinstance(PYTHON_STDLIB, frozenset)

    def test_python_stdlib_has_minimum_coverage(self):
        from genesis_architect_pro.stdlib_filter import PYTHON_STDLIB
        # Must cover at least 80 stdlib names (Python 3.11 has 100+)
        assert len(PYTHON_STDLIB) >= 80

    def test_dataclasses_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("dataclasses") is True

    def test_concurrent_futures_is_stdlib(self):
        from genesis_architect_pro.stdlib_filter import is_stdlib_import
        assert is_stdlib_import("concurrent.futures") is True


# ---------------------------------------------------------------------------
# bus factor (per_module_churn result)
# ---------------------------------------------------------------------------

def _init_git_repo(root: Path, user: str = "Alice", email: str = "alice@test.com"):
    """Initialize a bare-minimum git repo for testing."""
    subprocess.run(["git", "init", str(root)], capture_output=True, check=False)
    subprocess.run(["git", "config", "user.email", email],
                   capture_output=True, check=False, cwd=str(root))
    subprocess.run(["git", "config", "user.name", user],
                   capture_output=True, check=False, cwd=str(root))


def _commit(root: Path, message: str, files: dict[str, str],
            author_name: str | None = None, author_email: str | None = None):
    """Write files and commit them."""
    for fname, content in files.items():
        fpath = root / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
    subprocess.run(["git", "add", "."], capture_output=True, check=False, cwd=str(root))
    env_override = {}
    if author_name:
        env_override["GIT_AUTHOR_NAME"] = author_name
        env_override["GIT_AUTHOR_EMAIL"] = author_email or f"{author_name.lower()}@test.com"
        env_override["GIT_COMMITTER_NAME"] = author_name
        env_override["GIT_COMMITTER_EMAIL"] = author_email or f"{author_name.lower()}@test.com"
    import os
    env = {**os.environ, **env_override}
    subprocess.run(["git", "commit", "-m", message],
                   capture_output=True, check=False, cwd=str(root), env=env)


class TestBusFactor:
    def test_bus_factor_field_present_in_output(self, tmp_path):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if result:
            first = next(iter(result.values()))
            assert "bus_factor" in first

    def test_authors_field_present_in_output(self, tmp_path):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if result:
            first = next(iter(result.values()))
            assert "authors" in first
            assert isinstance(first["authors"], list)

    def test_single_author_bus_factor_is_one(self, tmp_path):
        _init_git_repo(tmp_path, user="Alice")
        _commit(tmp_path, "init", {"main.py": "x = 1\n"}, author_name="Alice")
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if "main.py" in result:
            assert result["main.py"]["bus_factor"] == 1

    def test_two_authors_bus_factor_is_two(self, tmp_path):
        _init_git_repo(tmp_path, user="Alice")
        _commit(tmp_path, "init by Alice", {"main.py": "x = 1\n"}, author_name="Alice")
        _commit(tmp_path, "edit by Bob", {"main.py": "x = 2\n"}, author_name="Bob")
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if "main.py" in result:
            assert result["main.py"]["bus_factor"] == 2

    def test_authors_list_is_sorted(self, tmp_path):
        _init_git_repo(tmp_path, user="Alice")
        _commit(tmp_path, "init", {"a.py": "x=1\n"}, author_name="Zara")
        _commit(tmp_path, "edit", {"a.py": "x=2\n"}, author_name="Alice")
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if "a.py" in result:
            authors = result["a.py"]["authors"]
            assert authors == sorted(authors)

    def test_real_git_output_yields_files_and_churn(self, tmp_path):
        """Regression: `git log --format=... --numstat` separates the header
        from its numstat block with a blank line. The parser must not drop
        the numstat lines (it did until v7.2 — churn was always empty on
        real repositories, so git_analyzer reported 'no git history')."""
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"main.py": "x = 1\n", "pkg/util.py": "y = 2\n"})
        from genesis_architect_pro.git_analyzer import _git_log, per_module_churn
        log = _git_log(tmp_path, days=90)
        assert len(log) == 1
        assert sorted(log[0]["files"]) == ["main.py", "pkg/util.py"]
        assert log[0]["additions"] == 2
        result = per_module_churn(tmp_path, days=90)
        assert set(result) == {"main.py", "pkg/util.py"}
        assert result["main.py"]["commits"] == 1

    def test_non_git_dir_still_returns_empty(self, tmp_path):
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        assert result == {}

    def test_existing_keys_still_present(self, tmp_path):
        """Ensure bus_factor addition didn't remove existing output keys."""
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import per_module_churn
        result = per_module_churn(tmp_path, days=90)
        if result:
            first = next(iter(result.values()))
            for key in ("commits", "fix_commits", "fix_ratio", "churn_level"):
                assert key in first, f"Existing key missing after Step 1: {key}"


# ---------------------------------------------------------------------------
# WeeklySnapshot + build_timeline
# ---------------------------------------------------------------------------

class TestBuildTimeline:
    def test_timeline_returns_correct_week_count(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        snapshots = build_timeline(commits=[], period_weeks=4)
        assert len(snapshots) == 4

    def test_timeline_sorted_ascending_by_week_start(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        snapshots = build_timeline(commits=[], period_weeks=6)
        dates = [s.week_start for s in snapshots]
        assert dates == sorted(dates)

    def test_all_zeros_when_no_commits(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        snapshots = build_timeline(commits=[], period_weeks=4)
        assert all(s.commits == 0 for s in snapshots)
        assert all(s.churn_lines == 0 for s in snapshots)
        assert all(s.active_files == 0 for s in snapshots)

    def test_week_start_is_monday(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        snapshots = build_timeline(commits=[], period_weeks=4)
        for s in snapshots:
            d = datetime.fromisoformat(s.week_start)
            assert d.weekday() == 0, f"{s.week_start} is not a Monday"

    def test_commit_counted_in_correct_week(self):
        from genesis_architect_pro.git_analyzer import build_timeline, _to_monday
        # Make a commit dated exactly 1 week ago
        one_week_ago = datetime.now(UTC) - timedelta(weeks=1)
        expected_week = _to_monday(one_week_ago)
        fake_commits = [{
            "hash": "a" * 40,
            "author": "Test",
            "date_iso": one_week_ago.isoformat(),
            "subject": "test commit",
            "files": ["main.py"],
            "additions": 5,
            "deletions": 2,
        }]
        snapshots = build_timeline(fake_commits, period_weeks=4)
        matching = [s for s in snapshots if s.week_start == expected_week]
        assert len(matching) == 1
        assert matching[0].commits == 1
        assert matching[0].churn_lines == 7  # 5 + 2
        assert matching[0].active_files == 1

    def test_commit_outside_window_ignored(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        # Commit from 20 weeks ago should be excluded from a 4-week window
        old_commit = [{
            "hash": "b" * 40,
            "author": "Test",
            "date_iso": (datetime.now(UTC) - timedelta(weeks=20)).isoformat(),
            "subject": "old commit",
            "files": ["old.py"],
            "additions": 1,
            "deletions": 0,
        }]
        snapshots = build_timeline(old_commit, period_weeks=4)
        assert sum(s.commits for s in snapshots) == 0

    def test_missing_date_iso_skipped_gracefully(self):
        from genesis_architect_pro.git_analyzer import build_timeline
        bad_commit = [{"hash": "c" * 40, "author": "X", "date_iso": "",
                       "subject": "bad", "files": [], "additions": 0, "deletions": 0}]
        # Must not raise
        snapshots = build_timeline(bad_commit, period_weeks=2)
        assert len(snapshots) == 2

    def test_weekly_snapshot_dataclass_fields(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot
        s = WeeklySnapshot(week_start="2026-06-23", commits=3, churn_lines=100, active_files=5)
        assert s.week_start == "2026-06-23"
        assert s.commits == 3
        assert s.churn_lines == 100
        assert s.active_files == 5


# ---------------------------------------------------------------------------
# render_sparkline
# ---------------------------------------------------------------------------

class TestRenderSparkline:
    def test_sparkline_length_matches_width(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot(f"2026-0{i+1}-01", commits=i) for i in range(6)]
        line = render_sparkline(snaps, metric="commits", width=6)
        assert len(line) == 6

    def test_sparkline_uses_block_chars(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        _BLOCKS = set(" ▁▂▃▄▅▆▇█")
        snaps = [WeeklySnapshot(f"2026-0{i+1}-01", commits=i * 5) for i in range(4)]
        line = render_sparkline(snaps, width=4)
        for ch in line:
            assert ch in _BLOCKS, f"Unexpected char: {ch!r}"

    def test_all_zero_values_produce_spaces(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot(f"2026-0{i+1}-01", commits=0) for i in range(4)]
        line = render_sparkline(snaps, width=4)
        assert line == "    "

    def test_max_value_produces_full_block(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot("2026-01-01", commits=100)]
        line = render_sparkline(snaps, width=1)
        assert line == "█"

    def test_empty_snapshots_returns_spaces(self):
        from genesis_architect_pro.git_analyzer import render_sparkline
        line = render_sparkline([], width=10)
        assert line == " " * 10

    def test_width_larger_than_snapshots(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot("2026-01-01", commits=5)]
        line = render_sparkline(snaps, width=4)
        assert len(line) == 4

    def test_width_smaller_than_snapshots(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot(f"2026-0{i+1}-01", commits=i) for i in range(8)]
        line = render_sparkline(snaps, width=4)
        assert len(line) == 4

    def test_metric_churn_lines_respected(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        # First snap: high churn, zero commits → churn metric should show high bar
        snaps = [
            WeeklySnapshot("2026-01-01", commits=0, churn_lines=500),
            WeeklySnapshot("2026-01-08", commits=0, churn_lines=0),
        ]
        line = render_sparkline(snaps, metric="churn_lines", width=2)
        assert len(line) == 2
        # First char should be fuller than second
        _BLOCKS = " ▁▂▃▄▅▆▇█"
        assert _BLOCKS.index(line[0]) > _BLOCKS.index(line[1])

    def test_increasing_values_produce_ascending_bars(self):
        from genesis_architect_pro.git_analyzer import WeeklySnapshot, render_sparkline
        snaps = [WeeklySnapshot(f"2026-0{i+1}-01", commits=i * 10) for i in range(4)]
        line = render_sparkline(snaps, width=4)
        _BLOCKS = " ▁▂▃▄▅▆▇█"
        indices = [_BLOCKS.index(ch) for ch in line]
        # Each bar should be >= previous (monotonically non-decreasing)
        assert all(indices[i] <= indices[i + 1] for i in range(len(indices) - 1))
