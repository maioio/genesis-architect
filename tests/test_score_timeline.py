"""
score_timeline (G-MED-03): read-only timeline and ASCII sparkline over
.genesis/score_history.jsonl, with every skipped line or record reported.
"""

import json
import sys
from pathlib import Path

import pytest

from genesis_architect_pro.architecture_scorer import (
    append_score_history,
    load_score_history,
)
from genesis_architect_pro.score_timeline import (
    DEFAULT_LAST,
    HISTORY_RELPATH,
    METRICS,
    RAMP,
    Point,
    build_timeline,
    format_report,
    main,
    metric_value,
    read_history,
    render_ascii_sparkline,
    score_timeline,
)


def _rec(total, day=1, **dims):
    record = {"timestamp": f"2026-09-{day:02d}T10:00:00+00:00", "total": total}
    record.update(dims)
    return record


def _write(root: Path, lines) -> Path:
    path = root / HISTORY_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(
        (line if isinstance(line, bytes) else line.encode("utf-8")) + b"\n"
        for line in lines
    )
    path.write_bytes(data)
    return path


def _history(root: Path, totals):
    return _write(root, [json.dumps(_rec(t, day=i + 1)) for i, t in enumerate(totals)])


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["score_timeline", *argv])
    with pytest.raises(SystemExit) as exc:
        main()
    return exc.value.code


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------

class TestSparkline:
    def test_ramp_is_ascii_and_low_to_high(self):
        assert RAMP.isascii()
        assert RAMP[0] == "_" and RAMP[-1] == "@"
        assert len(set(RAMP)) == len(RAMP)

    def test_endpoints_map_to_first_and_last_character(self):
        assert render_ascii_sparkline([0, 100]) == "_@"

    def test_midpoint(self):
        assert render_ascii_sparkline([0, 50, 100]) == "_+@"

    def test_half_steps_round_up(self):
        # 2.5 of 7 steps: half-up gives index 3 ('='), banker's would give 2 ('-')
        assert render_ascii_sparkline([0, 2.5, 7]) == "_=@"

    def test_one_character_per_value(self):
        assert len(render_ascii_sparkline([float(i) for i in range(37)])) == 37

    def test_flat_series_draws_the_middle_character(self):
        assert render_ascii_sparkline([70, 70, 70]) == "==="

    def test_explicit_range(self):
        assert render_ascii_sparkline([50], lo=0, hi=100) == "+"

    def test_values_outside_the_range_are_clamped(self):
        assert render_ascii_sparkline([-5, 150], lo=0, hi=100) == "_@"

    def test_equal_explicit_bounds_draw_the_middle(self):
        assert render_ascii_sparkline([10, 90], lo=40, hi=40) == "=="

    def test_empty(self):
        assert render_ascii_sparkline([]) == ""

    def test_custom_ramp(self):
        assert render_ascii_sparkline([0, 1], ramp="ab") == "ab"

    def test_ramp_too_short(self):
        with pytest.raises(ValueError, match="at least two"):
            render_ascii_sparkline([1, 2], ramp="x")

    def test_inverted_range(self):
        with pytest.raises(ValueError, match="above"):
            render_ascii_sparkline([1], lo=10, hi=5)


# ---------------------------------------------------------------------------
# metric_value
# ---------------------------------------------------------------------------

class TestMetricValue:
    @pytest.mark.parametrize("value, expected", [(72, 72.0), (61.5, 61.5), (0, 0.0)])
    def test_numbers(self, value, expected):
        assert metric_value({"total": value}, "total") == expected

    @pytest.mark.parametrize("value", [
        None, True, False, "72", [72], {"v": 72}, float("nan"), float("inf"), float("-inf"),
    ])
    def test_unusable_values(self, value):
        assert metric_value({"total": value}, "total") is None

    def test_absent(self):
        assert metric_value({}, "total") is None


# ---------------------------------------------------------------------------
# build_timeline
# ---------------------------------------------------------------------------

