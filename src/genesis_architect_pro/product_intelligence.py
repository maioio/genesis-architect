"""
Product Intelligence Engine for Genesis Architect (Pro).

Anonymous, opt-in product telemetry. This is the feedback loop that tells the
business which engines earn their keep and where users churn - WITHOUT ever
touching the customer's code, files, secrets, or identity.

Constitution 09 (Privacy & Telemetry) is binding here:

  1. Default is OFF. No pre-checked opt-in. Nothing is recorded until the user
     explicitly consents.
  2. Consent is revocable at any time.
  3. There is a way to see exactly what would be sent (`describe_payload`).
  4. With consent OFF the product is fully functional. Telemetry is never a gate.
  5. ANONYMOUS only: no account, project, machine, or path identifier that ties
     an event back to a person or codebase.

What is collected (only with consent):
  - which workflow / engine / research profile was used
  - whether a recommendation was accepted or rejected
  - where a user got stuck (a named friction point)
  - how long a step took (coarse duration bucket)
  - which screens go unused

What is NEVER collected (enforced by a sanitizer, not by trust):
  - source code, project files, file paths, project names
  - secrets / API keys / tokens
  - private prompts, business documents
  - any free-form string that could carry identifying content

Storage is local-first: events append to `.genesis/telemetry/events.jsonl`.
A separate transport may later upload them, but collection and upload are
decoupled - this module only records locally and lets the user inspect/clear.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow-list: the ONLY event shapes telemetry understands.
# Anything not on this list is dropped. This is the privacy contract in code.
# ---------------------------------------------------------------------------

# event name -> allowed field names (every field value is further sanitized).
_ALLOWED_EVENTS: dict[str, set[str]] = {
    "engine_used": {"engine", "tier"},
    "workflow_chosen": {"workflow"},
    "research_profile_used": {"profile"},
    "recommendation": {"decision", "engine"},          # decision: accepted|rejected
    "friction_point": {"where"},                        # a NAMED, enumerated point
    "step_duration": {"step", "bucket"},               # bucket: coarse, e.g. "1-5s"
    "screen_view": {"screen"},
}

# Values must be short, lowercase, enum-like tokens. Anything that looks like
# free text, a path, a secret, or an identifier is rejected.
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,63}$")

# A stored install_id is only ever a uuid4 hex (32 lowercase hex chars).
_VALID_INSTALL_ID = re.compile(r"^[0-9a-f]{32}$")

# Obvious sensitive-looking substrings -> hard reject even if token-shaped.
_FORBIDDEN_SUBSTR = (
    "/", "\\", "@", ":", "http", "key", "token", "secret", "password",
    "passwd", "bearer", "ssh", "api", "c:", "users", ".com", ".py", ".env",
)

# Common credential prefixes -> hard reject (sk-..., ghp_..., pk-..., AKIA...).
_FORBIDDEN_PREFIX = ("sk-", "sk_", "pk-", "pk_", "ghp_", "gho_", "ghs_",
                     "xox", "akia", "aiza", "ya29")


def _looks_like_secret(low: str) -> bool:
    """Heuristic for high-entropy credential-shaped tokens. Our legitimate values
    are dictionary-like enums (recovery, c4, accepted). A secret is long and
    mixes digits with letters in a way enums don't."""
    if low.startswith(_FORBIDDEN_PREFIX):
        return True
    if "-" in low or "_" in low or "." in low:
        return False  # structured enum-ish tokens (step_duration, 1-5s) are fine
    has_digit = any(c.isdigit() for c in low)
    has_alpha = any(c.isalpha() for c in low)
    # A bare run of mixed letters+digits longer than a normal word == suspicious.
    return len(low) >= 8 and has_digit and has_alpha


def _is_safe_token(value: object) -> bool:
    """A value is safe only if it is a short enum-like token with no sensitive
    markers. Numbers are allowed (and coerced to str by the caller)."""
    if not isinstance(value, str):
        return False
    if not _TOKEN_RE.match(value):
        return False
    low = value.lower()
    if any(s in low for s in _FORBIDDEN_SUBSTR):
        return False
    return not _looks_like_secret(low)


# ---------------------------------------------------------------------------
# Config (consent) - persisted, default OFF
# ---------------------------------------------------------------------------

CONSENT_PROMPT = (
    "Help improve Genesis?\n"
    "Genesis can anonymously collect feature usage, workflow patterns and "
    "product feedback.\n"
    "No code. No project data. No secrets. Only anonymous product telemetry.\n"
    "[Yes]  [No]"
)


@dataclass
class TelemetryConfig:
    enabled: bool = False          # default OFF - binding
    install_id: str = ""           # random, anonymous, not tied to user/machine
    decided: bool = False          # whether the user has been asked & answered

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "install_id": self.install_id,
                "decided": self.decided}

    @classmethod
    def from_dict(cls, d: dict) -> "TelemetryConfig":
        # install_id must be a 32-char hex (uuid4 hex) or empty. Anything else is
        # an injected/tampered value and is discarded - it must never become a
        # carrier for an identifier or secret (defense-in-depth, not trust).
        raw_id = str(d.get("install_id", ""))
        install_id = raw_id if _VALID_INSTALL_ID.match(raw_id) else ""
        return cls(
            enabled=bool(d.get("enabled", False)),
            install_id=install_id,
            decided=bool(d.get("decided", False)),
        )


def _telemetry_dir(project_root: Path) -> Path:
    return Path(project_root) / ".genesis" / "telemetry"


def _config_path(project_root: Path) -> Path:
    return _telemetry_dir(project_root) / "config.json"


def _events_path(project_root: Path) -> Path:
    return _telemetry_dir(project_root) / "events.jsonl"


