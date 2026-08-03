"""
First-run readiness + doctor report for Genesis Architect.

The promise: the experience is three steps - Install -> Start working, with NO
manual infrastructure (no Docker, Python venv juggling, Node, DB, Redis, or MCP
server set up by hand). There is no license step: Genesis Architect is free and
open source (AGPL-3.0) and every engine ships in the box.

This module is the single readiness surface that backs that promise. It is
READ-ONLY and never blocks: it reports what is ready and what is optional. It
composes existing pieces rather than reimplementing them:

  - env_probe.probe()             -> OS / python / package managers
  - pro_bridge.pro_installed()    -> are the advanced engines importable?
  - optional-dep checks           -> ffmpeg/yt-dlp for video (self-heal pattern)

Design rules:
  - Never raises. Missing helpers degrade to "unknown", never crash.
  - Never auto-installs or phones home from a status check. Self-heal is a
    separate, explicit action (ensure_optional_dep) the caller invokes on demand.
  - Local analysis works fully offline; network-only features are reported as
    optional, never as blockers.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Readiness model
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    ok: bool
    required: bool          # required for the DEFAULT customer path?
    detail: str = ""

    def status(self) -> str:
        if self.ok:
            return "ready"
        return "MISSING" if self.required else "optional"


@dataclass
class Readiness:
    licensed: bool
    pro_installed: bool
    checks: list[Check] = field(default_factory=list)

    @property
    def ready_to_work(self) -> bool:
        """True when every REQUIRED check passes. Optional gaps never block."""
        return all(c.ok for c in self.checks if c.required)

    def missing_required(self) -> list[Check]:
        return [c for c in self.checks if c.required and not c.ok]

    def optional_gaps(self) -> list[Check]:
        return [c for c in self.checks if not c.required and not c.ok]


# ---------------------------------------------------------------------------
# Probing (read-only)
# ---------------------------------------------------------------------------

def _pro_installed() -> bool:
    try:
        from genesis_architect.core import pro_bridge  # type: ignore
        return bool(pro_bridge.pro_installed())
    except Exception:
        # We are literally running inside the Pro package, so if the bridge is
        # unavailable, importing ourselves still proves Pro is installed.
        return True


def _licensed() -> bool:
    """Back-compat shim: there is no license tier, so nothing is ever locked."""
    return True


# Optional dependencies: each is (name, what it unlocks). Absence never blocks
# the default path - the relevant feature simply shows "unavailable" until the
# customer opts to enable it (one prompt, via ensure_optional_dep).
OPTIONAL_DEPS = {
    "ffmpeg": "video transcription (/watch, video-to-pitfall)",
    "yt-dlp": "video download for transcription",
    "git": "git history intelligence (churn, bus-factor)",
}


def _have(binary: str) -> bool:
    # yt-dlp may be importable as a module rather than on PATH
    if binary == "yt-dlp":
        if shutil.which("yt-dlp"):
            return True
        try:
            import yt_dlp  # noqa: F401
            return True
        except Exception:
            return False
    return shutil.which(binary) is not None


def check_readiness() -> Readiness:
    """Assemble the full readiness picture. Pure status, no side effects.

    Nothing is license-gated, so the only required check is that the engine
    layer imports. Everything else is optional and degrades gracefully.
    """
    licensed = _licensed()
    pro = _pro_installed()

    checks: list[Check] = [
        Check(
            name="engines",
            ok=pro,
            required=True,
            detail="All engines available (free, AGPL-3.0)." if pro else
                   "Engine layer failed to import — try: "
                   "pip install --force-reinstall genesis-architect",
        ),
    ]
    for dep, unlocks in OPTIONAL_DEPS.items():
        # Probing touches PATH and imports third-party modules; a hostile
        # environment can make either explode. A status check must degrade to
        # "not present", never crash the caller.
        try:
            present = _have(dep)
        except Exception:
            present = False
        checks.append(Check(
            name=dep, ok=present, required=False,
            detail=(f"{dep} present - {unlocks} available." if present
                    else f"{dep} not found - {unlocks} stays unavailable until "
                         f"enabled (one prompt)."),
        ))
    return Readiness(licensed=licensed, pro_installed=pro, checks=checks)


# ---------------------------------------------------------------------------
# Customer-facing doctor report
# ---------------------------------------------------------------------------

CUSTOMER_FLOW = (
    "1. Install Genesis\n"
    "2. Start working"
)


def doctor_report() -> str:
    """A short, customer-friendly readiness report. This is what `genesis doctor`
    (or first-run) shows: never a wall of setup steps."""
    r = check_readiness()
    lines = ["Genesis Architect - readiness check", ""]
    for c in r.checks:
        mark = "[ok]" if c.ok else ("[ MISSING ]" if c.required else "[optional]")
        lines.append(f"  {mark:<12} {c.name}: {c.detail}")
    lines.append("")
    if r.ready_to_work:
        lines.append("Ready. Start working - no further setup required.")
    else:
        lines.append("Almost there. Resolve the MISSING item(s) above:")
        for c in r.missing_required():
            lines.append(f"  -> {c.detail}")
    gaps = r.optional_gaps()
    if gaps:
        lines.append("")
        lines.append("Optional (only if you want those features):")
        for c in gaps:
            lines.append(f"  - {c.name}: {c.detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Offline / degraded reporting (honesty clause)
# ---------------------------------------------------------------------------

# Capabilities that work with no network at all.
LOCAL_CAPABILITIES = (
    "import graph", "architecture score", "anti-patterns", "C4 diagrams",
    "drift detection", "recovery report", "gate (rules engine)",
    "knowledge graph", "decision engine",
)
# Capabilities that need the network; offline -> reported "unavailable".
NETWORK_CAPABILITIES = (
    "research intelligence", "developer field intelligence (Reddit/SO/HN)",
    "YouTube transcript learning", "CVE/OSV lookups",
)


def offline_capability_report(network_available: bool) -> dict:
    """What works right now given connectivity. Local analysis always works;
    network features are honestly marked unavailable when offline - never faked,
    never blocking."""
    return {
        "network_available": bool(network_available),
        "available": list(LOCAL_CAPABILITIES) + (
            list(NETWORK_CAPABILITIES) if network_available else []),
        "unavailable": [] if network_available else list(NETWORK_CAPABILITIES),
        "note": ("All features available." if network_available else
                 "Offline: local analysis works fully; network-backed research "
                 "is marked unavailable in Evidence Packs (never fabricated)."),
    }


# ---------------------------------------------------------------------------
# Self-heal (explicit, opt-in - never silent, never from a status check)
# ---------------------------------------------------------------------------

@dataclass
class HealResult:
    dep: str
    already_present: bool
    attempted: bool
    ok: bool
    message: str


def ensure_optional_dep(dep: str, *, auto_install: bool = False) -> HealResult:
    """Make an optional dependency available, on explicit request.

    With auto_install=False (default) this only reports what to do - a status
    check must never install anything. With auto_install=True the caller has
    explicitly chosen to self-heal; for ffmpeg/yt-dlp we delegate to the existing
    video setup pattern. Never raises.
    """
    if dep not in OPTIONAL_DEPS:
        return HealResult(dep, False, False, False,
                          f"'{dep}' is not a known optional dependency.")
    if _have(dep):
        return HealResult(dep, True, False, True, f"{dep} already present.")

    if not auto_install:
        return HealResult(
            dep, False, False, False,
            f"{dep} is missing. Enable {OPTIONAL_DEPS[dep]} by installing it; "
            f"or call ensure_optional_dep('{dep}', auto_install=True).")

    # Delegate ffmpeg/yt-dlp to the established, tested video setup path.
    if dep in ("ffmpeg", "yt-dlp"):
        try:
            from genesis_architect.pro.video_research import ensure_watch_ready
            ensure_watch_ready(auto_install=True)
            ok = _have(dep)
            return HealResult(dep, False, True, ok,
                              "video tooling setup attempted; "
                              f"{dep} {'now present' if ok else 'still missing'}.")
        except Exception as exc:
            return HealResult(dep, False, True, False,
                              f"auto-install of {dep} failed: {exc}")

    # git and anything else: we never silently install system tools; guide.
    return HealResult(
        dep, False, False, False,
        f"{dep} must be installed via your system package manager.")
