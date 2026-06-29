"""Tests for ui_workspace - the no-setup Floating Assistant + Canvas renderer."""
import json
from pathlib import Path

from genesis_architect_pro.ui_workspace import (
    WorkspaceState, collect_state, render_workspace, write_workspace,
)


def _write(g: Path, rel: str, data: dict):
    p = g / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


class TestCollectState:
    def test_empty_project_is_honest(self, tmp_path):
        st = collect_state(tmp_path)
        assert st.architecture_score is None
        assert st.status == "no analysis yet"
        assert "Run an analysis" in st.recommended_action

    def test_reads_score(self, tmp_path):
        _write(tmp_path / ".genesis", "model.json",
               {"total": 82, "score_label": "GOOD"})
        st = collect_state(tmp_path)
        assert st.architecture_score == 82.0 and st.score_label == "GOOD"
        assert st.status == "ready"

    def test_reads_graph_and_counts_types(self, tmp_path):
        _write(tmp_path / ".genesis", "knowledge/graph.json", {
            "nodes": {"cve:1": {"type": "cve"}, "module:a": {"type": "module"},
                      "drift:a": {"type": "drift"}, "risk:r": {"type": "risk"}},
            "edges": [{"src": "cve:1", "rel": "affects", "dst": "module:a"}],
        })
        st = collect_state(tmp_path)
        assert st.graph_nodes == 4 and st.graph_edges == 1
        assert st.cve_count == 1 and st.drift_count == 1 and st.risk_count == 1

    def test_warnings_and_action_from_cve(self, tmp_path):
        _write(tmp_path / ".genesis", "knowledge/graph.json",
               {"nodes": {"cve:1": {"type": "cve"}}, "edges": []})
        st = collect_state(tmp_path)
        assert any("CVE" in w for w in st.warnings)
        assert "security" in st.recommended_action.lower() or "recovery" in st.recommended_action.lower()

    def test_low_score_warning(self, tmp_path):
        _write(tmp_path / ".genesis", "model.json", {"total": 40})
        st = collect_state(tmp_path)
        assert any("low" in w for w in st.warnings)

    def test_corrupt_artifact_does_not_crash(self, tmp_path):
        g = tmp_path / ".genesis"
        g.mkdir()
        (g / "model.json").write_text("{not json")
        st = collect_state(tmp_path)  # must not raise
        assert st.architecture_score is None


class TestRender:
    def test_render_is_self_contained_html(self, tmp_path):
        html = render_workspace(tmp_path)
        assert html.startswith("<!DOCTYPE html>")
        # no external assets (offline / no-setup)
        assert "http://" not in html and "https://" not in html
        assert "<script>" in html and "<style>" in html

    def test_render_has_both_modes(self, tmp_path):
        html = render_workspace(tmp_path)
        assert "ga-panel" in html       # floating assistant
        assert 'id="canvas"' in html    # canvas workspace

    def test_render_shows_empty_state_honestly(self, tmp_path):
        html = render_workspace(tmp_path)
        assert "No analysis artifacts yet" in html

    def test_render_shows_score_when_present(self, tmp_path):
        _write(tmp_path / ".genesis", "model.json", {"total": 91, "score_label": "EXCELLENT"})
        html = render_workspace(tmp_path)
        assert "91" in html and "EXCELLENT" in html

    def test_escapes_content(self, tmp_path):
        _write(tmp_path / ".genesis", "model.json",
               {"total": 50, "score_label": "<script>x</script>"})
        html = render_workspace(tmp_path)
        assert "<script>x</script>" not in html.split("<body>")[1].replace(
            "<script>function gaToggle", "")  # the label is escaped


class TestWrite:
    def test_write_creates_file(self, tmp_path):
        path = write_workspace(tmp_path)
        assert path is not None and path.exists()
        assert path.name == "workspace.html"
        assert path.parent.name == "ui"

    def test_written_html_is_valid_doctype(self, tmp_path):
        path = write_workspace(tmp_path)
        assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
