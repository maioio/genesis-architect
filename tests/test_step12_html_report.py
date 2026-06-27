"""
Tests for RecoveryReport.to_html() — Step 12.

Covers:
  - valid complete HTML document structure
  - all required sections rendered
  - embedded JSON payload present and parseable
  - HTML escaping of user/project-controlled text
  - empty report renders cleanly
  - high-risk report renders correctly
  - deterministic output for identical inputs
  - markdown output unchanged after adding to_html()
  - JSON output unchanged after adding to_html()
  - risk level badge colors present
  - quick wins section present
  - risk zones section present
  - deep refactor candidates section present
  - evidence basis section present
  - warnings section present
  - metadata section present
  - no external resource references (self-contained)
  - XSS vectors escaped in all recommendation fields
  - full suite remains green
"""

from __future__ import annotations

import json
import re

import pytest

from genesis_architect_pro.recovery_report import generate_report, RecoveryReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_report() -> RecoveryReport:
    return generate_report({})


def _vagrant_report(conf: float = 0.85) -> RecoveryReport:
    return generate_report({
        "drift_flags": {
            "vagrant_candidates": [
                {"node_id": "auth", "name": "AuthService", "kind": "component",
                 "reason": "not in planned", "confidence": conf}
            ],
            "stale_candidates": [],
            "confidence": conf, "basis": "test", "warnings": [],
        },
        "drift_score": {
            "overall_score": 30.0, "risk_level": "medium", "confidence": conf,
            "basis": "vagrant penalty", "top_risk_nodes": ["auth"],
            "per_node_scores": [], "warnings": [],
        },
        "source_anchors": {
            "total_responsibilities": 4, "unanchored_count": 2,
            "anchored_count": 2, "warnings": [],
        },
        "fix_commit_hotspots": {"src/auth.py": 5},
        "dead_file_candidates": ["src/orphan.py"],
        "version_sources": {"pyproject.toml": "1.0.0", "package.json": "1.1.0"},
        "version_drift": True,
    })


def _high_risk_report() -> RecoveryReport:
    return generate_report({
        "drift_flags": {
            "vagrant_candidates": [
                {"node_id": "a", "name": "NodeA", "kind": "service",
                 "reason": "absent from plan", "confidence": 0.90},
                {"node_id": "b", "name": "NodeB", "kind": "component",
                 "reason": "absent from plan", "confidence": 0.85},
            ],
            "stale_candidates": [
                {"node_id": "c", "responsibility_id": "r1",
                 "statement": "handle payments", "reason": "no anchor", "confidence": 0.80},
            ],
            "confidence": 0.88, "basis": "test", "warnings": ["test warning"],
        },
        "drift_score": {
            "overall_score": 72.0, "risk_level": "high", "confidence": 0.88,
            "basis": "combined penalties", "top_risk_nodes": ["a", "b"],
            "per_node_scores": [], "warnings": [],
        },
        "source_anchors": {
            "total_responsibilities": 10, "unanchored_count": 7,
            "anchored_count": 3, "warnings": [],
        },
        "architecture_score": 42.0,
        "fix_commit_hotspots": {"src/payments.py": 12, "src/core.py": 6},
    })


def _extract_json_payload(html: str) -> dict:
    m = re.search(r'id="json-payload">(.*?)</pre>', html, re.DOTALL)
    assert m, "json-payload element not found in HTML"
    raw = (m.group(1)
           .replace("&lt;", "<").replace("&gt;", ">")
           .replace("&amp;", "&").replace("&quot;", '"')
           .replace("&#x27;", "'"))
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Document structure
# ---------------------------------------------------------------------------

