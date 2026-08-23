"""Tests for the Genesis State & Caching Engine (cache_engine.py).

Two things carry most of the weight, and are tested first and hardest:

**A cache hit only happens when the content genuinely hasn't changed.** The
hash is what makes that trustworthy, so the tests attack the boundary
directly - same path, changed bytes, must miss.

**A miss is always safe.** Missing DB, missing row, changed hash, corrupted
summary - every one of these degrades to "do the real work," never to a wrong
answer served with confidence.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from genesis_architect.core.cache_engine import (
    CacheEngine,
    CacheEngineError,
    ToolEntry,
    ValidationResult,
    db_path,
    hash_file,
    main,
)

KNOWN_SHA256 = {
    b"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    b"hello": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
}


# ---------------------------------------------------------------------------
# hash_file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_matches_a_known_sha256(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_bytes(b"hello")
        assert hash_file(f) == KNOWN_SHA256[b"hello"][:64]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert hash_file(f) == KNOWN_SHA256[b""][:64]

    def test_a_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            hash_file(tmp_path / "nope.txt")

    def test_a_large_file_streams_without_error(self, tmp_path):
        """Regression guard: chunked reading must not truncate or duplicate."""
        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * (3 * (1 << 20) + 7))  # > one chunk, not aligned
        import hashlib
        expected = hashlib.sha256(f.read_bytes()).hexdigest()
        assert hash_file(f, chunk_size=1 << 16) == expected


# ---------------------------------------------------------------------------
# db_path / schema
# ---------------------------------------------------------------------------


class TestSetup:
    def test_db_lives_under_dot_genesis(self, tmp_path):
        assert db_path(tmp_path) == tmp_path / ".genesis" / "cache.db"

    def test_opening_creates_the_directory_and_file(self, tmp_path):
        with CacheEngine(tmp_path):
            pass
        assert db_path(tmp_path).is_file()

    def test_opening_twice_does_not_corrupt_existing_data(self, tmp_path):
        with CacheEngine(tmp_path) as e1:
            e1.register_tool("curl", "library", "local")
        with CacheEngine(tmp_path) as e2:
            assert e2.get_tool("curl", "local") is not None

    def test_it_is_a_real_sqlite_file(self, tmp_path):
        """Not a JSON file with a misleading extension."""
        with CacheEngine(tmp_path):
            pass
        conn = sqlite3.connect(str(db_path(tmp_path)))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        conn.close()
        assert {"tool_catalog", "config_cache"} <= tables

    def test_context_manager_closes_the_connection(self, tmp_path):
        with CacheEngine(tmp_path) as engine:
            pass
        with pytest.raises(sqlite3.ProgrammingError):
            engine._conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------


class TestToolCatalog:
    def test_register_and_get(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("firecrawl", "mcp", "global", version="1.2.0",
                            performance_rating=4.5, notes="reliable for scraping")
            entry = e.get_tool("firecrawl", "global")
        assert entry == ToolEntry("firecrawl", "mcp", "global", "1.2.0", 4.5,
                                  "reliable for scraping", entry.updated_at)

    def test_an_unregistered_tool_returns_none(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            assert e.get_tool("nope", "local") is None

    def test_re_registering_updates_rather_than_duplicates(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("curl", "library", "local", version="8.0")
            e.register_tool("curl", "library", "local", version="8.1")
            entries = e.list_tools()
        assert len(entries) == 1
        assert entries[0].version == "8.1"

    def test_the_same_name_can_be_both_global_and_local(self, tmp_path):
        """(name, scope) is the identity, not name alone."""
        with CacheEngine(tmp_path) as e:
            e.register_tool("exa", "mcp", "global")
            e.register_tool("exa", "mcp", "local", notes="pinned for this repo")
            entries = e.list_tools()
        assert len(entries) == 2
        assert {t.scope for t in entries} == {"global", "local"}

    def test_list_filters_by_kind(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("exa", "mcp", "global")
            e.register_tool("dry-run-interview", "skill", "global")
            names = {t.name for t in e.list_tools(kind="skill")}
        assert names == {"dry-run-interview"}

    def test_list_filters_by_scope(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("a", "library", "global")
            e.register_tool("b", "library", "local")
            names = {t.name for t in e.list_tools(scope="local")}
        assert names == {"b"}

    def test_list_is_sorted_for_stable_output(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            for name in ("zeta", "alpha", "mid"):
                e.register_tool(name, "library", "global")
            names = [t.name for t in e.list_tools()]
        assert names == sorted(names)

    def test_remove_reports_whether_anything_was_removed(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("curl", "library", "local")
            assert e.remove_tool("curl", "local") is True
            assert e.remove_tool("curl", "local") is False

    def test_notes_default_to_empty_string_not_null(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("curl", "library", "local")
            entry = e.get_tool("curl", "local")
        assert entry.notes == ""

    @pytest.mark.parametrize("bad_kind", ["", "framework", "MCP", None])
    def test_an_invalid_kind_is_refused(self, tmp_path, bad_kind):
        with CacheEngine(tmp_path) as e, pytest.raises(ValueError):
            e.register_tool("x", bad_kind, "local")

    @pytest.mark.parametrize("bad_scope", ["", "project", "Local"])
    def test_an_invalid_scope_is_refused(self, tmp_path, bad_scope):
        with CacheEngine(tmp_path) as e, pytest.raises(ValueError):
            e.register_tool("x", "library", bad_scope)

    def test_an_empty_name_is_refused(self, tmp_path):
        with CacheEngine(tmp_path) as e, pytest.raises(ValueError):
            e.register_tool("   ", "library", "local")

    @pytest.mark.parametrize("bad_rating", [-0.1, 5.1, 100.0])
    def test_a_rating_outside_zero_to_five_is_refused(self, tmp_path, bad_rating):
        with CacheEngine(tmp_path) as e, pytest.raises(ValueError):
            e.register_tool("x", "library", "local", performance_rating=bad_rating)

    def test_no_rating_is_allowed_and_stays_none(self, tmp_path):
        """An un-measured tool is NULL, never a fabricated default score."""
        with CacheEngine(tmp_path) as e:
            e.register_tool("x", "library", "local")
            entry = e.get_tool("x", "local")
        assert entry.performance_rating is None

    def test_boundary_ratings_zero_and_five_are_accepted(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            e.register_tool("floor", "library", "local", performance_rating=0.0)
            e.register_tool("ceiling", "library", "local", performance_rating=5.0)
        # no exception is the assertion


# ---------------------------------------------------------------------------
# The hash-validate-store cycle
# ---------------------------------------------------------------------------


class TestValidate:
    def test_a_never_seen_file_is_a_miss(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            result = e.validate(f)
        assert result.hit is False and result.summary is None

    def test_the_miss_still_carries_the_computed_hash(self, tmp_path):
        """So a caller storing after a miss never has to hash twice."""
        f = tmp_path / "package.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            result = e.validate(f)
        assert result.content_hash == hash_file(f)

    def test_an_unchanged_file_after_store_is_a_hit(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("requests==2.31.0\n")
        with CacheEngine(tmp_path) as e:
            miss = e.validate(f)
            e.store(f, miss.content_hash, {"deps": ["requests"]})
            hit = e.validate(f)
        assert hit.hit is True
        assert hit.summary == {"deps": ["requests"]}

    def test_editing_the_file_invalidates_the_hit(self, tmp_path):
        """The one property the whole cache exists to guarantee."""
        f = tmp_path / "requirements.txt"
        f.write_text("requests==2.31.0\n")
        with CacheEngine(tmp_path) as e:
            miss = e.validate(f)
            e.store(f, miss.content_hash, {"deps": ["requests"]})
            f.write_text("requests==2.32.0\n")
            result = e.validate(f)
        assert result.hit is False, "a changed file was served a stale summary"

    def test_reverting_the_file_to_a_previously_cached_hash_is_a_hit_again(self, tmp_path):
        """The cache is keyed by hash, not by "most recent write." """
        f = tmp_path / "requirements.txt"
        f.write_text("v1\n")
        with CacheEngine(tmp_path) as e:
            m1 = e.validate(f)
            e.store(f, m1.content_hash, {"v": 1})
            f.write_text("v2\n")
            m2 = e.validate(f)
            e.store(f, m2.content_hash, {"v": 2})
            f.write_text("v1\n")
            back = e.validate(f)
        assert back.hit is True and back.summary == {"v": 1}

    def test_the_same_path_from_a_different_cwd_still_hits(self, tmp_path, monkeypatch):
        """Path normalisation: an absolute and a relative reference to the
        same file must not be treated as two different cache entries."""
        f = tmp_path / "sub" / "config.json"
        f.parent.mkdir()
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            miss = e.validate(f)
            e.store(f, miss.content_hash, {"ok": True})

            monkeypatch.chdir(f.parent)
            hit = e.validate("config.json")
        assert hit.hit is True

    def test_two_known_versions_of_a_path_can_coexist(self, tmp_path):
        """Both stay hit-able; storing v2 must not evict v1."""
        f = tmp_path / "requirements.txt"
        f.write_text("v1\n")
        with CacheEngine(tmp_path) as e:
            m1 = e.validate(f)
            e.store(f, m1.content_hash, {"v": 1})
            f.write_text("v2\n")
            m2 = e.validate(f)
            e.store(f, m2.content_hash, {"v": 2})

            f.write_text("v1\n")
            assert e.validate(f).summary == {"v": 1}
            f.write_text("v2\n")
            assert e.validate(f).summary == {"v": 2}

    def test_invalidate_removes_every_known_version_of_the_path(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("v1\n")
        with CacheEngine(tmp_path) as e:
            m1 = e.validate(f)
            e.store(f, m1.content_hash, {"v": 1})
            f.write_text("v2\n")
            m2 = e.validate(f)
            e.store(f, m2.content_hash, {"v": 2})

            e.invalidate(f)

            f.write_text("v1\n")
            assert e.validate(f).hit is False, "an old version survived invalidate"

    def test_a_missing_file_raises_rather_than_reporting_a_miss(self, tmp_path):
        """Distinct failure modes: "never analysed" is not "cannot be found"."""
        with CacheEngine(tmp_path) as e:
            with pytest.raises(FileNotFoundError):
                e.validate(tmp_path / "ghost.json")

    def test_invalidate_forces_the_next_check_to_miss(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            miss = e.validate(f)
            e.store(f, miss.content_hash, {"ok": True})
            assert e.invalidate(f) is True
            assert e.validate(f).hit is False

    def test_invalidating_something_never_cached_reports_false(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            assert e.invalidate(f) is False

    def test_store_overwrites_rather_than_duplicates(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            m = e.validate(f)
            e.store(f, m.content_hash, {"a": 1})
            e.store(f, m.content_hash, {"a": 2})
            assert e.stats()["files_cached"] == 1
            assert e.validate(f).summary == {"a": 2}

    def test_unicode_in_the_summary_survives(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            m = e.validate(f)
            e.store(f, m.content_hash, {"note": "בדיקה עברית"})
            assert e.validate(f).summary == {"note": "בדיקה עברית"}

    def test_a_corrupted_stored_summary_is_reported_not_silently_swallowed(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            h = hash_file(f)
            e._conn.execute(
                "INSERT INTO config_cache (path, content_hash, summary, updated_at) "
                "VALUES (?, ?, 'not json', 'x')",
                (str(f.resolve().as_posix()), h),
            )
            e._conn.commit()
            with pytest.raises(CacheEngineError):
                e.validate(f)


class TestValidationResultType:
    def test_is_a_plain_dataclass(self):
        r = ValidationResult(path="x", content_hash="h", hit=False)
        assert r.summary is None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_empty_engine(self, tmp_path):
        with CacheEngine(tmp_path) as e:
            s = e.stats()
        assert s["tools_catalogued"] == 0 and s["files_cached"] == 0

    def test_counts_reflect_both_tables_independently(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text("{}")
        with CacheEngine(tmp_path) as e:
            e.register_tool("a", "library", "local")
            e.register_tool("b", "library", "local")
            m = e.validate(f)
            e.store(f, m.content_hash, {})
            s = e.stats()
        assert s["tools_catalogued"] == 2 and s["files_cached"] == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def _invoke(self, monkeypatch, capsys, *argv):
        monkeypatch.setattr("sys.argv", ["cache_engine.py", *argv])
        code = main()
        return code, capsys.readouterr()

    def test_register_and_list_round_trip(self, tmp_path, monkeypatch, capsys):
        code, out = self._invoke(monkeypatch, capsys, "register-tool", str(tmp_path),
                                 "curl", "--kind", "library", "--scope", "local")
        assert code == 0 and json.loads(out.out)["name"] == "curl"

        code, out = self._invoke(monkeypatch, capsys, "list-tools", str(tmp_path))
        assert code == 0
        assert [t["name"] for t in json.loads(out.out)] == ["curl"]

    def test_validate_miss_exits_nonzero_and_prints_the_hash(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "x.json"
        f.write_text("{}")
        code, out = self._invoke(monkeypatch, capsys, "validate", str(tmp_path), str(f))
        assert code == 1
        payload = json.loads(out.out)
        assert payload["hit"] is False and payload["content_hash"] == hash_file(f)

    def test_store_then_validate_hits_via_the_cli(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "x.json"
        f.write_text("{}")
        h = hash_file(f)
        code, _ = self._invoke(monkeypatch, capsys, "store", str(tmp_path), str(f),
                               "--content-hash", h, "--summary", '{"ok": true}')
        assert code == 0

        code, out = self._invoke(monkeypatch, capsys, "validate", str(tmp_path), str(f))
        assert code == 0 and json.loads(out.out) == {"ok": True}

    def test_store_with_invalid_json_summary_fails_cleanly(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "x.json"
        f.write_text("{}")
        code, out = self._invoke(monkeypatch, capsys, "store", str(tmp_path), str(f),
                                 "--content-hash", "deadbeef", "--summary", "{not json")
        assert code == 1
        assert "not valid JSON" in out.err

    def test_remove_tool_missing_reports_failure(self, tmp_path, monkeypatch, capsys):
        code, out = self._invoke(monkeypatch, capsys, "remove-tool", str(tmp_path),
                                 "ghost", "--scope", "local")
        assert code == 1
        assert "ghost" in out.err

    def test_stats_via_cli(self, tmp_path, monkeypatch, capsys):
        code, out = self._invoke(monkeypatch, capsys, "stats", str(tmp_path))
        assert code == 0
        assert json.loads(out.out)["tools_catalogued"] == 0

    def test_an_invalid_kind_exits_via_argparse_not_a_traceback(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["cache_engine.py", "register-tool", str(tmp_path),
                                        "x", "--kind", "framework", "--scope", "local"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2  # argparse's own usage-error code
