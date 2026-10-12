"""Contract tests for the optional Completion Guardian bridge, using a fake Guardian.

The fake mimics only the documented `status` and `mark` subcommands. No real Guardian,
no global install and no network are involved.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core import completion_guardian as cg  # noqa: E402

FAKE = '''
import hashlib, json, sys
from pathlib import Path
args = sys.argv[1:]
proj = Path(args[args.index("--project") + 1])
mode = (proj / ".fake_mode").read_text().strip() if (proj / ".fake_mode").exists() else "ok"
state = proj / ".fake_state.json"
fp = hashlib.sha1((proj / "README.md").read_bytes()).hexdigest()
if mode == "garbage":
    print("not json"); sys.exit(0)
if mode == "crash":
    sys.exit(2)
s = json.loads(state.read_text()) if state.exists() else {}
if args[0] == "mark":
    if mode != "mark_noop":
        s = {"fp": fp, "mode": args[args.index("--mode") + 1]}
        state.write_text(json.dumps(s))
    (proj / ".marks").open("a").write("x")
    print(json.dumps({"ok": True})); sys.exit(0)
cur = s.get("fp") == fp
print(json.dumps({"fingerprint": fp, "audited_current_state": cur,
                  "audited_final_current_state": cur and s.get("mode") == "final"}))
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "guardian.py").write_text(FAKE, encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "README.md").write_text("v1", encoding="utf-8")
    monkeypatch.setenv(cg.STATE_ENV, str(tmp_path / "att"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-cfg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv(cg.ENV_OVERRIDE, raising=False)
    return skill, proj, monkeypatch


def use_guardian(env):
    skill, proj, mp = env
    mp.setenv(cg.ENV_OVERRIDE, str(skill))
    return proj


def marks(proj):
    f = proj / ".marks"
    return len(f.read_text()) if f.exists() else 0


def test_unavailable_fails_open_without_install(env):
    _, proj, _ = env
    for fn in (cg.detect, cg.begin, cg.finalize):
        payload, code = fn(proj)
        assert code == cg.EXIT_OK and payload["available"] is False
        assert payload["action"] == "proceed_without_guardian"
    assert marks(proj) == 0


def test_available_requests_final_audit(env):
    proj = use_guardian(env)
    payload, code = cg.begin(proj)
    assert code == cg.EXIT_OK and payload["action"] == "run_final_audit"


def test_findings_block_mark(env):
    proj = use_guardian(env)
    cg.begin(proj)
    payload, code = cg.record(proj, "findings")
    assert code == cg.EXIT_BLOCKED and payload["action"] == "fix_findings"
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_BLOCKED and payload["action"] == "blocked_no_clear_audit"
    assert marks(proj) == 0


def test_fixed_and_reaudited_allows_final_mark(env):
    proj = use_guardian(env)
    cg.begin(proj)
    cg.record(proj, "findings")
    (proj / "README.md").write_text("v2 fixed", encoding="utf-8")
    payload, _ = cg.begin(proj)
    cg.record(proj, "clear")
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_OK and payload["action"] == "final_marked"
    assert cg.detect(proj)[0]["audited_final_current_state"] is True
    assert marks(proj) == 1


def test_change_after_clear_audit_blocks_mark(env):
    proj = use_guardian(env)
    cg.begin(proj)
    cg.record(proj, "clear")
    (proj / "README.md").write_text("edited after audit", encoding="utf-8")
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_BLOCKED and payload["action"] == "blocked_state_changed"
    assert marks(proj) == 0


@pytest.mark.parametrize("mode", ["garbage", "crash"])
def test_malformed_guardian_degrades_without_false_audit(env, mode):
    proj = use_guardian(env)
    (proj / ".fake_mode").write_text(mode)
    for fn in (cg.detect, cg.begin):
        payload, code = fn(proj)
        assert code == cg.EXIT_DEGRADED and payload["action"] == "degraded_use_genesis_gates"
    payload, code = cg.finalize(proj)
    assert code != cg.EXIT_OK or payload["action"] != "final_marked"
    assert marks(proj) == 0


def test_midflow_failure_never_reports_audited(env):
    proj = use_guardian(env)
    cg.begin(proj)
    cg.record(proj, "clear")
    (proj / ".fake_mode").write_text("garbage")
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_DEGRADED and payload["action"] != "final_marked"
    assert marks(proj) == 0


def test_mark_that_does_not_take_effect_is_degraded(env):
    proj = use_guardian(env)
    cg.begin(proj)
    cg.record(proj, "clear")
    (proj / ".fake_mode").write_text("mark_noop")
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_DEGRADED and payload["action"] != "final_marked"


def test_never_marks_without_a_started_audit(env):
    proj = use_guardian(env)
    payload, code = cg.record(proj, "clear")
    assert code == cg.EXIT_BLOCKED and payload["action"] == "blocked_no_audit_started"
    payload, code = cg.finalize(proj)
    assert code == cg.EXIT_BLOCKED and marks(proj) == 0


def test_discovery_order_and_documented_locations_only(env, tmp_path):
    skill, proj, mp = env
    assert cg.locate(proj) is None
    local = proj / ".claude" / "skills" / cg.SKILL_NAME / "scripts"
    local.mkdir(parents=True)
    (local / "guardian.py").write_text(FAKE, encoding="utf-8")
    assert cg.locate(proj) == proj / ".claude" / "skills" / cg.SKILL_NAME
    mp.setenv(cg.ENV_OVERRIDE, str(skill))
    assert cg.locate(proj) == skill


def test_cli_exit_codes(env, capsys):
    proj = use_guardian(env)
    assert cg.main(["begin", "--project", str(proj)]) == cg.EXIT_OK
    assert cg.main(["record", "--project", str(proj), "--verdict", "findings"]) == cg.EXIT_BLOCKED
    assert json.loads(capsys.readouterr().out.split("\n}\n")[-2] + "\n}")["action"] == "fix_findings"


def test_no_guardian_code_is_vendored():
    names = {p.name for p in ROOT.rglob("*.py") if ".git" not in p.parts}
    assert "guardian.py" not in names and "probe.py" not in names