def load_config(project_root: Path | str = ".") -> TelemetryConfig:
    p = _config_path(Path(project_root))
    if not p.exists():
        return TelemetryConfig()
    try:
        return TelemetryConfig.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return TelemetryConfig()


def _save_config(project_root: Path, cfg: TelemetryConfig) -> None:
    p = _config_path(Path(project_root))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Consent management
# ---------------------------------------------------------------------------

def set_consent(enabled: bool, project_root: Path | str = ".") -> TelemetryConfig:
    """Record the user's explicit choice. Generates an anonymous install_id the
    first time telemetry is turned on (never before)."""
    root = Path(project_root)
    cfg = load_config(root)
    cfg.enabled = bool(enabled)
    cfg.decided = True
    if cfg.enabled and not cfg.install_id:
        cfg.install_id = uuid.uuid4().hex  # random; not derived from anything
    _save_config(root, cfg)
    return cfg


def revoke_consent(project_root: Path | str = ".") -> TelemetryConfig:
    """Turn telemetry off. Existing local events are kept until the user clears
    them (see clear_events); revoking only stops further collection."""
    return set_consent(False, project_root)


def is_enabled(project_root: Path | str = ".") -> bool:
    return load_config(project_root).enabled


def needs_consent_prompt(project_root: Path | str = ".") -> bool:
    """True only if the user has never been asked. Used to show the prompt once."""
    return not load_config(project_root).decided


# ---------------------------------------------------------------------------
# Event recording
# ---------------------------------------------------------------------------

@dataclass
class SanitizeResult:
    ok: bool
    event: dict | None = None
    dropped_fields: list[str] = field(default_factory=list)
    reason: str = ""


def sanitize_event(name: str, fields: dict | None = None) -> SanitizeResult:
    """Validate an event against the allow-list and reject anything unsafe.

    This is pure (no I/O) so it can be unit-tested and reused by a UI preview.
    A single bad field does not poison the whole event - it is dropped and
    reported; but an unknown event name or an unknown field is rejected outright
    (fail-closed), because an unrecognized shape is exactly what a leak looks
    like.
    """
    fields = fields or {}
    if name not in _ALLOWED_EVENTS:
        return SanitizeResult(ok=False, reason=f"unknown event '{name}'")

    allowed = _ALLOWED_EVENTS[name]
    unknown = set(fields) - allowed
    if unknown:
        return SanitizeResult(
            ok=False, reason=f"unknown field(s) for '{name}': {sorted(unknown)}")

    clean: dict[str, str] = {}
    dropped: list[str] = []
    for key, value in fields.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # reject non-finite floats (nan/inf) - they are not enum values
            if isinstance(value, float) and value != value or value in (
                    float("inf"), float("-inf")):
                dropped.append(key)
                continue
            value = str(value)
        if _is_safe_token(value):
            clean[key] = value  # type: ignore[assignment]
        else:
            dropped.append(key)

    return SanitizeResult(ok=True, event={"event": name, "fields": clean},
                          dropped_fields=dropped)


def record_event(name: str, fields: dict | None = None,
                 project_root: Path | str = ".") -> bool:
    """Record one anonymous event IF consent is enabled. Returns True if written.

    No-op (returns False) when telemetry is off - the product never depends on
    this succeeding. Never raises on I/O problems (honesty: telemetry failure is
    invisible to the user and never blocks work).
    """
    root = Path(project_root)
    cfg = load_config(root)
    if not cfg.enabled:
        return False

    result = sanitize_event(name, fields)
    if not result.ok or result.event is None:
        return False  # fail closed: if we can't prove it's safe, we don't send

    record = {
        "v": 1,
        "ts": int(time.time()),
        "install_id": cfg.install_id,  # anonymous random id
        **result.event,
    }
    try:
        p = _events_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Transparency: let the user see and clear what is stored
# ---------------------------------------------------------------------------

def read_events(project_root: Path | str = ".") -> list[dict]:
    """Return all locally-stored telemetry events so the user can inspect
    exactly what would be sent. Satisfies Constitution 09 rule 2/3."""
    p = _events_path(Path(project_root))
    if not p.exists():
        return []
    events: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a corrupt line, keep the rest
    except OSError:
        return []
    return events


def describe_payload(project_root: Path | str = ".") -> str:
    """Human-readable summary of what telemetry holds locally. This is the
    'show me what you send' surface."""
    cfg = load_config(project_root)
    events = read_events(project_root)
    if not cfg.enabled and not events:
        return "Telemetry is OFF. Nothing is collected or stored."
    counts: dict[str, int] = {}
    unrecognized = 0
    for e in events:
        name = e.get("event", "?")
        # Only ever display names we recognize. An injected/foreign line is
        # counted but never echoed verbatim - the transparency surface must not
        # become an output channel for attacker-controlled strings.
        if name in _ALLOWED_EVENTS:
            counts[name] = counts.get(name, 0) + 1
        else:
            unrecognized += 1
    lines = [
        f"Telemetry: {'ON' if cfg.enabled else 'OFF'} "
        f"(anonymous install id: {cfg.install_id or 'none'})",
        f"Locally stored events: {len(events)}",
    ]
    for name in sorted(counts):
        lines.append(f"  - {name}: {counts[name]}")
    if unrecognized:
        lines.append(f"  - (unrecognized/foreign lines, not displayed): {unrecognized}")
    lines.append("Never stored: code, file paths, project names, secrets, prompts.")
    return "\n".join(lines)


def clear_events(project_root: Path | str = ".") -> int:
    """Delete all locally-stored events. Returns how many were removed."""
    p = _events_path(Path(project_root))
    n = len(read_events(project_root))
    try:
        if p.exists():
            p.unlink()
    except OSError:
        return 0
    return n
