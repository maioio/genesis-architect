"""
Cross-Session Memory for Genesis Architect.

Auto-loads research context at the start of a new session so users
never have to re-research a project they already worked on.

On session start Genesis calls restore_session() which:
1. Reads .genesis/state.json for last phase + timestamp
2. Loads vault cache for the vision
3. Announces what was restored ("Context restored - N repos, M pitfalls")
4. Returns a SessionContext the skill uses to skip completed phases

Also handles saving progress so restore works next time.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from genesis_architect.core import vault as _vault


# ---------------------------------------------------------------------------
# Session context
# ---------------------------------------------------------------------------

@dataclass
class SessionContext:
    vision: str
    last_phase: str          # "phase2" | "phase3" | "phase4" | "phase5" | "phase6"
    last_phase_ts: float     # unix timestamp
    repo_count: int
    deep_count: int
    pitfall_count: int
    research_quality: str    # FULL | PARTIAL | THIN
    vault_hit: bool          # True if loaded from vault cache
    restored: bool           # True if this is a restored session

    def age_hours(self) -> float:
        return (time.time() - self.last_phase_ts) / 3600

    def announce(self) -> str:
        """Generate the announcement string for SKILL.md Phase 7 resume flow."""
        if not self.restored:
            return ""
        age = self.age_hours()
        age_str = f"{age:.0f}h ago" if age < 48 else f"{age / 24:.0f} days ago"
        lines = [
            f"Context restored ({age_str}) - {self.repo_count} repos, "
            f"{self.deep_count} deep-analyzed, {self.pitfall_count} pitfalls. "
            f"Research quality: {self.research_quality}. "
            f"Last phase: {self.last_phase}.",
        ]
        if self.last_phase in ("phase2", "phase3"):
            lines.append("Next: continue from Phase 4 (Pitfall Identification).")
        elif self.last_phase == "phase4":
            lines.append("Next: Phase 5 (Architecture Choice).")
        elif self.last_phase == "phase5":
            lines.append("Next: Phase 6 (Genesis Build).")
        elif self.last_phase == "phase6":
            lines.append("Scaffold complete. Entering Companion Mode.")
        return " ".join(lines)


_EMPTY = SessionContext(
    vision="", last_phase="", last_phase_ts=0,
    repo_count=0, deep_count=0, pitfall_count=0,
    research_quality="THIN", vault_hit=False, restored=False,
)


# ---------------------------------------------------------------------------
# State file I/O
# ---------------------------------------------------------------------------

def _state_path(project_root: Path) -> Path:
    return project_root / ".genesis" / "state.json"


def _load_state(project_root: Path) -> dict:
    p = _state_path(project_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(project_root: Path, data: dict) -> None:
    p = _state_path(project_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_state(project_root)
    existing.update(data)
    p.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def restore_session(project_root: Path | str = ".") -> SessionContext:
    """
    Attempt to restore a previous Genesis session.
    Returns an empty SessionContext (restored=False) if nothing found.
    Called at the start of every Companion Mode session.
    """
    root = Path(project_root)
    state = _load_state(root)

    if not state:
        return _EMPTY

    vision = state.get("vision", "")
    last_phase = state.get("last_phase", "")
    last_ts = state.get("last_phase_ts", 0)

    if not vision or not last_phase:
        return _EMPTY

    # Try to load research summary from vault
    vault_entry = _vault.get(f"research:{vision.lower().strip()[:80]}", root)
    vault_hit = vault_entry is not None

    repo_count = state.get("repo_count", 0)
    deep_count = state.get("deep_count", 0)
    pitfall_count = state.get("pitfall_count", 0)
    quality = state.get("research_quality", "THIN")

    return SessionContext(
        vision=vision,
        last_phase=last_phase,
        last_phase_ts=last_ts,
        repo_count=repo_count,
        deep_count=deep_count,
        pitfall_count=pitfall_count,
        research_quality=quality,
        vault_hit=vault_hit,
        restored=True,
    )


def no_session_message() -> str:
    return (
        "No prior Genesis session found. "
        "Start with `genesis init [description]` or `genesis recover .` for an existing project."
    )


# ---------------------------------------------------------------------------
# Save progress (called by genesis_state.py equivalents)
# ---------------------------------------------------------------------------

def save_phase2(project_root: Path, vision: str, repo_count: int,
                deep_count: int, quality: str) -> None:
    _save_state(project_root, {
        "vision": vision,
        "last_phase": "phase2",
        "last_phase_ts": time.time(),
        "repo_count": repo_count,
        "deep_count": deep_count,
        "research_quality": quality,
    })


def save_phase4(project_root: Path, pitfall_count: int) -> None:
    _save_state(project_root, {
        "last_phase": "phase4",
        "last_phase_ts": time.time(),
        "pitfall_count": pitfall_count,
    })


def save_phase6(project_root: Path) -> None:
    _save_state(project_root, {
        "last_phase": "phase6",
        "last_phase_ts": time.time(),
    })


# ---------------------------------------------------------------------------
# Companion Mode: video pitfall persistence
# ---------------------------------------------------------------------------

def save_video_pitfalls(project_root: Path, source_url: str, count: int) -> None:
    """Record that video pitfalls were extracted and added to PITFALLS.md."""
    state = _load_state(project_root)
    existing = state.get("video_sources_analyzed", [])
    if source_url not in existing:
        existing.append(source_url)
    current_pitfalls = state.get("pitfall_count", 0)
    _save_state(project_root, {
        "video_sources_analyzed": existing,
        "pitfall_count": current_pitfalls + count,
        "last_phase_ts": time.time(),
    })


def list_analyzed_videos(project_root: Path) -> list[str]:
    """Return URLs of videos already analyzed in this project."""
    return _load_state(project_root).get("video_sources_analyzed", [])
