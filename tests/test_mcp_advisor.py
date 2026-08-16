"""Tests for mcp_advisor.py — the dual-level MCP & skill advisor.

The invariant this suite defends hardest: a recommendation may never appear
without the evidence that produced it. Advice with no inspectable basis is a
guess wearing a suit.
"""

from __future__ import annotations

import json

import pytest

from genesis_architect_pro.mcp_advisor import (
    CATALOG,
    AdvisorReport,
    advise,
    advise_global,
    advise_local,
    detect_signals,
    format_report,
    installed_mcp_servers,
)


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_mcp_config(tmp_path_factory, monkeypatch):
    """Pin the advisor to an empty MCP config for every test.

    Without this the advisor reads the developer's real ~/.claude.json, so
    "is github already installed?" would answer differently on every machine
    and the suite would pass here and fail in CI. Tests that specifically
    exercise installed-detection override this with their own config.
    """
    empty = tmp_path_factory.mktemp("mcp_cfg") / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GENESIS_MCP_CONFIG", str(empty))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pkg(tmp_path, deps: dict, dev: dict | None = None):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": deps, "devDependencies": dev or {}}),
        encoding="utf-8")


def _git_remote(tmp_path, url="https://github.com/acme/thing.git"):
    git = tmp_path / ".git"
    git.mkdir(exist_ok=True)
    (git / "config").write_text(
        f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8")


def _outcomes(tmp_path, records: list[dict]):
    learning = tmp_path / ".genesis" / "learning"
    learning.mkdir(parents=True, exist_ok=True)
    (learning / "outcomes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------


class TestDetectSignals:
    def test_empty_dir_detects_nothing(self, tmp_path):
        sig = detect_signals(tmp_path)
        assert sig.languages == set()
        assert sig.evidence == {}

    def test_missing_dir_is_safe(self, tmp_path):
        sig = detect_signals(tmp_path / "nope")
        assert sig.evidence == {}

    def test_python_detected_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        sig = detect_signals(tmp_path)
        assert "python" in sig.languages
        assert "pyproject.toml" in sig.evidence["python"]

    def test_python_detected_from_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
        assert "python" in detect_signals(tmp_path).languages

    def test_javascript_and_react_detected(self, tmp_path):
        _pkg(tmp_path, {"react": "^18"})
        sig = detect_signals(tmp_path)
        assert "javascript" in sig.languages
        assert "react" in sig.frameworks

    def test_dev_dependencies_also_scanned(self, tmp_path):
        _pkg(tmp_path, {}, dev={"svelte": "^4"})
        assert "svelte" in detect_signals(tmp_path).frameworks

    def test_expo_detected(self, tmp_path):
        _pkg(tmp_path, {"expo": "~56.0.4"})
        assert "expo" in detect_signals(tmp_path).frameworks

    def test_malformed_package_json_does_not_crash(self, tmp_path):
        (tmp_path / "package.json").write_text("{broken", encoding="utf-8")
        sig = detect_signals(tmp_path)
        assert "javascript" in sig.languages  # file exists
        assert sig.frameworks == set()        # but nothing parsed out of it

    def test_go_and_rust(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
        (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        sig = detect_signals(tmp_path)
        assert {"go", "rust"} <= sig.languages

    def test_docker_detected(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
        assert detect_signals(tmp_path).has_docker is True

    def test_compose_variants_detected(self, tmp_path):
        (tmp_path / "compose.yaml").write_text("services:\n", encoding="utf-8")
        assert detect_signals(tmp_path).has_docker is True

    def test_ci_detected_only_when_workflows_exist(self, tmp_path):
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        assert detect_signals(tmp_path).has_ci is False  # empty dir
        (workflows / "ci.yml").write_text("on: push\n", encoding="utf-8")
        assert detect_signals(tmp_path).has_ci is True

    def test_chrome_extension_needs_manifest_version(self, tmp_path):
        (tmp_path / "manifest.json").write_text(
            json.dumps({"name": "not an extension"}), encoding="utf-8")
        assert detect_signals(tmp_path).is_chrome_extension is False
        (tmp_path / "manifest.json").write_text(
            json.dumps({"manifest_version": 3}), encoding="utf-8")
        assert detect_signals(tmp_path).is_chrome_extension is True

    def test_database_from_prisma_dependency(self, tmp_path):
        _pkg(tmp_path, {"@prisma/client": "^5"})
        assert detect_signals(tmp_path).has_database is True

    def test_database_from_alembic(self, tmp_path):
        (tmp_path / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
        assert detect_signals(tmp_path).has_database is True

    def test_tests_directory_detected(self, tmp_path):
        (tmp_path / "tests").mkdir()
        assert detect_signals(tmp_path).has_tests is True

    def test_github_remote_detected(self, tmp_path):
        _git_remote(tmp_path)
        sig = detect_signals(tmp_path)
        assert sig.has_github_remote is True
        assert "github_remote" in sig.evidence

    def test_non_github_remote_not_flagged(self, tmp_path):
        _git_remote(tmp_path, "https://gitlab.com/acme/thing.git")
        assert detect_signals(tmp_path).has_github_remote is False


# ---------------------------------------------------------------------------
# Local advice — the evidence invariant
# ---------------------------------------------------------------------------


class TestLocalAdvice:
    def test_empty_project_yields_no_advice(self, tmp_path):
        assert advise_local(tmp_path) == []

    def test_every_recommendation_carries_evidence(self, tmp_path):
        _pkg(tmp_path, {"react": "^18", "@prisma/client": "^5"})
        _git_remote(tmp_path)
        (tmp_path / "Dockerfile").write_text("FROM node\n", encoding="utf-8")
        recs = advise_local(tmp_path)
        assert recs, "expected recommendations for a rich project"
        for rec in recs:
            assert rec.evidence, f"{rec.tool_id} was emitted with no evidence"
            for item in rec.evidence:
                assert "→" in item, "evidence must name the file that proved it"

    def test_github_recommended_only_with_remote(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        assert "github" not in {r.tool_id for r in advise_local(tmp_path)}
        _git_remote(tmp_path)
        assert "github" in {r.tool_id for r in advise_local(tmp_path)}

    def test_docker_recommended_only_with_docker(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        assert "docker" not in {r.tool_id for r in advise_local(tmp_path)}
        (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
        assert "docker" in {r.tool_id for r in advise_local(tmp_path)}

    def test_chrome_devtools_for_extension(self, tmp_path):
        (tmp_path / "manifest.json").write_text(
            json.dumps({"manifest_version": 3}), encoding="utf-8")
        assert "chrome-devtools" in {r.tool_id for r in advise_local(tmp_path)}

    def test_frontend_gets_ui_tools(self, tmp_path):
        _pkg(tmp_path, {"react": "^18"})
        ids = {r.tool_id for r in advise_local(tmp_path)}
        assert "21st" in ids and "figma" in ids

    def test_backend_does_not_get_ui_tools(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        ids = {r.tool_id for r in advise_local(tmp_path)}
        assert "21st" not in ids and "figma" not in ids

    def test_database_gets_db_tool(self, tmp_path):
        (tmp_path / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
        assert "neon" in {r.tool_id for r in advise_local(tmp_path)}

    def test_no_duplicate_tool_ids(self, tmp_path):
        _pkg(tmp_path, {"react": "^18", "expo": "~56"})
        _git_remote(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        ids = [r.tool_id for r in advise_local(tmp_path)]
        assert len(ids) == len(set(ids))

    def test_all_recommendations_are_scoped_local(self, tmp_path):
        _git_remote(tmp_path)
        assert all(r.scope == "local" for r in advise_local(tmp_path))

    def test_every_rec_explains_orchestration(self, tmp_path):
        _git_remote(tmp_path)
        for rec in advise_local(tmp_path):
            assert rec.why and rec.optimizes and rec.orchestration

    def test_deterministic_across_runs(self, tmp_path):
        _pkg(tmp_path, {"react": "^18"})
        _git_remote(tmp_path)
        first = [r.tool_id for r in advise_local(tmp_path)]
        second = [r.tool_id for r in advise_local(tmp_path)]
        assert first == second


# ---------------------------------------------------------------------------
# Global advice
# ---------------------------------------------------------------------------


class TestGlobalAdvice:
    def test_no_history_says_so(self, tmp_path):
        recs, notes = advise_global(tmp_path)
        assert recs == []
        assert notes and "No recorded task history" in notes[0]

    def test_history_drives_recommendations(self, tmp_path):
        _outcomes(tmp_path, [
            {"task_kind": "research", "profile": "deep_research", "accepted": True},
            {"task_kind": "research", "profile": "deep_research", "accepted": True},
        ])
        recs, _ = advise_global(tmp_path)
        ids = {r.tool_id for r in recs}
        assert "exa" in ids

    def test_recommendations_cite_the_count(self, tmp_path):
        _outcomes(tmp_path, [
            {"task_kind": "research", "profile": "p", "accepted": True} for _ in range(3)
        ])
        recs, _ = advise_global(tmp_path)
        assert any("3" in r.why for r in recs)
        assert all(r.evidence for r in recs)

    def test_unmapped_task_kind_notes_rather_than_invents(self, tmp_path):
        _outcomes(tmp_path, [
            {"task_kind": "totally_unknown_kind", "profile": "p", "accepted": True},
        ])
        recs, notes = advise_global(tmp_path)
        assert recs == []
        assert any("none map to a tool" in n for n in notes)

    def test_scope_is_global(self, tmp_path):
        _outcomes(tmp_path, [{"task_kind": "research", "profile": "p", "accepted": True}])
        recs, _ = advise_global(tmp_path)
        assert all(r.scope == "global" for r in recs)

    def test_no_duplicates_across_task_kinds(self, tmp_path):
        _outcomes(tmp_path, [
            {"task_kind": "research", "profile": "p", "accepted": True},
            {"task_kind": "deep_research", "profile": "p", "accepted": True},
        ])
        recs, _ = advise_global(tmp_path)
        ids = [r.tool_id for r in recs]
        assert len(ids) == len(set(ids))

    def test_corrupt_history_does_not_crash(self, tmp_path):
        learning = tmp_path / ".genesis" / "learning"
        learning.mkdir(parents=True)
        (learning / "outcomes.jsonl").write_text("{not json\n", encoding="utf-8")
        recs, notes = advise_global(tmp_path)
        assert isinstance(recs, list)


# ---------------------------------------------------------------------------
# Installed detection
# ---------------------------------------------------------------------------


class TestInstalledDetection:
    def test_marks_already_available(self, tmp_path, monkeypatch):
        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"github": {}}}), encoding="utf-8")
        monkeypatch.setenv("GENESIS_MCP_CONFIG", str(config))
        _git_remote(tmp_path)
        report = advise(tmp_path)
        github = next(r for r in report.local if r.tool_id == "github")
        assert github.already_available is True
        assert github not in report.actionable

    def test_unreadable_config_is_not_fatal(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.json"
        bad.write_text("{broken", encoding="utf-8")
        monkeypatch.setenv("GENESIS_MCP_CONFIG", str(bad))
        assert installed_mcp_servers() == set() or True  # must not raise
        _git_remote(tmp_path)
        report = advise(tmp_path)
        assert isinstance(report, AdvisorReport)

    def test_nested_project_servers_are_read(self, tmp_path, monkeypatch):
        config = tmp_path / "mcp.json"
        config.write_text(json.dumps(
            {"projects": {"/some/path": {"mcpServers": {"docker": {}}}}}), encoding="utf-8")
        monkeypatch.setenv("GENESIS_MCP_CONFIG", str(config))
        assert "docker" in installed_mcp_servers()

    def test_skills_never_marked_installed(self, tmp_path, monkeypatch):
        config = tmp_path / "mcp.json"
        config.write_text(json.dumps(
            {"mcpServers": {"software-architecture-skills": {}}}), encoding="utf-8")
        monkeypatch.setenv("GENESIS_MCP_CONFIG", str(config))
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        report = advise(tmp_path)
        skill = next(r for r in report.local if r.kind == "skill")
        # Only mcp_server recommendations consult the MCP config.
        assert skill.already_available is False


# ---------------------------------------------------------------------------
# Combined report
# ---------------------------------------------------------------------------


class TestAdvise:
    def test_returns_both_levels(self, tmp_path):
        _git_remote(tmp_path)
        _outcomes(tmp_path, [{"task_kind": "research", "profile": "p", "accepted": True}])
        report = advise(tmp_path)
        assert report.local and report.global_

    def test_local_only(self, tmp_path):
        _git_remote(tmp_path)
        _outcomes(tmp_path, [{"task_kind": "research", "profile": "p", "accepted": True}])
        report = advise(tmp_path, include_global=False)
        assert report.global_ == []

    def test_global_only(self, tmp_path):
        _git_remote(tmp_path)
        report = advise(tmp_path, include_local=False)
        assert report.local == []

    def test_empty_project_notes_the_absence(self, tmp_path):
        report = advise(tmp_path)
        assert any("No recognisable project signals" in n for n in report.notes)

    def test_report_never_installs_anything(self, tmp_path):
        # Sanity: advising must not create or modify anything in the tree.
        _git_remote(tmp_path)
        before = sorted(p.name for p in tmp_path.iterdir())
        advise(tmp_path)
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after


# ---------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_every_entry_is_fully_populated(self):
        for tool_id, spec in CATALOG.items():
            assert spec.tool_id == tool_id
            assert spec.kind in ("mcp_server", "skill")
            assert spec.title and spec.optimizes and spec.orchestration

    def test_both_external_skill_packs_present(self):
        assert CATALOG["software-architecture-skills"].kind == "skill"
        assert CATALOG["deep-research-skills"].kind == "skill"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatting:
    def test_empty_report_is_honest(self, tmp_path):
        text = format_report(advise(tmp_path))
        assert "Nothing to suggest" in text or "Note:" in text

    def test_populated_report_shows_all_four_fields(self, tmp_path):
        _git_remote(tmp_path)
        text = format_report(advise(tmp_path))
        for label in ("Why:", "Optimizes:", "Genesis:", "Evidence:"):
            assert label in text

    def test_report_states_nothing_installed(self, tmp_path):
        _git_remote(tmp_path)
        text = format_report(advise(tmp_path))
        assert "Nothing was installed" in text

    def test_signals_section_lists_evidence(self, tmp_path):
        _git_remote(tmp_path)
        assert "Detected in this project:" in format_report(advise(tmp_path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_advise_exits_zero(self, tmp_path):
        from genesis_architect_pro.gde_cli import main
        assert main(["advise", "--dir", str(tmp_path)]) == 0

    def test_advise_bad_dir_exits_one(self, tmp_path):
        from genesis_architect_pro.gde_cli import main
        assert main(["advise", "--dir", str(tmp_path / "nope")]) == 1

    def test_advise_json_output(self, tmp_path, capsys):
        from genesis_architect_pro.gde_cli import main
        _git_remote(tmp_path)
        main(["advise", "--dir", str(tmp_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert "local" in payload and "signals" in payload
        assert any(r["tool_id"] == "github" for r in payload["local"])

    def test_advise_local_only_flag(self, tmp_path, capsys):
        from genesis_architect_pro.gde_cli import main
        _outcomes(tmp_path, [{"task_kind": "research", "profile": "p", "accepted": True}])
        main(["advise", "--dir", str(tmp_path), "--local-only", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["global"] == []

    def test_in_package_namespace(self):
        import genesis_architect_pro as pkg
        for name in ("advise", "advise_local", "advise_global", "detect_signals"):
            assert hasattr(pkg, name)
