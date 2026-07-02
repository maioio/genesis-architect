"""
Memory Engine for Genesis Architect (Pro).

Per-project memory + Decision Journal as plain Markdown under `.genesis/`
(Constitution 08 / the HTML "Memory + Decision Journal" section). No vector DB —
human-readable, diffable, git-friendly files:

    .genesis/
      project_memory.md          # what the project is, current state
      decision_log.md            # the Decision Journal (every significant decision)
      research_history.md        # what was researched, when, result
      architecture_decisions.md  # ADRs — the intended-architecture / drift baseline
      known_risks.md             # open risks, severity, status
      lessons_learned.md         # what worked / what did not  (also fed by Learning)

This module OWNS the human-readable journal files. It is distinct from:
  - gde_session.py's `gde_decision_log.jsonl` (machine runtime log), and
  - learning_engine.py's `lessons_learned.md` digest (this module appends notes;
    the Learning Engine can regenerate the digest section).

Decision Journal rule (binding): a decision with no journal entry is treated as
not made. Every entry records: the decision, alternatives considered, evidence/
sources, confidence, "what would change this", an absolute date, and the loop
step that produced it.

All writes are append-or-create, never destructive. Never raises on I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# The journal files this engine manages, with their headers.
MEMORY_FILES = {
    "project_memory.md": "# Project Memory\n\n_What this project is and its current state._\n",
    "decision_log.md": "# Decision Log (Decision Journal)\n\n"
                       "_Every significant decision. A decision with no entry here "
                       "is treated as not made._\n",
    "research_history.md": "# Research History\n\n_What was researched, when, and the result._\n",
    "architecture_decisions.md": "# Architecture Decisions (ADRs)\n\n"
                                 "_The intended architecture — the drift baseline._\n",
    "known_risks.md": "# Known Risks\n\n_Open risks, severity, and status._\n",
    "lessons_learned.md": "# Lessons Learned\n\n_What worked, what did not._\n",
}


def _mem_dir(project_root: Path) -> Path:
    return Path(project_root) / ".genesis"


def _ensure_file(path: Path, header: str) -> bool:
    """Create the file with its header if missing. Returns True if it exists
    after the call."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(header + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def init_memory(project_root: Path | str = ".") -> list[str]:
    """Create any missing memory files with their headers. Returns the list of
    files that now exist. Idempotent and non-destructive."""
    root = _mem_dir(Path(project_root))
    created: list[str] = []
    for name, header in MEMORY_FILES.items():
        if _ensure_file(root / name, header):
            created.append(name)
    return created


def _append(project_root: Path, filename: str, header: str, block: str) -> bool:
    path = _mem_dir(Path(project_root)) / filename
    if not _ensure_file(path, header):
        return False
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + block.rstrip() + "\n")
        return True
    except OSError:
        return False


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Decision Journal
# ---------------------------------------------------------------------------

@dataclass
class DecisionJournalEntry:
    decision: str
    alternatives: list = field(default_factory=list)
    evidence: list = field(default_factory=list)        # sources / refs
    confidence: str = "low"                              # high | medium | low
    what_would_change_it: str = ""
    loop_step: str = "Decide"                            # which Thinking-Loop step
    date_: str = ""                                      # absolute; auto-filled

    def to_markdown(self) -> str:
        d = self.date_ or _today()
        lines = [f"## {d} — {self.decision}",
                 f"- **Loop step:** {self.loop_step}",
                 f"- **Confidence:** {self.confidence}"]
        if self.alternatives:
            lines.append("- **Alternatives considered:** "
                         + "; ".join(str(a) for a in self.alternatives))
        if self.evidence:
            lines.append("- **Evidence / sources:** "
                         + "; ".join(str(e) for e in self.evidence))
        lines.append("- **What would change it:** "
                     + (self.what_would_change_it or "(not specified)"))
        return "\n".join(lines)


def record_decision(entry: DecisionJournalEntry,
                    project_root: Path | str = ".") -> bool:
    """Append a Decision Journal entry to `.genesis/decision_log.md`.

    Honesty: high confidence requires at least one piece of evidence — otherwise
    it is recorded as 'medium' (a decision can't be highly confident with no
    basis)."""
    if entry.confidence == "high" and not entry.evidence:
        entry.confidence = "medium"
    if not entry.date_:
        entry.date_ = _today()
    return _append(project_root, "decision_log.md",
                   MEMORY_FILES["decision_log.md"], entry.to_markdown())


# ---------------------------------------------------------------------------
# Other journal helpers
# ---------------------------------------------------------------------------

def record_research(topic: str, sources: list, result: str,
                    project_root: Path | str = ".") -> bool:
    block = (f"## {_today()} — {topic}\n"
             f"- **Sources:** {'; '.join(str(s) for s in sources) or '(none)'}\n"
             f"- **Result:** {result}")
    return _append(project_root, "research_history.md",
                   MEMORY_FILES["research_history.md"], block)


def record_risk(label: str, severity: str = "medium", status: str = "open",
                note: str = "", project_root: Path | str = ".") -> bool:
    block = (f"## {label}\n"
             f"- **Severity:** {severity}\n"
             f"- **Status:** {status}\n"
             f"- **Noted:** {_today()}")
    if note:
        block += f"\n- **Note:** {note}"
    return _append(project_root, "known_risks.md",
                   MEMORY_FILES["known_risks.md"], block)


def record_adr(title: str, decision: str, rationale: str = "",
               project_root: Path | str = ".") -> bool:
    block = (f"## {_today()} — {title}\n"
             f"- **Decision:** {decision}")
    if rationale:
        block += f"\n- **Rationale:** {rationale}"
    return _append(project_root, "architecture_decisions.md",
                   MEMORY_FILES["architecture_decisions.md"], block)


def record_lesson(lesson: str, worked: bool = True,
                  project_root: Path | str = ".") -> bool:
    mark = "✅ worked" if worked else "❌ did not work"
    block = f"## {_today()} — {mark}\n- {lesson}"
    return _append(project_root, "lessons_learned.md",
                   MEMORY_FILES["lessons_learned.md"], block)


def set_project_memory(text: str, project_root: Path | str = ".") -> bool:
    """Overwrite project_memory.md body (the single 'current state' summary).
    Unlike the journals this is a living summary, so it is replaced, not
    appended."""
    path = _mem_dir(Path(project_root)) / "project_memory.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MEMORY_FILES["project_memory.md"] + "\n" +
                        text.rstrip() + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------

def read_memory(filename: str, project_root: Path | str = ".") -> str:
    """Return the contents of a memory file, or '' if absent."""
    path = _mem_dir(Path(project_root)) / filename
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def memory_status(project_root: Path | str = ".") -> dict:
    """Which memory files exist and roughly how much is in each (line count)."""
    root = _mem_dir(Path(project_root))
    out: dict[str, int | bool] = {}
    for name in MEMORY_FILES:
        p = root / name
        out[name] = (len(p.read_text(encoding="utf-8").splitlines())
                     if p.exists() else False)
    return out
