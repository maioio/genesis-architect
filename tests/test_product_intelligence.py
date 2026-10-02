"""Tests for product_intelligence - anonymous, opt-in, default-off telemetry.

These tests encode the binding privacy invariants from Constitution 09:
default OFF, anonymous, revocable, never collects sensitive content, never gates
the product, and always lets the user inspect/clear what is stored.
"""

from genesis_architect.pro.product_intelligence import (
    CONSENT_PROMPT, load_config, set_consent, revoke_consent, is_enabled, needs_consent_prompt,
    sanitize_event, record_event, read_events, describe_payload, clear_events,
)


class TestDefaultOff:
    def test_disabled_by_default(self, tmp_path):
        assert is_enabled(tmp_path) is False
        assert load_config(tmp_path).enabled is False

    def test_needs_prompt_until_decided(self, tmp_path):
        assert needs_consent_prompt(tmp_path) is True
        set_consent(False, tmp_path)
        assert needs_consent_prompt(tmp_path) is False  # asked & answered (no)

    def test_record_is_noop_when_off(self, tmp_path):
        assert record_event("engine_used", {"engine": "recovery"}, tmp_path) is False
        assert read_events(tmp_path) == []


class TestConsent:
    def test_enable_generates_anonymous_install_id(self, tmp_path):
        cfg = set_consent(True, tmp_path)
        assert cfg.enabled is True
        assert cfg.install_id  # a random id exists
        assert len(cfg.install_id) == 32  # uuid4 hex
        # not derived from anything identifying - just check it's hex
        int(cfg.install_id, 16)

    def test_no_install_id_before_enabling(self, tmp_path):
        cfg = set_consent(False, tmp_path)
        assert cfg.install_id == ""

    def test_revoke_turns_off_but_keeps_events(self, tmp_path):
        set_consent(True, tmp_path)
        record_event("engine_used", {"engine": "recovery"}, tmp_path)
        assert len(read_events(tmp_path)) == 1
        revoke_consent(tmp_path)
        assert is_enabled(tmp_path) is False
        # revoke stops collection but does not silently delete history
        assert len(read_events(tmp_path)) == 1
        # and further events are not recorded
        assert record_event("engine_used", {"engine": "c4"}, tmp_path) is False
        assert len(read_events(tmp_path)) == 1


class TestSanitizer:
    def test_accepts_known_event_and_fields(self, tmp_path):
        r = sanitize_event("engine_used", {"engine": "recovery", "tier": "pro"})
        assert r.ok and r.event == {"event": "engine_used",
                                    "fields": {"engine": "recovery", "tier": "pro"}}

    def test_rejects_unknown_event(self):
        assert sanitize_event("steal_code", {"x": "y"}).ok is False

    def test_rejects_unknown_field(self):
        assert sanitize_event("engine_used", {"engine": "r", "evil": "x"}).ok is False

    def test_drops_pathlike_value(self):
        r = sanitize_event("friction_point", {"where": "C:/Users/Maio/secret.py"})
        assert r.ok is True
        assert "where" in r.dropped_fields
        assert r.event == {"event": "friction_point", "fields": {}}

    def test_drops_secret_looking_value(self):
        for bad in ("sk-abc123", "bearer_xyz", "my_api_key", "a@b.com",
                    "http://x", "ghp_token"):
            r = sanitize_event("friction_point", {"where": bad})
            assert "where" in r.dropped_fields, bad

    def test_drops_free_text(self):
        r = sanitize_event("friction_point",
                            {"where": "the user got stuck on the login form"})
        assert "where" in r.dropped_fields  # spaces -> not a token

    def test_coerces_numbers(self):
        r = sanitize_event("step_duration", {"step": "scan", "bucket": "5"})
        assert r.ok and r.event["fields"]["bucket"] == "5"


class TestRecording:
    def test_records_when_enabled(self, tmp_path):
        set_consent(True, tmp_path)
        assert record_event("workflow_chosen", {"workflow": "recovery"}, tmp_path)
        events = read_events(tmp_path)
        assert len(events) == 1
        e = events[0]
        assert e["event"] == "workflow_chosen"
        assert e["fields"] == {"workflow": "recovery"}
        assert e["install_id"] == load_config(tmp_path).install_id
        assert "ts" in e

    def test_unsafe_event_not_written_even_when_enabled(self, tmp_path):
        set_consent(True, tmp_path)
        assert record_event("friction_point",
                            {"where": "/home/user/app.py"}, tmp_path) is True
        # event written, but the unsafe field was stripped
        assert read_events(tmp_path)[0]["fields"] == {}

    def test_unknown_event_never_written(self, tmp_path):
        set_consent(True, tmp_path)
        assert record_event("exfiltrate", {"code": "x"}, tmp_path) is False
        assert read_events(tmp_path) == []


class TestTransparency:
    def test_describe_when_off(self, tmp_path):
        assert "OFF" in describe_payload(tmp_path)

    def test_describe_lists_counts(self, tmp_path):
        set_consent(True, tmp_path)
        record_event("engine_used", {"engine": "recovery"}, tmp_path)
        record_event("engine_used", {"engine": "c4"}, tmp_path)
        out = describe_payload(tmp_path)
        assert "ON" in out and "engine_used: 2" in out
        assert "Never stored" in out

    def test_clear_removes_events(self, tmp_path):
        set_consent(True, tmp_path)
        record_event("engine_used", {"engine": "recovery"}, tmp_path)
        assert clear_events(tmp_path) == 1
        assert read_events(tmp_path) == []


class TestResilience:
    def test_corrupt_config_falls_back_to_off(self, tmp_path):
        d = tmp_path / ".genesis" / "telemetry"
        d.mkdir(parents=True)
        (d / "config.json").write_text("{not json")
        assert is_enabled(tmp_path) is False

    def test_corrupt_event_line_skipped(self, tmp_path):
        set_consent(True, tmp_path)
        record_event("engine_used", {"engine": "recovery"}, tmp_path)
        p = tmp_path / ".genesis" / "telemetry" / "events.jsonl"
        p.write_text(p.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")
        assert len(read_events(tmp_path)) == 1  # good line survives

    def test_consent_prompt_text_is_anonymous(self):
        low = CONSENT_PROMPT.lower()
        assert "no code" in low and "no secrets" in low


class TestHardening:
    """Defense-in-depth fixes from adversarial privacy review."""

    def test_injected_install_id_is_discarded(self, tmp_path):
        d = tmp_path / ".genesis" / "telemetry"
        d.mkdir(parents=True)
        (d / "config.json").write_text(
            '{"enabled": true, "decided": true, '
            '"install_id": "C:/Users/Maio/secret"}')
        cfg = load_config(tmp_path)
        assert cfg.install_id == ""  # tampered id rejected, not carried

    def test_valid_install_id_survives_roundtrip(self, tmp_path):
        cfg = set_consent(True, tmp_path)
        reloaded = load_config(tmp_path)
        assert reloaded.install_id == cfg.install_id

    def test_nan_inf_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            r = sanitize_event("step_duration", {"step": "scan", "bucket": bad})
            assert "bucket" in r.dropped_fields

    def test_describe_does_not_echo_foreign_event_names(self, tmp_path):
        set_consent(True, tmp_path)
        p = tmp_path / ".genesis" / "telemetry" / "events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"event": "C:/Users/Maio/secret.py", "fields": {}}\n',
                     encoding="utf-8")
        out = describe_payload(tmp_path)
        assert "secret.py" not in out
        assert "unrecognized" in out
