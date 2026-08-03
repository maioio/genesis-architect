"""Tests for genesis sync, the autonomous maintenance loop.

This module had no coverage at all, despite `genesis sync` being one of the
headline capabilities: GREEN applies automatically, YELLOW queues for a human,
RED blocks and demands review. Those three zones are a safety boundary, so the
rules that sort findings into them are worth pinning down precisely.
"""

import json

import pytest

from genesis_architect.pro.genesis_sync import (
    ZONE_GREEN,
    ZONE_RED,
    ZONE_YELLOW,
    SyncFinding,
    SyncReport,
    _classify_finding,
    _read_sync_config,
    _write_pending,
    _write_sync_log,
    run_sync,
)


def _zones(findings):
    return {f.zone for f in findings}


class TestZoneClassification:
    """The score thresholds are the documented contract: <55 red, <70 yellow."""

    def test_critical_score_is_red(self):
        findings = _classify_finding("architecture_scorer", {"score": 42.0})
        assert ZONE_RED in _zones(findings)
        assert any(f.severity == "critical" for f in findings)

    def test_mediocre_score_is_not_red(self):
        findings = _classify_finding("architecture_scorer", {"score": 61.0})
        assert ZONE_RED not in _zones(findings)

    def test_healthy_score_raises_nothing_severe(self):
        findings = _classify_finding("architecture_scorer", {"score": 95.0})
        assert ZONE_RED not in _zones(findings)

    @pytest.mark.parametrize("score,expect_red", [
        (54.9, True),
        (55.0, False),   # boundary: 55 is not below 55
    ])
    def test_red_boundary_is_exclusive(self, score, expect_red):
        findings = _classify_finding("architecture_scorer", {"score": score})
        assert (ZONE_RED in _zones(findings)) is expect_red

    def test_steep_decay_trend_is_yellow_not_red(self):
        """A declining trend warrants review, but must not block on its own."""
        findings = _classify_finding("architecture_scorer", {
            "score": 88.0,
            "decay_forecast": {"weekly_delta": -3.0, "predicted_score_12w": 52},
        })
        assert ZONE_YELLOW in _zones(findings)
        assert ZONE_RED not in _zones(findings)

    def test_gentle_decay_is_not_flagged(self):
        findings = _classify_finding("architecture_scorer", {
            "score": 88.0,
            "decay_forecast": {"weekly_delta": -0.2, "predicted_score_12w": 86},
        })
        assert ZONE_YELLOW not in _zones(findings)

    def test_unknown_engine_yields_no_findings(self):
        """An engine sync does not understand must stay silent, never guess."""
        assert _classify_finding("some_future_engine", {"anything": 1}) == []

    def test_empty_payload_does_not_raise(self):
        for engine in ("architecture_scorer", "antipattern_detector",
                       "rules_engine", "git_analyzer", "import_audit"):
            _classify_finding(engine, {})  # must not raise


class TestPendingQueue:
    def test_yellow_findings_are_written(self, tmp_path):
        f = SyncFinding(id="a1", zone=ZONE_YELLOW, engine="e",
                        title="t", detail="d", action="act", severity="warning")
        _write_pending(tmp_path, [f])
        data = json.loads((tmp_path / ".genesis" / "pending.json").read_text(encoding="utf-8"))
        assert [d["id"] for d in data] == ["a1"]

    def test_pending_is_deduplicated_across_runs(self, tmp_path):
        """sync runs on a schedule, so the same finding recurs every week. It
        must not pile up duplicates in the human review queue."""
        f = SyncFinding(id="same", zone=ZONE_YELLOW, engine="e",
                        title="t", detail="d", action="a", severity="warning")
        _write_pending(tmp_path, [f])
        _write_pending(tmp_path, [f])
        data = json.loads((tmp_path / ".genesis" / "pending.json").read_text(encoding="utf-8"))
        assert len(data) == 1

    def test_corrupt_pending_file_does_not_lose_the_new_finding(self, tmp_path):
        pending = tmp_path / ".genesis" / "pending.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("{ not json", encoding="utf-8")
        f = SyncFinding(id="new", zone=ZONE_YELLOW, engine="e",
                        title="t", detail="d", action="a", severity="warning")
        _write_pending(tmp_path, [f])
        data = json.loads(pending.read_text(encoding="utf-8"))
        assert [d["id"] for d in data] == ["new"]


def _report(**kw) -> SyncReport:
    base = dict(run_id="r1", project_dir=".", timestamp="2026-08-03T00:00:00Z",
                duration_seconds=0.1)
    base.update(kw)
    return SyncReport(**base)


class TestSyncLog:
    def test_log_is_append_only_jsonl(self, tmp_path):
        for i in range(3):
            _write_sync_log(tmp_path, _report(run_id=f"r{i}"))
        lines = (tmp_path / ".genesis" / "sync_log.jsonl").read_text(
            encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # each line must parse on its own


class TestConfig:
    def test_defaults_match_the_documented_thresholds(self, tmp_path):
        cfg = _read_sync_config(tmp_path)
        assert cfg["score_threshold_red"] == 55
        assert cfg["score_threshold_yellow"] == 70
        assert cfg["auto_apply_green"] is True

    def test_user_config_overrides_defaults_but_keeps_the_rest(self, tmp_path):
        cfgdir = tmp_path / ".genesis"
        cfgdir.mkdir(parents=True)
        (cfgdir / "sync_config.json").write_text(
            json.dumps({"score_threshold_red": 40}), encoding="utf-8")
        cfg = _read_sync_config(tmp_path)
        assert cfg["score_threshold_red"] == 40      # overridden
        assert cfg["score_threshold_yellow"] == 70   # default preserved

    def test_corrupt_config_falls_back_to_defaults(self, tmp_path):
        cfgdir = tmp_path / ".genesis"
        cfgdir.mkdir(parents=True)
        (cfgdir / "sync_config.json").write_text("nonsense{", encoding="utf-8")
        assert _read_sync_config(tmp_path)["score_threshold_red"] == 55


class TestRunSync:
    def test_dry_run_writes_nothing(self, tmp_path):
        """The documented promise is that sync never edits your source. In dry
        run it must not even write its own bookkeeping files."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")

        run_sync(tmp_path, dry_run=True, json_output=True)

        genesis_dir = tmp_path / ".genesis"
        for artifact in ("pending.json", "sync_log.jsonl"):
            assert not (genesis_dir / artifact).exists(), artifact

    def test_run_sync_never_touches_source_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        target = src / "app.py"
        original = "def f():\n    return 1\n"
        target.write_text(original, encoding="utf-8")

        run_sync(tmp_path, json_output=True)

        assert target.read_text(encoding="utf-8") == original

    def test_run_sync_returns_a_report(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("y = 2\n", encoding="utf-8")
        report = run_sync(tmp_path, json_output=True)
        assert isinstance(report, SyncReport)
        assert isinstance(report.as_dict(), dict)