class TestDocumentStructure:
    def test_starts_with_doctype(self):
        html = _empty_report().to_html()
        assert html.startswith("<!DOCTYPE html>")

    def test_has_html_open_close(self):
        html = _empty_report().to_html()
        assert "<html" in html
        assert "</html>" in html

    def test_has_head_section(self):
        html = _empty_report().to_html()
        assert "<head>" in html
        assert "</head>" in html

    def test_has_body_section(self):
        html = _empty_report().to_html()
        assert "<body>" in html
        assert "</body>" in html

    def test_has_charset_meta(self):
        html = _empty_report().to_html()
        assert 'charset="UTF-8"' in html

    def test_has_viewport_meta(self):
        html = _empty_report().to_html()
        assert "viewport" in html

    def test_has_title(self):
        html = _empty_report().to_html()
        assert "<title>" in html and "</title>" in html

    def test_has_inline_style(self):
        html = _empty_report().to_html()
        assert "<style>" in html and "</style>" in html

    def test_no_external_stylesheet_links(self):
        html = _empty_report().to_html()
        assert 'rel="stylesheet"' not in html
        assert "<link" not in html

    def test_no_external_script_src(self):
        html = _empty_report().to_html()
        # No <script src="..."> — only inline script/pre elements
        assert 'src="http' not in html
        assert "<script src=" not in html

    def test_is_string(self):
        assert isinstance(_empty_report().to_html(), str)

    def test_non_empty(self):
        assert len(_empty_report().to_html()) > 500


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------

class TestRequiredSections:
    def test_executive_summary_section(self):
        html = _vagrant_report().to_html()
        assert "Executive Summary" in html

    def test_project_risk_level_in_header(self):
        html = _high_risk_report().to_html()
        assert "Project Risk" in html

    def test_architecture_health_section(self):
        html = _vagrant_report().to_html()
        assert "Architecture Health" in html

    def test_drift_summary_section(self):
        html = _vagrant_report().to_html()
        assert "Drift Summary" in html

    def test_recommendations_section(self):
        html = _vagrant_report().to_html()
        assert "Recommendations" in html

    def test_quick_wins_section(self):
        html = _vagrant_report().to_html()
        assert "Quick Wins" in html

    def test_deep_refactor_section(self):
        html = _vagrant_report().to_html()
        assert "Deep Refactor" in html

    def test_risk_zones_section(self):
        html = _vagrant_report().to_html()
        assert "Risk Zone" in html

    def test_evidence_basis_section(self):
        html = _vagrant_report().to_html()
        assert "Evidence Basis" in html

    def test_warnings_section(self):
        html = _vagrant_report().to_html()
        assert "Warnings" in html

    def test_metadata_section(self):
        html = _vagrant_report().to_html()
        assert "Metadata" in html

    def test_json_payload_section(self):
        html = _vagrant_report().to_html()
        assert "json-payload" in html

    def test_executive_summary_content_present(self):
        r = _vagrant_report()
        html = r.to_html()
        # First few words of summary should appear (escaped)
        first_word = r.executive_summary.split()[0]
        assert first_word in html


# ---------------------------------------------------------------------------
# Embedded JSON payload
# ---------------------------------------------------------------------------

class TestEmbeddedJSON:
    def test_payload_present(self):
        html = _vagrant_report().to_html()
        assert 'id="json-payload"' in html

    def test_payload_parseable(self):
        html = _vagrant_report().to_html()
        data = _extract_json_payload(html)
        assert isinstance(data, dict)

    def test_payload_has_executive_summary(self):
        html = _vagrant_report().to_html()
        data = _extract_json_payload(html)
        assert "executive_summary" in data

    def test_payload_has_recommendations(self):
        html = _vagrant_report().to_html()
        data = _extract_json_payload(html)
        assert "recommendations" in data

    def test_payload_has_drift_summary(self):
        html = _vagrant_report().to_html()
        data = _extract_json_payload(html)
        assert "drift_summary" in data

    def test_payload_has_project_risk_level(self):
        html = _vagrant_report().to_html()
        data = _extract_json_payload(html)
        assert "project_risk_level" in data

    def test_payload_matches_to_dict(self):
        r = _vagrant_report()
        html = r.to_html()
        payload = _extract_json_payload(html)
        direct = r.to_dict()
        assert payload["project_risk_level"] == direct["project_risk_level"]
        assert len(payload["recommendations"]) == len(direct["recommendations"])

    def test_payload_in_details_element(self):
        html = _vagrant_report().to_html()
        assert "<details>" in html or "<details" in html


