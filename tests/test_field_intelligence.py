"""Tests for field_intelligence - Reddit Answers workflow + verification rule."""
from genesis_architect.pro.field_intelligence import (
    REDDIT_ANSWERS_TEMPLATES, FieldFinding, FieldReport,
    build_reddit_answers_queries, verify_finding, run_field_workflow,
)


class TestQueries:
    def test_builds_developer_queries(self):
        qs = build_reddit_answers_queries("fastapi")
        assert "fastapi problems" in qs
        assert "fastapi worth it" in qs
        # vs-template skipped without an alternative
        assert not any(" vs " in q for q in qs)

    def test_includes_vs_when_alternative_given(self):
        qs = build_reddit_answers_queries("fastapi", "flask")
        assert "fastapi vs flask" in qs

    def test_empty_tool_returns_nothing(self):
        assert build_reddit_answers_queries("") == []

    def test_workflow_returns_plan(self):
        rep = run_field_workflow("django")
        assert rep.tool == "django"
        assert len(rep.queries) >= len(REDDIT_ANSWERS_TEMPLATES) - 1
        assert rep.findings == []


class TestVerificationRule:
    def test_verified_only_by_engineering_truth(self):
        f = FieldFinding(claim="X leaks memory under load")
        verify_finding(f, confirming_sources=["github_issues"])  # source tier
        assert f.verified is True and f.status == "verified"

    def test_field_source_does_not_verify(self):
        f = FieldFinding(claim="X is slow")
        # reddit is field tier — cannot serve as engineering-truth verification
        verify_finding(f, confirming_sources=["reddit"])
        assert f.verified is False and f.status == "unverified"

    def test_market_source_does_not_verify(self):
        f = FieldFinding(claim="everyone loves X")
        verify_finding(f, confirming_sources=["instagram"])
        assert f.verified is False

    def test_contradiction_marks_contradicted(self):
        f = FieldFinding(claim="X supports feature Y")
        verify_finding(f, confirming_sources=["github_issues"],
                       contradicting_sources=["official_docs"])
        assert f.status == "contradicted"


class TestReport:
    def test_summary_counts(self):
        rep = FieldReport(tool="x", findings=[
            verify_finding(FieldFinding("a"), confirming_sources=["official_docs"]),
            FieldFinding("b"),  # unverified
        ])
        assert len(rep.verified()) == 1
        assert len(rep.unverified()) == 1
        assert "not engineering truth" in rep.summary().lower()
