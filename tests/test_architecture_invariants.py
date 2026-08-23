"""The published invariants must keep matching the code that produced them.

Genesis publishes structural numbers about itself in the README, the
architecture reference and the landing page. Prose copies of a number drift
silently - there is no compiler for a sentence. ARCHITECTURE_INVARIANTS.json is
the single source those documents answer to, generated from the live package.

These tests fail when a structural change lands without regenerating it, which
is the only moment the drift is cheap to fix.
"""

import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INVARIANTS = REPO / "ARCHITECTURE_INVARIANTS.json"
GENERATOR = REPO / "scripts" / "architecture_invariants.py"


@pytest.fixture(scope="module")
def published() -> dict:
    assert INVARIANTS.is_file(), (
        "ARCHITECTURE_INVARIANTS.json is missing. Regenerate it with "
        "`python scripts/architecture_invariants.py --write`."
    )
    return json.loads(INVARIANTS.read_text(encoding="utf-8"))


class TestInvariantsAreCurrent:
    def test_committed_file_matches_the_live_package(self):
        """The generator's own --check mode, run as a test.

        A structural change that nobody documented turns this red, and the
        failure message says exactly which command fixes it.
        """
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            capture_output=True, text=True, cwd=str(REPO), timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestTheInvariantsThemselves:
    """The file records claims. These assert the claims are true."""

    def test_zero_import_cycles(self, published):
        assert published["structure"]["import_cycles"] == 0

    def test_cli_modules_respect_the_self_imposed_ceiling(self, published):
        """11, against a rule that only flags at 15.

        A module sitting exactly on a threshold is a latent breach: the next
        feature tips it over. The ceiling is deliberately below the rule.
        """
        ceiling = published["thresholds"]["self_imposed_fan_out_ceiling"]
        over = [m for m in published["cli_modules"] if m["fan_out"] > ceiling]
        assert over == [], f"over the {ceiling} ceiling: {over}"

    def test_ceiling_leaves_margin_under_the_rule(self, published):
        t = published["thresholds"]
        assert t["self_imposed_fan_out_ceiling"] < t["god_class_fan_out"]

    def test_every_engine_id_is_registered(self, published):
        from genesis_architect.pro.engine_bootstrap import ensure_registered
        from genesis_architect.pro.engine_registry import get_default_registry

        ensure_registered()
        live = {d.id for d in get_default_registry().all()}
        assert set(published["engines"]) == live

    def test_gate_count_and_hard_blocks(self, published):
        """Two gates are non-overridable. That is a deliberate contract."""
        gates = published["gates"]
        assert len(gates) == published["counts"]["gates"]
        hard = [g for g in gates if not g["overridable"]]
        assert len(hard) == 2, [g["id"] for g in hard]
        assert {g["id"] for g in hard} == {"PLAN_WRITE", "RULES_FAIL"}

    def test_version_matches_the_package(self, published):
        import genesis_architect

        assert published["version"] == genesis_architect.__version__
