"""
Learning Engine for Genesis Architect (Pro).

Genesis improves over time by learning which research strategies and
recommendations actually worked - and adjusting future behavior accordingly.

Two learning scopes (Constitution 08):

  1. PER-PROJECT (immediate): outcomes recorded in this project feed back into
     the same project's next task right away. Stored in
     `.genesis/learning/outcomes.jsonl` and summarized into
     `.genesis/lessons_learned.md`.

  2. CROSS-PROJECT (anonymous): aggregate signal comes ONLY from consented,
     anonymous telemetry (see product_intelligence). Never from project code or
     content.

What is learned:
  - Which research profile produced accepted recommendations for a given task
    kind (bug, architecture, security, migration, ...).
  - Which recommendations get accepted vs rejected.
  - Which engines earn their keep.

How it is used:
  - `recommend_profile(task_kind)` returns the profile with the best track
    record for that kind of task, with a confidence that stays LOW until enough
    evidence accumulates (honesty clause - never claim a strong preference from
    one or two samples).
  - `rank_profiles(task_kind)` returns all candidate profiles ordered by their
    learned acceptance rate.

Determinism: scoring is a pure function of recorded outcomes. No model, no
randomness. The same history always yields the same recommendation.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

# Minimum samples before a learned preference is allowed to claim more than
# "low" confidence. Below this we still rank, but we say so honestly.
_MIN_SAMPLES_MEDIUM = 3
_MIN_SAMPLES_HIGH = 8

# The research profiles Genesis can choose between (mirrors the research engine).
KNOWN_PROFILES = (
    "deep_research", "bug_hunter", "architecture_review", "security_review",
    "performance_review", "migration_planner", "recovery_mode",
    "ai_model_comparison", "library_evaluation",
)


# ---------------------------------------------------------------------------
# Outcome record
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    """One recorded result: for a task of `task_kind`, profile `profile` produced
    a recommendation that was `accepted` (or not). `engine` is optional context.
    Carries NO project content - only enum-like labels."""
    task_kind: str
    profile: str
    accepted: bool
    engine: str = ""
    ts: int = 0

    def to_dict(self) -> dict:
        return {"task_kind": self.task_kind, "profile": self.profile,
                "accepted": self.accepted, "engine": self.engine, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Outcome":
        return cls(
            task_kind=str(d.get("task_kind", "")),
            profile=str(d.get("profile", "")),
            accepted=bool(d.get("accepted", False)),
            engine=str(d.get("engine", "")),
            ts=int(d.get("ts", 0)),
        )


@dataclass
class ProfileStat:
    profile: str
    accepted: int = 0
    total: int = 0

    @property
    def rate(self) -> float:
        return self.accepted / self.total if self.total else 0.0


@dataclass
class Recommendation:
    task_kind: str
    profile: str | None
    confidence: str            # high | medium | low | none
    rate: float
    samples: int
    rationale: str
    alternatives: list[ProfileStat] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _learning_dir(project_root: Path) -> Path:
    return Path(project_root) / ".genesis" / "learning"


def _outcomes_path(project_root: Path) -> Path:
    return _learning_dir(project_root) / "outcomes.jsonl"


def record_outcome(task_kind: str, profile: str, accepted: bool,
                   engine: str = "", project_root: Path | str = ".") -> bool:
    """Append one outcome to the per-project learning log. Returns True if
    written. Silently no-ops on bad input or I/O error (never blocks work)."""
    task_kind = (task_kind or "").strip().lower()
    profile = (profile or "").strip().lower()
    if not task_kind or not profile:
        return False
    rec = Outcome(task_kind=task_kind, profile=profile, accepted=bool(accepted),
                  engine=(engine or "").strip().lower(), ts=int(time.time()))
    try:
        p = _outcomes_path(Path(project_root))
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def read_outcomes(project_root: Path | str = ".") -> list[Outcome]:
    p = _outcomes_path(Path(project_root))
    if not p.exists():
        return []
    out: list[Outcome] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Outcome.from_dict(json.loads(line)))
            except json.JSONDecodeError:
                continue  # skip corrupt line, keep the rest
    except OSError:
        return []
    return out


# ---------------------------------------------------------------------------
# Learning (pure analysis over recorded outcomes)
# ---------------------------------------------------------------------------

def _stats_for_kind(outcomes: list[Outcome], task_kind: str) -> dict[str, ProfileStat]:
    stats: dict[str, ProfileStat] = {}
    for o in outcomes:
        if o.task_kind != task_kind:
            continue
        s = stats.setdefault(o.profile, ProfileStat(profile=o.profile))
        s.total += 1
        if o.accepted:
            s.accepted += 1
    return stats


def _confidence(samples: int) -> str:
    if samples >= _MIN_SAMPLES_HIGH:
        return "high"
    if samples >= _MIN_SAMPLES_MEDIUM:
        return "medium"
    if samples >= 1:
        return "low"
    return "none"


def rank_profiles(task_kind: str,
                  project_root: Path | str = ".") -> list[ProfileStat]:
    """All profiles seen for this task kind, ordered by acceptance rate then
    sample count (more evidence breaks ties). Empty if nothing learned yet."""
    task_kind = (task_kind or "").strip().lower()
    stats = _stats_for_kind(read_outcomes(project_root), task_kind)
    return sorted(stats.values(), key=lambda s: (s.rate, s.total), reverse=True)


def recommend_profile(task_kind: str,
                      project_root: Path | str = ".") -> Recommendation:
    """Recommend the best-performing research profile for a task kind, learned
    from this project's history. Confidence is honest about how much evidence
    backs the choice."""
    task_kind = (task_kind or "").strip().lower()
    ranked = rank_profiles(task_kind, project_root)
    if not ranked:
        return Recommendation(
            task_kind=task_kind, profile=None, confidence="none", rate=0.0,
            samples=0,
            rationale="No outcomes recorded yet for this task kind; "
                      "no learned preference. Genesis will use defaults.",
            alternatives=[],
        )
    top = ranked[0]
    conf = _confidence(top.total)
    # Honesty: a perfect rate from a single sample is not high confidence.
    return Recommendation(
        task_kind=task_kind,
        profile=top.profile,
        confidence=conf,
        rate=top.rate,
        samples=top.total,
        rationale=(f"'{top.profile}' has a {top.rate:.0%} acceptance rate over "
                   f"{top.total} recorded outcome(s) for '{task_kind}' tasks."),
        alternatives=ranked[1:],
    )


# ---------------------------------------------------------------------------
# Lessons digest (human-readable feedback into the project)
# ---------------------------------------------------------------------------

def summarize_lessons(project_root: Path | str = ".") -> str:
    """A Markdown digest of what has been learned, suitable for appending to
    `.genesis/lessons_learned.md`. Deterministic."""
    outcomes = read_outcomes(project_root)
    if not outcomes:
        return "# Lessons Learned\n\n_No outcomes recorded yet._\n"
    kinds = sorted({o.task_kind for o in outcomes})
    lines = ["# Lessons Learned", "",
             f"_Learned from {len(outcomes)} recorded outcome(s)._", ""]
    for kind in kinds:
        rec = recommend_profile(kind, project_root)
        lines.append(f"## {kind}")
        if rec.profile:
            lines.append(f"- Best profile: **{rec.profile}** "
                         f"({rec.rate:.0%} accepted, {rec.samples} samples, "
                         f"confidence: {rec.confidence})")
        for alt in rec.alternatives:
            lines.append(f"  - {alt.profile}: {alt.rate:.0%} "
                         f"({alt.total} samples)")
        lines.append("")
    return "\n".join(lines)


def write_lessons(project_root: Path | str = ".") -> Path | None:
    """Write the lessons digest to `.genesis/lessons_learned.md`. Returns the
    path, or None on I/O error."""
    root = Path(project_root)
    target = root / ".genesis" / "lessons_learned.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(summarize_lessons(root), encoding="utf-8")
        return target
    except OSError:
        return None
