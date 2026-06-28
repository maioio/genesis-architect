"""Tests for import_audit - declared (model) vs actual (code) import edges."""
from pathlib import Path

import pytest

from genesis_architect_pro.import_audit import (
    audit, format_report, ImportAuditReport, _last_seg, _edge_matches,
)
from genesis_architect_pro.model_store import ArchModel, ModelNode, ModelLink


def _proj(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir()
    for name, content in files.items():
        (src / name).write_text(content)
    return tmp_path


def _model(nodes, links):
    return ArchModel(
        nodes=[ModelNode(id=f"n{n}", kind="component", name=n, technology=n) for n in nodes],
        links=[ModelLink(id=f"l{i}", src=f"n{s}", dst=f"n{d}")
               for i, (s, d) in enumerate(links)],
    )


class TestHelpers:
    def test_last_seg(self):
        assert _last_seg("src/foo/bar.py") == "bar"
        assert _last_seg("bar") == "bar"

    def test_edge_matches_exact_segment(self):
        actual = {("src/a", "src/b")}
        assert _edge_matches(("a", "b"), actual)
        assert not _edge_matches(("a", "c"), actual)

    def test_no_loose_substring_match(self):
        # "c" must NOT match "core" just because it is a substring
        actual = {("a", "core")}
        assert not _edge_matches(("a", "c"), actual)


class TestAudit:
    def test_no_model_returns_note(self, tmp_path):
        _proj(tmp_path, {"a.py": "x=1\n"})
        rep = audit(tmp_path)  # no model in .genesis
        assert isinstance(rep, ImportAuditReport)
        assert rep.consistent  # nothing to compare
        assert rep.notes

    def test_matching_link_is_consistent(self, tmp_path):
        d = _proj(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n"})
        rep = audit(d, model=_model(["a", "b"], [("a", "b")]))
        assert rep.matched == 1
        assert rep.consistent

    def test_declared_but_missing_import_flagged(self, tmp_path):
        d = _proj(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n", "c.py": "y=1\n"})
        rep = audit(d, model=_model(["a", "b", "c"], [("a", "b"), ("a", "c")]))
        assert not rep.consistent
        assert any(f.dst == "c" for f in rep.missing_imports)
        assert rep.matched == 1

    def test_undeclared_import_flagged(self, tmp_path):
        # code: a imports b; model knows both nodes but declares NO link
        d = _proj(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n"})
        rep = audit(d, model=_model(["a", "b"], []))
        assert any(_last_seg(f.dst) == "b" for f in rep.undeclared_imports)
        assert not rep.consistent

    def test_format_report_runs(self, tmp_path):
        d = _proj(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n", "c.py": "y=1\n"})
        out = format_report(audit(d, model=_model(["a", "b", "c"], [("a", "c")])))
        assert "Import Audit" in out and "RESULT:" in out

    def test_read_only_no_files_created(self, tmp_path):
        d = _proj(tmp_path, {"a.py": "import b\n", "b.py": "x=1\n"})
        before = {p.name for p in d.iterdir()}
        audit(d, model=_model(["a", "b"], [("a", "b")]))
        after = {p.name for p in d.iterdir()}
        assert after - before <= {".genesis"}