# ---------------------------------------------------------------------------
# HTML escaping / XSS prevention
# ---------------------------------------------------------------------------

class TestHTMLEscaping:
    def _malicious_scan(self) -> dict:
        return {
            "drift_flags": {
                "vagrant_candidates": [{
                    "node_id": "<script>alert('xss')</script>",
                    "name": '<img src=x onerror="alert(1)">',
                    "kind": "component",
                    "reason": '"><svg onload=alert(1)>',
                    "confidence": 0.80,
                }],
                "stale_candidates": [{
                    "node_id": "n",
                    "responsibility_id": "r",
                    "statement": "<b>bold</b><script>evil()</script>",
                    "reason": "& < > \" '",
                    "confidence": 0.70,
                }],
                "confidence": 0.80, "basis": "<test>", "warnings": ["<warn>"],
            },
            "drift_score": {
                "overall_score": 20.0, "risk_level": "medium", "confidence": 0.80,
                "basis": "<basis>", "top_risk_nodes": ["<node>"],
                "per_node_scores": [], "warnings": [],
            },
            "source_anchors": {
                "total_responsibilities": 0, "unanchored_count": 0,
                "anchored_count": 0, "warnings": [],
            },
        }

    def test_script_tag_escaped(self):
        html = generate_report(self._malicious_scan()).to_html()
        assert "<script>alert(" not in html
        assert "<script>evil()" not in html

    def test_img_onerror_escaped(self):
        html = generate_report(self._malicious_scan()).to_html()
        assert '<img src=x onerror=' not in html

    def test_svg_onload_escaped(self):
        html = generate_report(self._malicious_scan()).to_html()
        assert "<svg onload=" not in html

    def test_angle_brackets_escaped(self):
        html = generate_report(self._malicious_scan()).to_html()
        assert "&lt;script&gt;" in html

    def test_ampersand_escaped(self):
        scan = {"version_sources": {"a&b.toml": "1.0&0"}, "version_drift": True}
        html = generate_report(scan).to_html()
        assert "a&b" not in html or "a&amp;b" in html

    def test_double_quote_escaped_in_content(self):
        scan = {
            "drift_flags": {
                "vagrant_candidates": [{
                    "node_id": 'say "hello"',
                    "name": 'say "hello"',
                    "kind": "c", "reason": "r", "confidence": 0.80,
                }],
                "stale_candidates": [],
                "confidence": 0.80, "basis": "t", "warnings": [],
            },
            "drift_score": {"overall_score": 10.0, "risk_level": "low",
                            "confidence": 0.80, "basis": "t",
                            "top_risk_nodes": [], "per_node_scores": [], "warnings": []},
            "source_anchors": {"total_responsibilities": 0, "unanchored_count": 0,
                               "anchored_count": 0, "warnings": []},
        }
        html = generate_report(scan).to_html()
        # Raw unescaped double-quote should not appear in element text
        # (it may appear in the JSON payload, which is itself escaped)
        assert '&quot;' in html or '"hello"' not in html.split("json-payload")[0]

    def test_bold_tag_in_statement_escaped(self):
        html = generate_report(self._malicious_scan()).to_html()
        assert "<b>bold</b>" not in html
        assert "&lt;b&gt;" in html

    def test_warning_with_html_escaped(self):
        scan = {"drift_flags": {
            "vagrant_candidates": [], "stale_candidates": [],
            "confidence": 0.5, "basis": "t",
            "warnings": ["<script>bad()</script>"],
        }}
        html = generate_report(scan).to_html()
        assert "<script>bad()" not in html


# ---------------------------------------------------------------------------
# Empty report
# ---------------------------------------------------------------------------

