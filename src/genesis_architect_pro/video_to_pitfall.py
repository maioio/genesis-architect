"""
Video-to-Pitfall Pipeline.

Converts /watch skill output (transcript + frame analysis) into
PITFALLS.md-compatible entries. Bridges Stream D video research
with the Phase 3/4 pitfall extraction pipeline.

Input:  raw text from a /watch analysis session
Output: list of PitfallEntry objects ready to append to PITFALLS.md

Usage in Companion Mode:
  After `genesis research --video <url>`, Claude passes the /watch
  output to extract_from_watch_output(), then appends the results
  to the existing PITFALLS.md via append_to_pitfalls_md().
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model - matches PITFALLS.md schema from SKILL.md Phase 4
# ---------------------------------------------------------------------------

@dataclass
class PitfallEntry:
    title: str
    source_url: str
    source_type: str          # video | github_issue | reddit | hn
    category: str             # pitfall | architecture_regret | security | performance
    what: str                 # problem description
    why: str                  # root cause
    mitigation: str           # what to build differently
    mitigation_file_path: str # scaffold path (required by Phase 4 schema)
    timestamp_cited: str      # video timestamp if available, else ""
    confidence: str           # high | medium | low
    raw_excerpt: str          # source text that triggered this entry
    tags: list[str] = field(default_factory=list)

    def to_markdown(self, index: int) -> str:
        """Render as a PITFALLS.md section."""
        lines = [
            f"## Pitfall {index}: {self.title}",
            f"**Source**: [{self.source_url}]({self.source_url})"
            + (f" at `{self.timestamp_cited}`" if self.timestamp_cited else ""),
            f"**Category**: {self.category}",
            f"**Confidence**: {self.confidence}",
            f"**What**: {self.what}",
            f"**Why**: {self.why}",
            f"**Mitigation**: {self.mitigation}",
            f"**mitigation_file_path**: `{self.mitigation_file_path}`",
            "",
            "**Implementation**:",
            f"- Create: `{self.mitigation_file_path}` with {self.mitigation}",
            f"- Test: `tests/test_{_slug(self.title)}.py` covering the {self.category} case",
            f"- Validate: verify `{self.mitigation_file_path}` exists and contains relevant logic",
            "",
            f"> *Extracted from video/media research. Excerpt: \"{self.raw_excerpt[:200]}\"*",
            "",
        ]
        return "\n".join(lines)


def _slug(text: str) -> str:
    """Convert title to snake_case slug for file names."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# Phrases that signal a pitfall being described
_PITFALL_SIGNALS = [
    r"(?:mistake|pitfall|gotcha|warn(?:ing)?|avoid|don't|never|regret)",
    r"(?:we (?:broke|learned|discovered|found out|realized))",
    r"(?:what (?:i|we) wish (?:i|we) (?:knew|had done))",
    r"(?:lesson(?:s)? learned?)",
    r"(?:went wrong|caused (?:issues?|problems?|outage))",
    r"(?:technical debt|anti.?pattern|bad (?:idea|practice))",
]
_PITFALL_RE = re.compile("|".join(_PITFALL_SIGNALS), re.IGNORECASE)

# Timestamp pattern from /watch output: [MM:SS] or [HH:MM:SS]
_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")

# Architecture decision signals
_ARCH_SIGNALS = re.compile(
    r"(?:decided|chose|switched|migrated|refactor(?:ed)?|moved (?:from|to)|replaced)",
    re.IGNORECASE,
)

# Performance signals
_PERF_SIGNALS = re.compile(
    r"(?:slow|memory|latency|timeout|oom|bottleneck|perf(?:ormance)?|scale)",
    re.IGNORECASE,
)

# Security signals
_SEC_SIGNALS = re.compile(
    r"(?:"
    r"security|auth(?:entication|orization)?|inject(?:ion)?|"
    r"cve|vulnerab(?:le|ility)?|secret|"
    r"token[s]?\b|cookie[s]?\b|session\b|httponly|"
    r"pentest|penetra(?:tion|te)|"
    r"credential|password|plaintext|plain.text|"
    r"xss|csrf|sql.injection|"
    r"encrypt|decrypt|cors|"
    r"bearer.token|oAuth|"
    r"malicious|attack|exploit|backdoor|"
    r"mitm|man.in.the.middle|"
    r"two.factor|mfa"
    r")",
    re.IGNORECASE,
)


def _classify_category(text: str) -> str:
    if _SEC_SIGNALS.search(text):
        return "security"
    if _PERF_SIGNALS.search(text):
        return "performance"
    if _ARCH_SIGNALS.search(text):
        return "architecture_regret"
    return "pitfall"


def _extract_timestamp(context: str) -> str:
    m = _TIMESTAMP_RE.search(context)
    return m.group(1) if m else ""