class TestBuildTimeline:
    def test_summary_numbers(self):
        t = build_timeline([_rec(60, 1), _rec(65, 2), _rec(72, 3)])
        assert (t.first, t.last, t.change, t.low, t.high) == (60, 72, 12, 60, 72)
        assert t.sparkline == "_=@"
        assert (t.scale_low, t.scale_high) == (60, 72)
        assert (t.since, t.until) == ("2026-09-01", "2026-09-03")
        assert (t.available, t.records_total, t.records_skipped) == (3, 3, 0)
        assert t.warnings == []

    def test_low_and_high_are_not_first_and_last(self):
        t = build_timeline([_rec(70, 1), _rec(50, 2), _rec(90, 3), _rec(75, 4)])
        assert (t.first, t.last, t.low, t.high, t.change) == (70, 75, 50, 90, 5)

    def test_last_keeps_the_most_recent(self):
        t = build_timeline([_rec(60, 1), _rec(65, 2), _rec(72, 3)], last=2)
        assert [p.value for p in t.points] == [65, 72]
        assert t.available == 3
        assert t.sparkline == "_@"
        assert t.change == 7
        assert t.since == "2026-09-02"

    def test_last_larger_than_history(self):
        t = build_timeline([_rec(60), _rec(65)], last=10)
        assert len(t.points) == 2

    def test_last_none_keeps_everything(self):
        records = [_rec(50 + i % 30) for i in range(DEFAULT_LAST + 15)]
        assert len(build_timeline(records, last=None).points) == DEFAULT_LAST + 15
        assert len(build_timeline(records).points) == DEFAULT_LAST

    def test_negative_change(self):
        t = build_timeline([_rec(80), _rec(70)])
        assert t.change == -10

    def test_change_is_rounded(self):
        t = build_timeline([_rec(61.1), _rec(74.3)])
        assert t.change == 13.2

    def test_unusable_records_are_skipped_and_reported(self):
        records = [
            _rec(60, 1),
            {"timestamp": "2026-09-02T00:00:00+00:00"},
            _rec(True, 3),
            _rec("70", 4),
            _rec(float("nan"), 5),
            _rec(80, 6),
        ]
        t = build_timeline(records)
        assert [p.value for p in t.points] == [60, 80]
        assert [p.ordinal for p in t.points] == [1, 6]
        assert (t.records_total, t.records_skipped, t.available) == (6, 4, 2)
        assert "4 record(s) have no numeric 'total' value and were skipped." in t.warnings

    def test_malformed_lines_are_reported(self):
        t = build_timeline([_rec(60), _rec(70)], lines_malformed=3)
        assert t.lines_malformed == 3
        assert any(w.startswith("3 line(s) in .genesis/score_history.jsonl") for w in t.warnings)

    def test_single_point_has_no_trend(self):
        t = build_timeline([_rec(66)])
        assert t.change is None
        assert (t.first, t.last) == (66, 66)
        assert t.sparkline == "="
        assert any("no trend to show yet" in w for w in t.warnings)

    def test_no_usable_points(self):
        t = build_timeline([{"timestamp": "x"}])
        assert t.points == [] and t.sparkline == ""
        assert (t.first, t.last, t.change, t.low, t.high) == (None,) * 5
        assert (t.scale_low, t.scale_high, t.since, t.until) == (None,) * 4
        assert t.records_skipped == 1

    def test_empty_records(self):
        t = build_timeline([])
        assert t.points == [] and t.warnings == []

    @pytest.mark.parametrize("metric", [m for m in METRICS if m != "total"])
    def test_dimension_metrics(self, metric):
        records = [_rec(70, 1, **{metric: 40.5}), _rec(71, 2, **{metric: 55.5})]
        t = build_timeline(records, metric=metric)
        assert (t.metric, t.first, t.last, t.change) == (metric, 40.5, 55.5, 15.0)

    def test_fixed_scale_spans_0_to_100(self):
        t = build_timeline([_rec(50), _rec(50)], scale="fixed")
        assert (t.scale_low, t.scale_high) == (0.0, 100.0)
        assert t.sparkline == "++"

    def test_auto_scale_flat_series(self):
        assert build_timeline([_rec(50), _rec(50)]).sparkline == "=="

    def test_fixed_scale_extremes(self):
        assert build_timeline([_rec(0), _rec(100)], scale="fixed").sparkline == "_@"

    def test_timestamps_missing_or_unparseable(self):
        records = [{"total": 60}, {"timestamp": 12345, "total": 61}, {"timestamp": "soon", "total": 62}]
        t = build_timeline(records)
        assert [p.timestamp for p in t.points] == ["", "", "soon"]
        assert (t.since, t.until) == (None, None)

    def test_file_order_is_kept(self):
        t = build_timeline([_rec(60, 9), _rec(70, 1)])
        assert [p.value for p in t.points] == [60, 70]
        assert (t.since, t.until) == ("2026-09-09", "2026-09-01")

    @pytest.mark.parametrize("kwargs, match", [
        ({"metric": "speed"}, "Unknown metric"),
        ({"scale": "log"}, "Unknown scale"),
        ({"last": 0}, "positive integer"),
        ({"last": -3}, "positive integer"),
        ({"last": True}, "positive integer"),
        ({"last": 2.5}, "positive integer"),
    ])
    def test_invalid_arguments(self, kwargs, match):
        with pytest.raises(ValueError, match=match):
            build_timeline([_rec(60)], **kwargs)

    def test_to_dict(self):
        d = build_timeline([_rec(60, 1), _rec(72, 2)]).to_dict()
        assert d["points"] == [
            {"ordinal": 1, "timestamp": "2026-09-01T10:00:00+00:00", "value": 60.0},
            {"ordinal": 2, "timestamp": "2026-09-02T10:00:00+00:00", "value": 72.0},
        ]
        assert d["change"] == 12 and d["sparkline"] == "_@" and d["metric"] == "total"
        json.dumps(d)  # serialisable

    def test_point_to_dict(self):
        assert Point(3, "t", 1.5).to_dict() == {"ordinal": 3, "timestamp": "t", "value": 1.5}


