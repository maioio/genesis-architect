"""Tests for memory_engine - per-project Markdown memory + Decision Journal."""
from genesis_architect.pro.memory_engine import (
    MEMORY_FILES, DecisionJournalEntry,
    init_memory, record_decision, record_research, record_risk, record_adr,
    record_lesson, set_project_memory, read_memory, memory_status,
)


class TestInit:
    def test_creates_all_files(self, tmp_path):
        created = init_memory(tmp_path)
        assert set(created) == set(MEMORY_FILES)
        for name in MEMORY_FILES:
            assert (tmp_path / ".genesis" / name).exists()

    def test_idempotent_non_destructive(self, tmp_path):
        record_lesson("first lesson", project_root=tmp_path)
        init_memory(tmp_path)  # must not wipe existing content
        assert "first lesson" in read_memory("lessons_learned.md", tmp_path)


class TestDecisionJournal:
    def test_records_entry_with_schema(self, tmp_path):
        e = DecisionJournalEntry(
            decision="use FastAPI",
            alternatives=["Flask", "Django"],
            evidence=["official docs", "github issues"],
            confidence="high",
            what_would_change_it="if async support regresses",
            loop_step="Decide")
        assert record_decision(e, tmp_path)
        md = read_memory("decision_log.md", tmp_path)
        assert "use FastAPI" in md
        assert "Flask" in md and "Django" in md
        assert "official docs" in md
        assert "what would change it" in md.lower()

    def test_high_confidence_requires_evidence(self, tmp_path):
        e = DecisionJournalEntry(decision="risky call", confidence="high")
        record_decision(e, tmp_path)
        md = read_memory("decision_log.md", tmp_path)
        # downgraded to medium because there was no evidence
        assert "Confidence:** medium" in md

    def test_entry_has_absolute_date(self, tmp_path):
        record_decision(DecisionJournalEntry(decision="x", evidence=["e"]),
                        tmp_path)
        md = read_memory("decision_log.md", tmp_path)
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", md)

    def test_multiple_entries_appended(self, tmp_path):
        record_decision(DecisionJournalEntry(decision="one", evidence=["e"]), tmp_path)
        record_decision(DecisionJournalEntry(decision="two", evidence=["e"]), tmp_path)
        md = read_memory("decision_log.md", tmp_path)
        assert "one" in md and "two" in md


class TestOtherJournals:
    def test_research_history(self, tmp_path):
        record_research("fastapi async", ["docs", "so"], "async fully supported",
                        project_root=tmp_path)
        assert "async fully supported" in read_memory("research_history.md", tmp_path)

    def test_known_risks(self, tmp_path):
        record_risk("auth module untested", severity="high", status="open",
                    project_root=tmp_path)
        md = read_memory("known_risks.md", tmp_path)
        assert "auth module untested" in md and "high" in md

    def test_adr(self, tmp_path):
        record_adr("layered architecture", "domain never imports infra",
                   project_root=tmp_path)
        assert "domain never imports infra" in read_memory(
            "architecture_decisions.md", tmp_path)

    def test_lesson_worked_flag(self, tmp_path):
        record_lesson("caching helped", worked=True, project_root=tmp_path)
        record_lesson("global state hurt", worked=False, project_root=tmp_path)
        md = read_memory("lessons_learned.md", tmp_path)
        assert "✅" in md and "❌" in md


class TestProjectMemory:
    def test_set_replaces_body(self, tmp_path):
        set_project_memory("v1 state", project_root=tmp_path)
        set_project_memory("v2 state", project_root=tmp_path)
        md = read_memory("project_memory.md", tmp_path)
        assert "v2 state" in md and "v1 state" not in md


class TestStatus:
    def test_status_reports_presence(self, tmp_path):
        record_lesson("x", project_root=tmp_path)
        st = memory_status(tmp_path)
        assert st["lessons_learned.md"]  # truthy line count
        assert st["project_memory.md"] is False  # not created yet

    def test_read_missing_returns_empty(self, tmp_path):
        assert read_memory("known_risks.md", tmp_path) == ""
