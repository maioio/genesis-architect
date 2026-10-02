"""Tests for learning_engine - per-project learning of research strategies.

Encodes Constitution 08: learns from outcomes (not project content), feeds back
immediately, and is honest about confidence (low until enough evidence).
"""
from genesis_architect.pro.learning_engine import (
    KNOWN_PROFILES, record_outcome, read_outcomes, rank_profiles, recommend_profile,
    summarize_lessons, write_lessons,
)


class TestRecording:
    def test_record_and_read(self, tmp_path):
        assert record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        outs = read_outcomes(tmp_path)
        assert len(outs) == 1
        assert outs[0].task_kind == "bug" and outs[0].profile == "bug_hunter"
        assert outs[0].accepted is True

    def test_normalizes_case_and_whitespace(self, tmp_path):
        record_outcome("  BUG ", " Bug_Hunter ", True, project_root=tmp_path)
        o = read_outcomes(tmp_path)[0]
        assert o.task_kind == "bug" and o.profile == "bug_hunter"

    def test_rejects_empty(self, tmp_path):
        assert record_outcome("", "bug_hunter", True, project_root=tmp_path) is False
        assert record_outcome("bug", "", True, project_root=tmp_path) is False
        assert read_outcomes(tmp_path) == []


class TestRanking:
    def test_ranks_by_acceptance_rate(self, tmp_path):
        # profile A: 2/2 accepted; profile B: 1/3 accepted
        for _ in range(2):
            record_outcome("arch", "architecture_review", True, project_root=tmp_path)
        record_outcome("arch", "deep_research", True, project_root=tmp_path)
        record_outcome("arch", "deep_research", False, project_root=tmp_path)
        record_outcome("arch", "deep_research", False, project_root=tmp_path)
        ranked = rank_profiles("arch", tmp_path)
        assert [s.profile for s in ranked] == ["architecture_review", "deep_research"]
        assert ranked[0].rate == 1.0
        assert abs(ranked[1].rate - (1 / 3)) < 1e-9

    def test_more_samples_break_rate_ties(self, tmp_path):
        # both 100% but one has more evidence -> ranked first
        for _ in range(5):
            record_outcome("sec", "security_review", True, project_root=tmp_path)
        record_outcome("sec", "deep_research", True, project_root=tmp_path)
        ranked = rank_profiles("sec", tmp_path)
        assert ranked[0].profile == "security_review"

    def test_only_counts_matching_kind(self, tmp_path):
        record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        record_outcome("arch", "architecture_review", True, project_root=tmp_path)
        assert len(rank_profiles("bug", tmp_path)) == 1


class TestRecommendation:
    def test_no_history_returns_none(self, tmp_path):
        rec = recommend_profile("bug", tmp_path)
        assert rec.profile is None and rec.confidence == "none"

    def test_low_confidence_with_few_samples(self, tmp_path):
        record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        rec = recommend_profile("bug", tmp_path)
        assert rec.profile == "bug_hunter"
        assert rec.confidence == "low"  # one sample is never high

    def test_medium_confidence(self, tmp_path):
        for _ in range(3):
            record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        assert recommend_profile("bug", tmp_path).confidence == "medium"

    def test_high_confidence_needs_many_samples(self, tmp_path):
        for _ in range(8):
            record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        rec = recommend_profile("bug", tmp_path)
        assert rec.confidence == "high"
        assert rec.rate == 1.0 and rec.samples == 8

    def test_rationale_and_alternatives(self, tmp_path):
        record_outcome("mig", "migration_planner", True, project_root=tmp_path)
        record_outcome("mig", "deep_research", False, project_root=tmp_path)
        rec = recommend_profile("mig", tmp_path)
        assert "migration_planner" in rec.rationale
        assert [a.profile for a in rec.alternatives] == ["deep_research"]


class TestLessons:
    def test_summary_empty(self, tmp_path):
        assert "No outcomes recorded" in summarize_lessons(tmp_path)

    def test_summary_lists_best_per_kind(self, tmp_path):
        for _ in range(4):
            record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        record_outcome("arch", "architecture_review", True, project_root=tmp_path)
        out = summarize_lessons(tmp_path)
        assert "## bug" in out and "bug_hunter" in out
        assert "## arch" in out

    def test_write_lessons_creates_file(self, tmp_path):
        record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        path = write_lessons(tmp_path)
        assert path is not None and path.exists()
        assert "bug_hunter" in path.read_text(encoding="utf-8")


class TestResilience:
    def test_corrupt_line_skipped(self, tmp_path):
        record_outcome("bug", "bug_hunter", True, project_root=tmp_path)
        p = tmp_path / ".genesis" / "learning" / "outcomes.jsonl"
        p.write_text(p.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")
        assert len(read_outcomes(tmp_path)) == 1

    def test_known_profiles_present(self):
        assert "bug_hunter" in KNOWN_PROFILES
        assert "recovery_mode" in KNOWN_PROFILES
