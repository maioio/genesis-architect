"""License gating for Genesis Architect Pro (Ed25519-signed keys).

A license key is:  gpro_<b64url(payload_json)>.<b64url(signature)>

The payload is signed offline by the holder's private key (kept out of
this package, in a separate secrets store). The client verifies the
signature against the embedded PUBLIC key below. Without the private key,
a valid key cannot be forged, so the client check is safe to ship.

Payload fields (JSON):
    sub   - licensee id / email
    exp   - optional unix expiry (int); omitted = perpetual
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ENV_VAR = "GENESIS_PRO_LICENSE"
LICENSE_FILE = Path.home() / ".genesis" / "pro_license"
_KEY_PREFIX = "gpro_"

# Public verification key (safe to embed). Private signing key is NEVER here.
PUBLIC_KEY_B64 = "ps2botOL9YB30y71QfPdvBWGShiE4wM4qfBo54aB5lk="


class LicenseError(RuntimeError):
    """Raised when no valid Pro license is present."""


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))


def _read_key() -> str | None:
    key = os.environ.get(ENV_VAR)
    if key:
        return key.strip()
    if LICENSE_FILE.is_file():
        return LICENSE_FILE.read_text(encoding="utf-8").strip()
    return None


def parse_key(key: str) -> dict | None:
    """Verify the signature and expiry. Returns payload dict, or None."""
    if not key or not key.startswith(_KEY_PREFIX):
        return None
    body = key[len(_KEY_PREFIX):]
    if "." not in body:
        return None
    payload_b64, sig_b64 = body.split(".", 1)
    try:
        payload_raw = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, TypeError):
        return None
    try:
        _public_key().verify(signature, payload_raw)
    except InvalidSignature:
        return None
    try:
        payload = json.loads(payload_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        return None
    return payload


def is_licensed() -> bool:
    key = _read_key()
    return key is not None and parse_key(key) is not None


def require_license(feature: str = "this feature") -> None:
    """Gate a Pro feature. Raises LicenseError if unlicensed."""
    if is_licensed():
        return
    raise LicenseError(
        f"Genesis Architect Pro is required for {feature}.\n"
        f"Set {ENV_VAR}=<your-key> or place a key at {LICENSE_FILE}.\n"
        f"Get a license: https://github.com/maioio/genesis-architect"
    )