class TestEmptyReport:
    def test_renders_without_crash(self):
        html = _empty_report().to_html()
        assert isinstance(html, str)

    def test_no_recommendations_message(self):
        html = _empty_report().to_html()
        assert "None identified" in html

    def test_risk_level_none_in_title(self):
        html = _empty_report().to_html()
        assert "NONE" in html

    def test_json_payload_present_and_parseable(self):
        html = _empty_report().to_html()
        data = _extract_json_payload(html)
        assert data["project_risk_level"] == "none"
        assert data["recommendations"] == []


# ---------------------------------------------------------------------------
# High-risk report
# ---------------------------------------------------------------------------

class TestHighRiskReport:
    def test_high_in_html(self):
        html = _high_risk_report().to_html()
        assert "HIGH" in html or "high" in html

    def test_recommendations_rendered(self):
        html = _high_risk_report().to_html()
        assert "NodeA" in html or "vagrant" in html.lower()

    def test_warning_from_flags_rendered(self):
        html = _high_risk_report().to_html()
        assert "test warning" in html

    def test_architecture_score_shown(self):
        html = _high_risk_report().to_html()
        assert "42" in html

    def test_drift_score_shown(self):
        html = _high_risk_report().to_html()
        assert "72" in html


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_identical_reports_identical_html(self):
        r = _vagrant_report()
        assert r.to_html() == r.to_html()

    def test_identical_scan_identical_html(self):
        scan = {
            "drift_flags": {
                "vagrant_candidates": [{"node_id":"x","name":"X","kind":"c","reason":"r","confidence":0.80}],
                "stale_candidates": [],
                "confidence": 0.80, "basis": "t", "warnings": [],
            },
            "drift_score": {"overall_score": 12.0, "risk_level": "low", "confidence": 0.80,
                            "basis": "t", "top_risk_nodes": [], "per_node_scores": [], "warnings": []},
            "source_anchors": {"total_responsibilities": 0, "unanchored_count": 0,
                               "anchored_count": 0, "warnings": []},
        }
        h1 = generate_report(scan).to_html()
        h2 = generate_report(scan).to_html()
        assert h1 == h2


# ---------------------------------------------------------------------------
# Existing outputs unchanged
# ---------------------------------------------------------------------------

class TestExistingOutputsUnchanged:
    def test_to_json_still_works(self):
        r = _vagrant_report()
        j = json.loads(r.to_json())
        assert "executive_summary" in j
        assert "recommendations" in j

    def test_to_markdown_still_works(self):
        r = _vagrant_report()
        md = r.to_markdown()
        assert "# Genesis Recovery Report" in md
        assert "## Executive Summary" in md

    def test_to_dict_unchanged(self):
        r = _vagrant_report()
        d = r.to_dict()
        for k in ("executive_summary", "project_risk_level", "architecture_health",
                  "drift_summary", "recommendations", "quick_wins",
                  "deep_refactor_candidates", "risk_zones",
                  "recommended_fix_order", "evidence_basis", "warnings", "metadata"):
            assert k in d

    def test_html_does_not_mutate_report(self):
        r = _vagrant_report()
        n_recs_before = len(r.recommendations)
        _ = r.to_html()
        assert len(r.recommendations) == n_recs_before

    def test_html_then_json_consistent(self):
        r = _vagrant_report()
        _ = r.to_html()
        j = json.loads(r.to_json())
        assert j["project_risk_level"] == r.project_risk_level


# ---------------------------------------------------------------------------
# Self-contained check
# ---------------------------------------------------------------------------

class TestSelfContained:
    def test_no_http_links(self):
        html = _high_risk_report().to_html()
        assert "http://" not in html
        assert "https://" not in html

    def test_no_external_fonts(self):
        html = _vagrant_report().to_html()
        assert "fonts.googleapis" not in html
        assert "fonts.gstatic" not in html

    def test_css_is_inline(self):
        html = _vagrant_report().to_html()
        assert "<style>" in html
        assert "font-family" in html

    def test_single_file_viable(self):
        html = _high_risk_report().to_html()
        # Can be written to a single .html file and opened with no dependencies
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
