"""Tests for vault.py and resolve_engine.py."""
import sys
import time
import json
import unittest.mock as mock
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core import vault, resolve_engine


class TestVault:
    def test_put_and_get(self, tmp_path):
        vault.put("key1", "solution text", "https://so.com/a/1", tmp_path)
        entry = vault.get("key1", tmp_path)
        assert entry is not None
        assert entry["solution"] == "solution text"
        assert entry["source_url"] == "https://so.com/a/1"

    def test_miss_returns_none(self, tmp_path):
        assert vault.get("nonexistent", tmp_path) is None

    def test_lru_eviction(self, tmp_path):
        # fill to MAX+1
        orig = vault._MAX_ENTRIES
        vault._MAX_ENTRIES = 3
        try:
            for i in range(4):
                time.sleep(0.01)
                vault.put(f"key{i}", f"sol{i}", f"https://so.com/{i}", tmp_path)
            data = json.loads((tmp_path / ".genesis" / "vault" / "index.json").read_text())
            assert len(data) == 3
        finally:
            vault._MAX_ENTRIES = orig

    def test_is_stale_fresh(self, tmp_path):
        vault.put("fresh", "sol", "url", tmp_path)
        entry = vault.get("fresh", tmp_path)
        assert not vault.is_stale(entry)

    def test_is_stale_old(self, tmp_path):
        vault.put("old", "sol", "url", tmp_path)
        path = tmp_path / ".genesis" / "vault" / "index.json"
        data = json.loads(path.read_text())
        data["old"]["created_at"] = time.time() - (vault._TTL_SECONDS + 1)
        path.write_text(json.dumps(data))
        entry = vault.get("old", tmp_path)
        assert vault.is_stale(entry)

    def test_stats(self, tmp_path):
        vault.put("a", "sol", "url", tmp_path)
        s = vault.stats(tmp_path)
        assert s["total"] == 1
        assert s["stale"] == 0

    def test_last_accessed_updated_on_get(self, tmp_path):
        vault.put("k", "s", "u", tmp_path)
        e1 = vault.get("k", tmp_path)
        time.sleep(0.05)
        e2 = vault.get("k", tmp_path)
        assert e2["last_accessed"] >= e1["last_accessed"]


class TestResolveEngine:
    def test_fresh_cache_no_api_call(self, tmp_path):
        vault.put("python timeout requests", "use timeout=5", "https://so.com/1", tmp_path)
        with mock.patch("genesis_architect.core.resolve_engine._fetch_from_so") as m:
            sol, url, stale = resolve_engine.resolve("python timeout requests", str(tmp_path))
        m.assert_not_called()
        assert sol == "use timeout=5"
        assert not stale

    def test_missing_calls_api(self, tmp_path):
        with mock.patch("genesis_architect.core.resolve_engine._fetch_from_so",
                        return_value={"solution": "fresh sol", "source_url": "https://so.com/2"}):
            sol, url, stale = resolve_engine.resolve("new query", str(tmp_path))
        assert sol == "fresh sol"
        assert not stale

    def test_stale_fallback_on_network_failure(self, tmp_path):
        vault.put("stale query", "old sol", "https://so.com/3", tmp_path)
        path = tmp_path / ".genesis" / "vault" / "index.json"
        data = json.loads(path.read_text())
        data["stale query"]["created_at"] = time.time() - (vault._TTL_SECONDS + 1)
        path.write_text(json.dumps(data))
        with mock.patch("genesis_architect.core.resolve_engine._fetch_from_so", return_value=None):
            sol, url, stale = resolve_engine.resolve("stale query", str(tmp_path))
        assert sol == "old sol"
        assert stale is True

    def test_stale_warning_in_output(self, tmp_path):
        vault.put("old q", "old", "url", tmp_path)
        path = tmp_path / ".genesis" / "vault" / "index.json"
        data = json.loads(path.read_text())
        data["old q"]["created_at"] = time.time() - (vault._TTL_SECONDS + 1)
        path.write_text(json.dumps(data))
        with mock.patch("genesis_architect.core.resolve_engine._fetch_from_so", return_value=None):
            out = resolve_engine.resolve_with_output("old q", str(tmp_path))
        assert "Warning" in out
        assert "6 months" in out

    def test_no_result_returns_empty(self, tmp_path):
        with mock.patch("genesis_architect.core.resolve_engine._fetch_from_so", return_value=None):
            sol, url, stale = resolve_engine.resolve("completely unknown xyz123", str(tmp_path))
        assert sol == ""

    def test_score_accepted_answer(self):
        answer = {"is_accepted": True, "score": 15, "creation_date": time.time() - 100, "body": "<code>x</code>"}
        score = resolve_engine._score_answer(answer)
        assert score == 110  # 50+30+20+10

    def test_score_old_answer(self):
        answer = {"is_accepted": False, "score": 2, "creation_date": time.time() - (3 * 365 * 86400), "body": "text"}
        score = resolve_engine._score_answer(answer)
        assert score == 0
