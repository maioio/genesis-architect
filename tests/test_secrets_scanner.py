"""Tests for secrets_scanner.py — the third leg of `genesis harden`
(STRIDE + OWASP + secrets scan). Offline, regex-based, no network calls."""

from __future__ import annotations

from genesis_architect_pro.secrets_scanner import _generate_secrets_doc, scan_secrets


def test_detects_aws_key_and_redacts(tmp_path):
    (tmp_path / "config.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAABCDEFGHIJKLMNOP"\n', encoding="utf-8",
    )
    findings = scan_secrets(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule == "AWS Access Key ID"
    assert findings[0].severity == "high"
    assert "AKIAABCDEFGHIJKLMNOP" not in findings[0].redacted
    assert findings[0].redacted.startswith("AKIA")
    assert findings[0].redacted.endswith("MNOP")
    assert "*" in findings[0].redacted


def test_detects_private_key_block(tmp_path):
    (tmp_path / "id_rsa").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    findings = scan_secrets(tmp_path)
    assert any(f.rule == "Private Key Block" for f in findings)


def test_generic_assignment_flagged_as_medium(tmp_path):
    (tmp_path / "settings.py").write_text(
        'api_key = "sk_abcdefghij1234567890"\n', encoding="utf-8",
    )
    findings = scan_secrets(tmp_path)
    assert any(f.severity == "medium" for f in findings)


def test_placeholder_values_are_not_flagged(tmp_path):
    (tmp_path / ".env.example").write_text(
        'API_KEY="your-key-here"\n'
        'AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX\n',
        encoding="utf-8",
    )
    findings = scan_secrets(tmp_path)
    assert findings == []


def test_no_secrets_found_is_honest_not_fabricated(tmp_path):
    (tmp_path / "readme.md").write_text("Nothing to see here.\n", encoding="utf-8")
    findings = scan_secrets(tmp_path)
    assert findings == []
    doc = _generate_secrets_doc(tmp_path)
    assert "no likely secrets" in doc.lower()


def test_skips_binary_and_vendor_dirs(tmp_path):
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "lib.js").write_text(
        'const key = "AKIAABCDEFGHIJKLMNOP";\n', encoding="utf-8",
    )
    findings = scan_secrets(tmp_path)
    assert findings == []


def test_report_never_contains_raw_secret(tmp_path):
    (tmp_path / "config.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAABCDEFGHIJKLMNOP"\n', encoding="utf-8",
    )
    doc = _generate_secrets_doc(tmp_path)
    assert "AKIAABCDEFGHIJKLMNOP" not in doc
    assert "AKIA" in doc  # redacted prefix still visible for triage