# ---------------------------------------------------------------------------
# read_history
# ---------------------------------------------------------------------------

class TestReadHistory:
    def test_not_a_directory(self, tmp_path):
        with pytest.raises(ValueError, match="Not a directory"):
            read_history(tmp_path / "nope")

    def test_missing_file_creates_nothing(self, tmp_path):
        assert read_history(tmp_path) == ([], 0)
        assert not (tmp_path / ".genesis").exists()

    def test_mixed_lines(self, tmp_path):
        _write(tmp_path, [
            json.dumps(_rec(60, 1)),
            "",
            "   ",
            "not json",
            "[1, 2]",
            "42",
            b"\xff\xfe{\"total\": 1}",
            "﻿" + json.dumps(_rec(70, 2)),
            json.dumps(_rec(80, 3)),
        ])
        records, malformed = read_history(tmp_path)
        assert [r["total"] for r in records] == [60, 70, 80]
        assert malformed == 4

    def test_crlf_line_endings(self, tmp_path):
        path = tmp_path / HISTORY_RELPATH
        path.parent.mkdir()
        path.write_bytes(
            (json.dumps(_rec(60)) + "\r\n" + json.dumps(_rec(61)) + "\r\n").encode("utf-8")
        )
        records, malformed = read_history(tmp_path)
        assert [r["total"] for r in records] == [60, 61] and malformed == 0

    def test_file_is_not_modified(self, tmp_path):
        path = _write(tmp_path, [json.dumps(_rec(60)), "junk"])
        before = path.read_bytes()
        read_history(tmp_path)
        score_timeline(tmp_path)
        assert path.read_bytes() == before
        assert sorted(p.name for p in (tmp_path / ".genesis").iterdir()) == ["score_history.jsonl"]

    def test_matches_load_score_history_on_valid_files(self, tmp_path):
        _history(tmp_path, [60, 65, 72])
        assert read_history(tmp_path)[0] == load_score_history(tmp_path)

    def test_reads_what_append_score_history_writes(self, tmp_path):
        for i, total in enumerate([58, 63, 71]):
            append_score_history(tmp_path, {
                "timestamp": f"2026-09-2{i}T08:00:00+00:00", "total": total,
                "modularity": 70.0 + i, "coupling": 60.5, "cohesion": 55.0,
                "layering": 90.0, "profile": "library", "cycle_count": 0,
                "module_count": 12,
            })
        t = score_timeline(tmp_path)
        assert [p.value for p in t.points] == [58, 63, 71]
        assert (t.since, t.until, t.change) == ("2026-09-20", "2026-09-22", 13)
        assert score_timeline(tmp_path, metric="modularity").change == 2
        assert t.warnings == []

    def test_unreadable_file(self, tmp_path, monkeypatch):
        _history(tmp_path, [60])

        def boom(_self):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_bytes", boom)
        with pytest.raises(ValueError, match="Cannot read"):
            read_history(tmp_path)


# ---------------------------------------------------------------------------
# score_timeline
# ---------------------------------------------------------------------------

