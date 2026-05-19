"""Tests for the 3 new hard gates added in v2.4.0: phase2, phase5-previews, phase6-smoke."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from genesis_state import (
    write_phase2, require_phase2,
    write_phase3_validation, require_phase3_validation,
    write_phase5_previews, require_phase5_previews,
    write_phase6_smoke, require_phase6_smoke,
    SMOKE_COMMANDS,
)


# ---------------------------------------------------------------------------
# Phase 2 gate
# ---------------------------------------------------------------------------

class TestPhase2Gate:
    def test_write_phase2_passes_when_floor_met(self, tmp_path):
        rc = write_phase2(str(tmp_path), repo_count=12, deep_count=5)
        assert rc == 0
        state = json.loads((tmp_path / ".genesis" / "phase-2-research.json").read_text())
        assert state["phase2_passed"] is True
        assert state["user_override"] is False

    def test_write_phase2_fails_when_repos_insufficient(self, tmp_path, capsys):
        rc = write_phase2(str(tmp_path), repo_count=6, deep_count=5)
        assert rc == 1
        assert "floor not met" in capsys.readouterr().err.lower()

    def test_write_phase2_fails_when_deep_insufficient(self, tmp_path):
        rc = write_phase2(str(tmp_path), repo_count=12, deep_count=3)
        assert rc == 1

    def test_write_phase2_override_records_acknowledgment(self, tmp_path):
        rc = write_phase2(str(tmp_path), repo_count=6, deep_count=3, override=True)
        assert rc == 0
        state = json.loads((tmp_path / ".genesis" / "phase-2-research.json").read_text())
        assert state["user_override"] is True
        assert state["phase2_passed"] is False  # floor not met, but override accepted

    def test_require_phase2_passes_when_gate_written(self, tmp_path):
        write_phase2(str(tmp_path), repo_count=15, deep_count=8)
        assert require_phase2(str(tmp_path)) == 0

    def test_require_phase2_fails_when_no_state_file(self, tmp_path, capsys):
        rc = require_phase2(str(tmp_path))
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_require_phase2_accepts_override(self, tmp_path):
        write_phase2(str(tmp_path), repo_count=5, deep_count=2, override=True)
        assert require_phase2(str(tmp_path)) == 0

    def test_require_phase2_rejects_failed_state_without_override(self, tmp_path):
        write_phase2(str(tmp_path), repo_count=5, deep_count=2)
        # state was written with phase2_passed=False and override=False
        rc = require_phase2(str(tmp_path))
        assert rc == 1


# ---------------------------------------------------------------------------
# Phase 3 validation gate
# ---------------------------------------------------------------------------

class TestPhase3ValidationGate:
    def test_write_passes_when_no_dead_urls(self, tmp_path):
        rc = write_phase3_validation(str(tmp_path), urls_checked=10, urls_dead=0)
        assert rc == 0
        import json
        state = json.loads((tmp_path / ".genesis" / "phase-3-validation.json").read_text())
        assert state["phase3_validation_passed"] is True

    def test_write_fails_when_dead_urls_exist(self, tmp_path, capsys):
        rc = write_phase3_validation(str(tmp_path), urls_checked=10, urls_dead=2)
        assert rc == 1
        assert "dead URL" in capsys.readouterr().err

    def test_require_passes_when_gate_written(self, tmp_path):
        write_phase3_validation(str(tmp_path), urls_checked=5, urls_dead=0)
        assert require_phase3_validation(str(tmp_path)) == 0

    def test_require_fails_when_no_state_file(self, tmp_path, capsys):
        rc = require_phase3_validation(str(tmp_path))
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_require_fails_when_validation_failed(self, tmp_path):
        write_phase3_validation(str(tmp_path), urls_checked=5, urls_dead=1)
        assert require_phase3_validation(str(tmp_path)) == 1


# ---------------------------------------------------------------------------
# Phase 5 previews gate
# ---------------------------------------------------------------------------

class TestPhase5PreviewsGate:
    def test_write_phase5_previews_all_present(self, tmp_path):
        rc = write_phase5_previews(str(tmp_path), True, True, True)
        assert rc == 0
        state = json.loads((tmp_path / ".genesis" / "phase-5-previews.json").read_text())
        assert state["phase5_previews_present"] is True

    def test_write_phase5_previews_missing_research(self, tmp_path, capsys):
        rc = write_phase5_previews(str(tmp_path), False, True, True)
        assert rc == 1
        assert "RESEARCH.md" in capsys.readouterr().err

    def test_write_phase5_previews_missing_pitfalls(self, tmp_path, capsys):
        rc = write_phase5_previews(str(tmp_path), True, False, True)
        assert rc == 1
        assert "PITFALLS.md" in capsys.readouterr().err

    def test_write_phase5_previews_missing_roadmap(self, tmp_path, capsys):
        rc = write_phase5_previews(str(tmp_path), True, True, False)
        assert rc == 1
        assert "ROADMAP.md" in capsys.readouterr().err

    def test_require_phase5_previews_passes_when_all_present(self, tmp_path):
        write_phase5_previews(str(tmp_path), True, True, True)
        assert require_phase5_previews(str(tmp_path)) == 0

    def test_require_phase5_previews_fails_when_no_state_file(self, tmp_path, capsys):
        rc = require_phase5_previews(str(tmp_path))
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_require_phase5_previews_fails_when_incomplete(self, tmp_path):
        write_phase5_previews(str(tmp_path), True, False, True)
        # file is written even on failure - read it back and verify
        state = json.loads((tmp_path / ".genesis" / "phase-5-previews.json").read_text())
        assert state["phase5_previews_present"] is False
        assert require_phase5_previews(str(tmp_path)) == 1


# ---------------------------------------------------------------------------
# Phase 6 smoke gate
# ---------------------------------------------------------------------------

class TestPhase6SmokeGate:
    def test_write_phase6_smoke_passes_on_exit_0(self, tmp_path):
        rc = write_phase6_smoke(str(tmp_path), "cli", "mytool --version", 0)
        assert rc == 0
        state = json.loads((tmp_path / ".genesis" / "phase-6-smoke.json").read_text())
        assert state["phase6_smoke_passed"] is True
        assert state["phase6_smoke_defined"] is True

    def test_write_phase6_smoke_fails_on_nonzero_exit(self, tmp_path, capsys):
        rc = write_phase6_smoke(str(tmp_path), "cli", "mytool --version", 1)
        assert rc == 1
        assert "failed" in capsys.readouterr().err.lower()

    def test_write_phase6_smoke_records_command(self, tmp_path):
        write_phase6_smoke(str(tmp_path), "library", "python -c 'import mylib'", 0)
        state = json.loads((tmp_path / ".genesis" / "phase-6-smoke.json").read_text())
        assert state["smoke_command"] == "python -c 'import mylib'"
        assert state["archetype"] == "library"

    def test_require_phase6_smoke_passes_when_gate_written(self, tmp_path):
        write_phase6_smoke(str(tmp_path), "cli", "mytool --version", 0)
        assert require_phase6_smoke(str(tmp_path)) == 0

    def test_require_phase6_smoke_fails_when_no_state_file(self, tmp_path, capsys):
        rc = require_phase6_smoke(str(tmp_path))
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_require_phase6_smoke_fails_when_exit_nonzero(self, tmp_path):
        write_phase6_smoke(str(tmp_path), "cli", "bad --version", 127)
        assert require_phase6_smoke(str(tmp_path)) == 1


# ---------------------------------------------------------------------------
# SMOKE_COMMANDS constant
# ---------------------------------------------------------------------------

class TestSmokeCommandsConstant:
    def test_all_archetypes_have_templates(self):
        for archetype in ("cli", "library", "service", "frontend"):
            assert archetype in SMOKE_COMMANDS, f"Missing smoke template for: {archetype}"

    def test_cli_template_contains_entrypoint(self):
        assert "{entrypoint}" in SMOKE_COMMANDS["cli"]

    def test_library_template_contains_pkg(self):
        assert "{pkg}" in SMOKE_COMMANDS["library"]

    def test_service_template_contains_port(self):
        assert "{port}" in SMOKE_COMMANDS["service"]
