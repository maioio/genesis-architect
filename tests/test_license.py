"""Tests for the Ed25519 license gate.

These do not need the private signing key for the negative cases. The
positive case is covered by the rest of the suite running under a real
GENESIS_PRO_LICENSE; here we assert that forgery and tampering fail.
"""

import pytest

from genesis_architect_pro.license import (
    LicenseError,
    is_licensed,
    parse_key,
    require_license,
)


def test_empty_key_rejected():
    assert parse_key("") is None
    assert parse_key("notakey") is None


def test_wrong_prefix_rejected():
    assert parse_key("bad_eyJzdWIiOiJ4In0.AAAA") is None


def test_forged_placeholder_rejected():
    # Old placeholder scheme (plain hex) must no longer pass.
    assert parse_key("gpro_deadbeefdeadbeefdeadbeef") is None


def test_tampered_signature_rejected():
    fake = "gpro_eyJzdWIiOiJhdHRhY2tlciJ9.AAAAfakesig"
    assert parse_key(fake) is None


def test_require_license_raises_without_key(monkeypatch):
    monkeypatch.delenv("GENESIS_PRO_LICENSE", raising=False)
    monkeypatch.setattr("genesis_architect_pro.license._read_key", lambda: None)
    assert is_licensed() is False
    with pytest.raises(LicenseError):
        require_license("test feature")