def _infer_mitigation_path(title: str, category: str) -> str:
    slug = _slug(title)
    if category == "security":
        return "src/utils/security.py"
    if category == "performance":
        return f"src/core/{slug}_optimized.py"
    return f"src/core/{slug}.py"


def _confidence_from_context(sentence: str, has_timestamp: bool) -> str:
    """Higher confidence when timestamp cited (speaker was specific)."""
    if has_timestamp and len(sentence) > 80:
        return "high"
    if len(sentence) > 50:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_from_watch_output(
    watch_text: str,
    source_url: str,
    vision: str,
    min_confidence: str = "medium",
) -> list[PitfallEntry]:
    """
    Parse /watch transcript+analysis text and extract pitfall entries.

    watch_text:     the full text output from a /watch session
    source_url:     the YouTube URL that was analyzed
    vision:         the project vision (used for mitigation path inference)
    min_confidence: filter out entries below this level (low|medium|high)
    """
    entries: list[PitfallEntry] = []
    seen_titles: set[str] = set()

    # Split into sentences / paragraphs for analysis
    segments = re.split(r"(?<=[.!?])\s+|\n{2,}", watch_text)

    for segment in segments:
        segment = segment.strip()
        if len(segment) < 40:
            continue
        if not _PITFALL_RE.search(segment):
            continue

        # Extract up to 2 sentences around the signal as excerpt
        excerpt = segment[:300]
        timestamp = _extract_timestamp(segment)
        category = _classify_category(segment)
        confidence = _confidence_from_context(segment, bool(timestamp))

        _conf_order = {"low": 0, "medium": 1, "high": 2}
        if _conf_order.get(confidence, 0) < _conf_order.get(min_confidence, 1):
            continue

        # Derive a short title from the first meaningful clause
        title_match = re.match(r"([A-Z][^.!?\n]{10,60})", segment)
        title = title_match.group(1).strip() if title_match else segment[:60]
        title = re.sub(r"\s+", " ", title)

        # Dedup by approximate title
        title_key = _slug(title)[:20]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        mitigation_path = _infer_mitigation_path(title, category)

        entries.append(PitfallEntry(
            title=title,
            source_url=source_url,
            source_type="video",
            category=category,
            what=title,
            why=f"Identified in video analysis at {timestamp or 'unknown timestamp'}",
            mitigation=f"Address the {category} issue described: {title[:80]}",
            mitigation_file_path=mitigation_path,
            timestamp_cited=timestamp,
            confidence=confidence,
            raw_excerpt=excerpt,
            tags=[category, "video_research"],
        ))

    return entries[:7]   # cap: match Phase 4's 3-7 pitfall target


# ---------------------------------------------------------------------------
# PITFALLS.md integration
# ---------------------------------------------------------------------------

def append_to_pitfalls_md(
    entries: list[PitfallEntry],
    pitfalls_path: Path,
    next_index: int | None = None,
) -> int:
    """
    Append extracted entries to an existing PITFALLS.md.
    Returns the count of entries appended.
    If the file doesn't exist, creates it with a minimal header.
    """
    if not entries:
        return 0

    if not pitfalls_path.exists():
        pitfalls_path.write_text(
            "# PITFALLS.md\n\nGenerated by Genesis Architect.\n\n",
            encoding="utf-8",
        )

    existing = pitfalls_path.read_text(encoding="utf-8")

    # Find highest existing pitfall index
    if next_index is None:
        indices = [int(m.group(1)) for m in re.finditer(r"## Pitfall (\d+)", existing)]
        next_index = (max(indices) + 1) if indices else 1

    new_sections = ["\n\n---\n\n## Video Research Pitfalls\n\n"]
    for i, entry in enumerate(entries):
        new_sections.append(entry.to_markdown(next_index + i))

    pitfalls_path.write_text(
        existing + "".join(new_sections),
        encoding="utf-8",
    )
    return len(entries)


def summarize_extraction(entries: list[PitfallEntry], source_url: str) -> str:
    """One-paragraph summary for Companion Mode output."""
    if not entries:
        return f"No clear pitfalls extracted from {source_url}. The video may be a tutorial rather than a lessons-learned talk."

    by_cat: dict[str, int] = {}
    for e in entries:
        by_cat[e.category] = by_cat.get(e.category, 0) + 1

    cat_summary = ", ".join(f"{v} {k}" for k, v in by_cat.items())
    high_conf = [e for e in entries if e.confidence == "high"]

    lines = [
        f"Extracted {len(entries)} pitfall candidates from video research ({cat_summary}).",
    ]
    if high_conf:
        lines.append(f"High-confidence findings: {', '.join(e.title[:50] for e in high_conf)}.")
    lines.append("Run `genesis harden .` to validate mitigations are implemented.")
    return " ".join(lines)
