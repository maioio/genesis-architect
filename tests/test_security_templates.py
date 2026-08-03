"""Tests for security_templates.py's content generation.

Regression coverage for a real bug found by inspecting actual generated
output: the STRIDE threat-matrix table truncated "Enforce TLS 1.2+ on all
endpoints." to "Enforce TLS 1." because it split the mitigation text on the
first "." found anywhere, not the first real sentence boundary.
"""

from genesis_architect.pro.security_templates import (
    STRIDE_TEMPLATES,
    _first_sentence,
    _generate_stride_doc,
)


class TestFirstSentence:
    def test_simple_sentence(self):
        assert _first_sentence("Enforce strong authentication.") == "Enforce strong authentication."

    def test_does_not_truncate_on_decimal_point(self):
        text = "Enforce TLS 1.2+ on all endpoints. Use signed payloads for webhooks."
        assert _first_sentence(text) == "Enforce TLS 1.2+ on all endpoints."

    def test_multiple_sentences_keeps_only_first(self):
        text = "First sentence here. Second sentence here. Third."
        assert _first_sentence(text) == "First sentence here."

    def test_no_period_appends_one(self):
        assert _first_sentence("No terminal punctuation") == "No terminal punctuation."

    def test_period_at_end_no_trailing_space(self):
        assert _first_sentence("Ends right here.") == "Ends right here."

    def test_every_real_mitigation_string_is_not_truncated_mid_number(self):
        """Empirical regression guard: run the fix against every mitigation
        string actually shipped, not just a synthetic example."""
        for data in STRIDE_TEMPLATES.values():
            for mitigation in data["default_mitigations"].values():
                summary = _first_sentence(mitigation)
                # A summary ending in a bare digit + "." right before more
                # digits/a "+" in the source text means we cut a decimal in
                # half (e.g. "TLS 1." from "TLS 1.2+").
                cut_index = len(summary)
                if cut_index < len(mitigation) and mitigation[cut_index - 2].isdigit():
                    assert not mitigation[cut_index].isdigit(), (
                        f"truncated mid-number: {mitigation!r} -> {summary!r}")


class TestGenerateStrideDoc:
    def _stack(self, **overrides):
        base = {
            "language": "python", "archetype": "service", "framework": "FastAPI",
            "has_auth": False, "has_db": False, "has_api": True,
            "has_file_upload": False, "has_payments": False, "has_cli": False,
            "is_library": False,
        }
        base.update(overrides)
        return base

    def test_matrix_row_matches_detail_section_sentence(self, tmp_path):
        """The exact bug found in real output: the table row's mitigation
        must be a real prefix of the full mitigation shown in the detail
        section below it, not an independently-truncated string."""
        doc = _generate_stride_doc(tmp_path, self._stack())
        # T/api's real mitigation starts with "Enforce TLS 1.2+ on all endpoints."
        assert "| T | Tampering | Man-in-the-middle | Medium | High | Enforce TLS 1.2+ on all endpoints. |" in doc
        assert "Enforce TLS 1." in doc
        assert "Enforce TLS 1. |" not in doc  # the old truncated form must never reappear

    def test_all_six_categories_present(self, tmp_path):
        doc = _generate_stride_doc(tmp_path, self._stack())
        for letter in ("S", "T", "R", "I", "D", "E"):
            assert f"## {letter}:" in doc

    def test_cli_archetype_uses_cli_mitigations(self, tmp_path):
        doc = _generate_stride_doc(tmp_path, self._stack(
            has_api=False, has_cli=True))
        assert "OS keychain" in doc  # S/cli mitigation, not S/api's JWT text