class TestScoreTimeline:
    def test_missing_history_warns(self, tmp_path):
        t = score_timeline(tmp_path)
        assert t.points == []
        assert t.warnings[0].startswith(
            "No score history yet: .genesis/score_history.jsonl does not exist."
        )
        assert "GDE architecture-scorer" in t.warnings[0]

    def test_empty_history_warns(self, tmp_path):
        _write(tmp_path, [])
        assert "is empty" in score_timeline(tmp_path).warnings[0]

    def test_only_malformed_lines(self, tmp_path):
        _write(tmp_path, ["junk", "{"])
        t = score_timeline(tmp_path)
        assert t.lines_malformed == 2
        assert not any(w.startswith("No score history") for w in t.warnings)
        assert any(w.startswith("2 line(s)") for w in t.warnings)

    def test_passes_options_through(self, tmp_path):
        _history(tmp_path, [10, 20, 30, 40])
        t = score_timeline(tmp_path, last=2, scale="fixed")
        assert [p.value for p in t.points] == [30, 40]
        assert t.scale == "fixed" and t.scale_high == 100.0

    def test_not_a_directory(self, tmp_path):
        with pytest.raises(ValueError, match="Not a directory"):
            score_timeline(tmp_path / "missing")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestFormat:
    def test_full_report(self):
        report = format_report(build_timeline([_rec(60, 1), _rec(65, 2), _rec(72, 3)]))
        assert report.splitlines() == [
            "Score timeline: total  (3 of 3 records, 2026-09-01 -> 2026-09-03)",
            "  _=@",
            "  scale: '_' = 60 ... '@' = 72 (auto)",
            "  first 60  last 72  change +12  low 60  high 72",
        ]

    def test_truncated_report_counts(self):
        report = format_report(build_timeline([_rec(v) for v in (60, 61, 62)], last=2))
        assert "(2 of 3 records," in report

    def test_negative_zero_and_fractional_change(self):
        assert "change -10" in format_report(build_timeline([_rec(80), _rec(70)]))
        assert "change 0 " in format_report(build_timeline([_rec(70), _rec(70)]))
        assert "change +13.2" in format_report(build_timeline([_rec(61.1), _rec(74.3)]))

    def test_single_point_says_n_a(self):
        report = format_report(build_timeline([_rec(66)]))
        assert "change n/a" in report
        assert "WARNING: Only one record carries 'total'" in report

    def test_unknown_dates(self):
        report = format_report(build_timeline([{"total": 60}, {"total": 70}]))
        assert "? -> ?" in report

    def test_no_points(self, tmp_path):
        report = format_report(score_timeline(tmp_path))
        lines = report.splitlines()
        assert lines[0] == "Score timeline: total  (no records to plot)"
        assert lines[1].startswith("  WARNING: No score history yet")

    def test_fixed_scale_label(self):
        report = format_report(build_timeline([_rec(60), _rec(70)], scale="fixed"))
        assert "scale: '_' = 0 ... '@' = 100 (fixed)" in report

    def test_report_is_ascii(self, tmp_path):
        _write(tmp_path, [json.dumps({"timestamp": "2026-09-01", "total": 60, "profile": "café"}),
                          "junk"])
        assert format_report(score_timeline(tmp_path)).isascii()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_text_output(self, tmp_path, monkeypatch, capsys):
        _history(tmp_path, [60, 65, 72])
        assert _run(monkeypatch, str(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "Score timeline: total" in out and "  _=@" in out

    def test_json_output(self, tmp_path, monkeypatch, capsys):
        _history(tmp_path, [60, 65, 72])
        assert _run(monkeypatch, str(tmp_path), "--json", "--metric", "total") == 0
        data = json.loads(capsys.readouterr().out)
        assert data["sparkline"] == "_=@" and data["change"] == 12

    def test_last_and_scale(self, tmp_path, monkeypatch, capsys):
        _history(tmp_path, [10, 20, 30, 40])
        assert _run(monkeypatch, str(tmp_path), "--last", "2", "--scale", "fixed", "--json") == 0
        data = json.loads(capsys.readouterr().out)
        assert [p["value"] for p in data["points"]] == [30, 40]
        assert data["scale"] == "fixed"

    def test_last_zero_shows_all(self, tmp_path, monkeypatch, capsys):
        _history(tmp_path, [50 + i % 20 for i in range(DEFAULT_LAST + 5)])
        assert _run(monkeypatch, str(tmp_path), "--last", "0", "--json") == 0
        assert len(json.loads(capsys.readouterr().out)["points"]) == DEFAULT_LAST + 5

    def test_no_history_exits_1(self, tmp_path, monkeypatch, capsys):
        assert _run(monkeypatch, str(tmp_path)) == 1
        assert "WARNING: No score history yet" in capsys.readouterr().out

    def test_not_a_directory_exits_2(self, tmp_path, monkeypatch, capsys):
        assert _run(monkeypatch, str(tmp_path / "nope")) == 2
        assert "Not a directory" in capsys.readouterr().err

    def test_negative_last_exits_2(self, tmp_path, monkeypatch, capsys):
        assert _run(monkeypatch, str(tmp_path), "--last", "-1") == 2
        assert "--last must be 0 or more" in capsys.readouterr().err

    @pytest.mark.parametrize("argv", [("--metric", "speed"), ("--scale", "log"), ("--last", "x")])
    def test_bad_arguments_exit_2(self, tmp_path, monkeypatch, argv):
        assert _run(monkeypatch, str(tmp_path), *argv) == 2
