"""
git_analyzer: change coupling (G-HIGH-06), rename-aware paths, single-pass
last-touched and the opt-in log cache (G-MED-06).

Real git runs only in a temp repo; everything else uses fake commit dicts
shaped like _git_log() records.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _init_git_repo(root: Path, user: str = "Alice", email: str = "alice@test.com"):
    subprocess.run(["git", "init", str(root)], capture_output=True, check=False)
    subprocess.run(["git", "config", "user.email", email],
                   capture_output=True, check=False, cwd=str(root))
    subprocess.run(["git", "config", "user.name", user],
                   capture_output=True, check=False, cwd=str(root))


def _commit(root: Path, message: str, files: dict[str, str]):
    for fname, content in files.items():
        fpath = root / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
    subprocess.run(["git", "add", "-A"], capture_output=True, check=False, cwd=str(root))
    subprocess.run(["git", "commit", "-m", message],
                   capture_output=True, check=False, cwd=str(root))


def _fake(files: list[str], subject: str = "change") -> dict:
    return {"hash": "a" * 40, "author": "Alice", "date_iso": "2026-09-01T10:00:00+00:00",
            "committed_ts": 1788256800, "subject": subject, "files": files,
            "additions": 1, "deletions": 0}


# ---------------------------------------------------------------------------
# path normalization
# ---------------------------------------------------------------------------

class TestNormalizePath:
    @pytest.mark.parametrize("raw, expected", [
        ("src/app.py", "src/app.py"),
        ("src\\app.py", "src/app.py"),
        ("src/{a.py => b.py}", "src/b.py"),
        ("{old => new}/x.py", "new/x.py"),
        ("src/{ => sub}/x.py", "src/sub/x.py"),
        ("src/{sub => }/x.py", "src/x.py"),
        ("old.py => new.py", "new.py"),
    ])
    def test_renames_resolve_to_new_path(self, raw, expected):
        from genesis_architect_pro.git_analyzer import _normalize_path
        assert _normalize_path(raw) == expected

    def test_quoted_non_ascii_name_is_unquoted(self):
        from genesis_architect_pro.git_analyzer import _normalize_path
        # git prints "src/ש.py" as octal escapes of its UTF-8 bytes
        assert _normalize_path('"src/\\327\\251.py"') == "src/ש.py"

    def test_quoted_rename_is_unquoted_then_resolved(self):
        from genesis_architect_pro.git_analyzer import _normalize_path
        assert _normalize_path('"src/{a.py => \\327\\251.py}"') == "src/ש.py"


class TestRealGitRename:
    def test_renamed_file_is_counted_under_new_path(self, tmp_path):
        _init_git_repo(tmp_path)
        body = "".join(f"line_{i} = {i}\n" for i in range(30))
        _commit(tmp_path, "init", {"pkg/old_name.py": body})
        subprocess.run(["git", "mv", "pkg/old_name.py", "pkg/new_name.py"],
                       capture_output=True, check=False, cwd=str(tmp_path))
        _commit(tmp_path, "rename", {"pkg/new_name.py": body + "extra = 1\n"})

        from genesis_architect_pro.git_analyzer import _git_log, per_module_churn
        log = _git_log(tmp_path, days=90)
        all_files = [f for c in log for f in c["files"]]
        assert all(" => " not in f and "{" not in f for f in all_files), all_files
        assert "pkg/new_name.py" in all_files
        churn = per_module_churn(tmp_path, days=90)
        assert "pkg/new_name.py" in churn
        assert not any("=>" in k for k in churn)


# ---------------------------------------------------------------------------
# single-pass last_touched
# ---------------------------------------------------------------------------

class TestLastTouchedFromLog:
    def test_log_records_carry_committer_timestamp(self, tmp_path):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log
        log = _git_log(tmp_path, days=90)
        assert isinstance(log[0]["committed_ts"], int)
        assert log[0]["subject"] == "init"

    def test_subject_with_pipe_is_kept_whole(self, tmp_path):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "fix: a | b | c", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log
        assert _git_log(tmp_path, days=90)[0]["subject"] == "fix: a | b | c"

    def test_no_per_file_git_call(self, tmp_path, monkeypatch):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"a.py": "x = 1\n", "b.py": "y = 1\n", "c.py": "z = 1\n"})
        import genesis_architect_pro.git_analyzer as ga

        def _boom(*_a, **_k):
            raise AssertionError("_last_touched must not run when the log has timestamps")

        monkeypatch.setattr(ga, "_last_touched", _boom)
        churn = ga.per_module_churn(tmp_path, days=90)
        assert set(churn) == {"a.py", "b.py", "c.py"}
        assert all(v["last_touched_days"] == 0 for v in churn.values())


# ---------------------------------------------------------------------------
# opt-in log cache
# ---------------------------------------------------------------------------

class TestLogCache:
    def test_default_writes_nothing(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        before = {p for p in tmp_path.rglob("*") if ".git" not in p.parts}
        from genesis_architect_pro.git_analyzer import per_module_churn
        per_module_churn(repo, days=90)
        after = {p for p in tmp_path.rglob("*") if ".git" not in p.parts}
        assert after == before

    def test_second_call_is_served_from_cache(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log

        first = _git_log(repo, days=90, cache_dir=cache)
        files = list(cache.glob("gitlog-*.json"))
        assert len(files) == 1

        # Tamper with the cached copy: if the next call returns the tampered
        # subject, it read the cache instead of running git.
        data = json.loads(files[0].read_text(encoding="utf-8"))
        data["commits"][0]["subject"] = "FROM-CACHE"
        files[0].write_text(json.dumps(data), encoding="utf-8")

        second = _git_log(repo, days=90, cache_dir=cache)
        assert first[0]["subject"] == "init"
        assert second[0]["subject"] == "FROM-CACHE"

    def test_new_commit_invalidates_cache(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log
        assert len(_git_log(repo, days=90, cache_dir=cache)) == 1
        _commit(repo, "second", {"main.py": "x = 2\n"})
        assert len(_git_log(repo, days=90, cache_dir=cache)) == 2
        assert len(list(cache.glob("gitlog-*.json"))) == 2

    def test_corrupt_cache_falls_back_to_git(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log
        _git_log(repo, days=90, cache_dir=cache)
        cached = next(cache.glob("gitlog-*.json"))
        cached.write_text("{not json", encoding="utf-8")
        log = _git_log(repo, days=90, cache_dir=cache)
        assert log[0]["subject"] == "init"
        # and the bad file was replaced by a readable one
        assert json.loads(cached.read_text(encoding="utf-8"))["commits"][0]["subject"] == "init"

    def test_old_format_version_is_ignored(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        from genesis_architect_pro.git_analyzer import _git_log
        _git_log(repo, days=90, cache_dir=cache)
        cached = next(cache.glob("gitlog-*.json"))
        cached.write_text(json.dumps({"version": 1, "commits": [{"subject": "OLD"}]}),
                          encoding="utf-8")
        assert _git_log(repo, days=90, cache_dir=cache)[0]["subject"] == "init"

    def test_prune_keeps_at_most_sixteen(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        cache.mkdir()
        _init_git_repo(repo)
        _commit(repo, "init", {"main.py": "x = 1\n"})
        for i in range(20):
            stale = cache / f"gitlog-v2-{i:016x}-2026-01-01.json"
            stale.write_text("{}", encoding="utf-8")
            os.utime(stale, (1_000_000 + i, 1_000_000 + i))
        unrelated = cache / "keep-me.txt"
        unrelated.write_text("x", encoding="utf-8")
        from genesis_architect_pro.git_analyzer import _git_log
        _git_log(repo, days=90, cache_dir=cache)
        assert len(list(cache.glob("gitlog-*.json"))) == 16
        assert unrelated.exists()

    def test_repo_without_commits_does_not_crash(self, tmp_path):
        repo, cache = tmp_path / "repo", tmp_path / "cache"
        repo.mkdir()
        _init_git_repo(repo)
        from genesis_architect_pro.git_analyzer import _git_log
        assert _git_log(repo, days=90, cache_dir=cache) == []
        assert not cache.exists() or not list(cache.glob("gitlog-*.json"))


# ---------------------------------------------------------------------------
# change_coupling
# ---------------------------------------------------------------------------

class TestChangeCoupling:
    def test_empty_input(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        assert change_coupling([]) == []

    def test_always_together_scores_one(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        commits = [_fake(["a.py", "b.py"]) for _ in range(3)]
        pairs = change_coupling(commits)
        assert len(pairs) == 1
        p = pairs[0]
        assert (p.file_a, p.file_b, p.cochanges, p.confidence) == ("a.py", "b.py", 3, 1.0)

    def test_confidence_uses_the_busier_file(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        commits = [_fake(["a.py", "b.py"]), _fake(["a.py", "b.py"]),
                   _fake(["a.py"]), _fake(["a.py"])]
        p = change_coupling(commits)[0]
        assert (p.commits_a, p.commits_b) == (4, 2)
        assert p.confidence == 0.5

    def test_single_cochange_is_noise(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        assert change_coupling([_fake(["a.py", "b.py"])]) == []
        assert len(change_coupling([_fake(["a.py", "b.py"])], min_cochanges=1)) == 1

    def test_bulk_commit_is_excluded_entirely(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        bulk = _fake([f"f{i:02d}.py" for i in range(31)], subject="format everything")
        commits = [bulk, bulk, _fake(["f00.py", "f01.py"]), _fake(["f00.py", "f01.py"])]
        pairs = change_coupling(commits)
        assert len(pairs) == 1
        # the bulk commits did not inflate the per-file counts either
        assert (pairs[0].commits_a, pairs[0].commits_b, pairs[0].confidence) == (2, 2, 1.0)

    def test_order_is_deterministic_and_capped(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        commits = (
            [_fake(["x.py", "y.py"])] * 2                       # 1.0, 2 together
            + [_fake(["a.py", "b.py"])] * 5                     # 1.0, 5 together
            + [_fake(["m.py", "n.py"])] * 2 + [_fake(["m.py"])] * 2  # 0.5
        )
        pairs = change_coupling(commits)
        assert [(p.file_a, p.file_b) for p in pairs] == [
            ("a.py", "b.py"), ("x.py", "y.py"), ("m.py", "n.py")]
        assert len(change_coupling(commits, top_n=2)) == 2
        assert change_coupling(commits, top_n=0) == []

    def test_duplicate_and_backslash_paths_collapse(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        commits = [_fake(["src\\a.py", "src/a.py", "src/b.py"])] * 2
        pairs = change_coupling(commits)
        assert [(p.file_a, p.file_b, p.cochanges) for p in pairs] == [
            ("src/a.py", "src/b.py", 2)]

    def test_to_dict_is_json_serializable(self):
        from genesis_architect_pro.git_analyzer import change_coupling
        p = change_coupling([_fake(["a.py", "b.py"])] * 2)[0]
        d = json.loads(json.dumps(p.to_dict()))
        assert set(d) == {"file_a", "file_b", "cochanges", "commits_a", "commits_b",
                          "confidence"}

    def test_real_repo_end_to_end(self, tmp_path):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "init", {"schema.py": "v=1\n", "serializer.py": "v=1\n",
                                   "readme.md": "hi\n"})
        _commit(tmp_path, "field", {"schema.py": "v=2\n", "serializer.py": "v=2\n"})
        _commit(tmp_path, "field 2", {"schema.py": "v=3\n", "serializer.py": "v=3\n"})
        from genesis_architect_pro.git_analyzer import _git_log, change_coupling
        pairs = change_coupling(_git_log(tmp_path, days=90))
        assert pairs[0].file_a == "schema.py" and pairs[0].file_b == "serializer.py"
        assert pairs[0].cochanges == 3 and pairs[0].confidence == 1.0

    def test_cli_coupling_json(self, tmp_path, monkeypatch, capsys):
        _init_git_repo(tmp_path)
        _commit(tmp_path, "one", {"a.py": "1\n", "b.py": "1\n"})
        _commit(tmp_path, "two", {"a.py": "2\n", "b.py": "2\n"})
        from genesis_architect_pro import git_analyzer
        monkeypatch.setattr(sys, "argv", ["git_analyzer", str(tmp_path), "--coupling", "--json"])
        git_analyzer.main()
        out = json.loads(capsys.readouterr().out)
        assert out[0]["file_a"] == "a.py" and out[0]["cochanges"] == 2

    def test_lazy_exports(self):
        import genesis_architect_pro as pkg
        assert pkg.change_coupling is not None
        assert pkg.CoupledPair is not None
