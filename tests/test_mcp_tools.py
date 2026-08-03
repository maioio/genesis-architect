"""Tests for mcp_tools - read-only Genesis analysis exposed as MCP tools."""
from pathlib import Path

import pytest

from genesis_architect.pro import mcp_tools as m


def _project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("import os\n")
    return tmp_path


class TestRegistry:
    def test_list_tools_has_expected(self):
        names = {t["name"] for t in m.list_tools()}
        assert {"genesis_architecture_score", "genesis_anti_patterns",
                "genesis_recovery_report", "genesis_gate"} <= names

    def test_every_tool_has_description(self):
        assert all(t["description"] for t in m.list_tools())

    def test_unknown_tool_raises(self):
        with pytest.raises(KeyError):
            m.call_tool("nope", ".")


class TestToolsRunReadOnly:
    def test_architecture_score(self, tmp_path):
        r = m.call_tool("genesis_architecture_score", str(_project(tmp_path)))
        assert "total" in r and "label" in r

    def test_anti_patterns(self, tmp_path):
        r = m.call_tool("genesis_anti_patterns", str(_project(tmp_path)))
        assert set(["critical", "high", "medium", "low"]) <= r.keys()

    def test_recovery_report(self, tmp_path):
        r = m.call_tool("genesis_recovery_report", str(_project(tmp_path)))
        assert isinstance(r, dict)

    def test_gate_no_rules_passes(self, tmp_path):
        r = m.call_tool("genesis_gate", str(_project(tmp_path)))
        assert r["passed"] is True

    def test_tools_do_not_create_files(self, tmp_path):
        """Read-only: calling tools must not write into the project root."""
        p = _project(tmp_path)
        before = set(x.name for x in p.iterdir())
        m.call_tool("genesis_architecture_score", str(p))
        m.call_tool("genesis_anti_patterns", str(p))
        after = set(x.name for x in p.iterdir())
        # tools may create the .genesis cache dir, but must not add stray files
        assert after - before <= {".genesis"}


class TestMcpServerOptional:
    def test_mcp_available_is_bool(self):
        assert isinstance(m.mcp_available(), bool)

    def test_build_server_raises_clean_without_sdk(self):
        if m.mcp_available():
            pytest.skip("mcp SDK is installed; cannot test the missing-SDK path")
        with pytest.raises(RuntimeError, match="MCP SDK not installed"):
            m.build_mcp_server()
