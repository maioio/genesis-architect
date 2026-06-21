"""License gating for Genesis Architect Pro.

Pro engines must call require_license() before doing real work. The check
is intentionally simple and offline-first: a signed key in the environment
or a license file. Replace verify_key() with real signature verification
(e.g. Ed25519 over an issued payload) before commercial launch.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

ENV_VAR = "GENESIS_PRO_LICENSE"
LICENSE_FILE = Path.home() / ".genesis" / "pro_license"

# Placeholder verification secret. Before launch, swap this whole scheme for
# asymmetric signature verification so keys cannot be forged from the client.
_KEY_PREFIX = "gpro_"


class LicenseError(RuntimeError):
    """Raised when no valid Pro license is present."""


def _read_key() -> str | None:
    key = os.environ.get(ENV_VAR)
    if key:
        return key.strip()
    if LICENSE_FILE.is_file():
        return LICENSE_FILE.read_text(encoding="utf-8").strip()
    return None


def verify_key(key: str) -> bool:
    """Validate a license key.

    Current scheme (placeholder): key is 'gpro_' + hex digest. This proves
    the gate works end to end; replace with real crypto before charging.
    """
    if not key or not key.startswith(_KEY_PREFIX):
        return False
    payload = key[len(_KEY_PREFIX):]
    if len(payload) < 16:
        return False
    # Accept any well-formed hex payload for now (offline dev mode).
    try:
        int(payload, 16)
        return True
    except ValueError:
        return False


def is_licensed() -> bool:
    key = _read_key()
    return bool(key) and verify_key(key)


def require_license(feature: str = "this feature") -> None:
    """Gate a Pro feature. Raises LicenseError if unlicensed."""
    if is_licensed():
        return
    raise LicenseError(
        f"Genesis Architect Pro is required for {feature}.\n"
        f"Set {ENV_VAR}=<your-key> or place a key at {LICENSE_FILE}.\n"
        f"Get a license: https://github.com/maioio/genesis-architect"
    )


def dev_key() -> str:
    """Generate a well-formed offline dev key (not for production)."""
    digest = hashlib.sha256(b"genesis-pro-dev").hexdigest()
    return _KEY_PREFIX + digest
