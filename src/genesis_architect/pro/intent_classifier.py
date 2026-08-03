"""Genesis Decision Engine — intent classifier.

Maps free-text user input to a GDEMode + Intent using keyword/pattern signals.
No LLM calls. No side effects. Pure function.

Confidence rules:
- Each matched signal adds to a per-mode score.
- Final confidence = matched_score / max_possible_score, clamped to [0.0, 1.0].
- If top-mode confidence < CLARIFY_THRESHOLD, clarifying_questions are populated.
- If two modes are within AMBIGUITY_MARGIN of each other, COMMITTEE_MODE wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from genesis_architect.pro.gde_types import GDEMode, Intent

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

CLARIFY_THRESHOLD = 0.25   # below this → attach clarifying questions
AMBIGUITY_MARGIN = 0.10    # if top two modes within this margin → COMMITTEE
MIN_CONFIDENCE = 0.10      # floor returned even on zero signal match


# ---------------------------------------------------------------------------
# Signal table
# ---------------------------------------------------------------------------
# Each entry: (regex_pattern, weight)
# All patterns are matched case-insensitively against the full input text.

_MODE_SIGNALS: dict[GDEMode, list[tuple[str, float]]] = {
    GDEMode.RECOVERY: [
        (r"\brecover\b", 1.0),
        (r"\bdiagnos", 1.0),
        (r"\bscan\b", 0.8),
        (r"\bhealth\b", 0.7),
        (r"\bbroken\b", 0.9),
        (r"\bfix\b", 0.6),
        (r"\berror\b", 0.7),
        (r"\bcrash\b", 0.9),
        (r"\bfail", 0.7),
        (r"\bdrift\b", 0.8),
        (r"\bdecay\b", 0.8),
        (r"\bfragil", 0.7),
        (r"\banti.?pattern", 0.8),
        (r"\bimport.*graph\b", 0.6),
        (r"\barchitecture.*score", 0.6),
        (r"\bwhat.s wrong", 1.0),
        (r"\bwhat is wrong", 1.0),
        (r"\bcheck.*project", 0.5),
        (r"\baudit\b", 0.7),
        (r"\bidentify.*drift", 1.0),
        (r"\bidentify.*fragil", 1.0),
        (r"\bidentify.*issue", 0.7),
        (r"\bhealth.*check", 0.9),
        (r"\bcodebase.*health", 0.9),
    ],
    GDEMode.RESEARCH: [
        (r"\bresearch\b", 1.0),
        (r"\binvestigat", 0.9),
        (r"\bbest.*practice", 0.9),
        (r"\bpitfall", 0.9),
        (r"\bcompar", 0.7),
        (r"\blearn\b", 0.6),
        (r"\bstudy\b", 0.6),
        (r"\bfind.*info", 0.7),
        (r"\blook.*up\b", 0.6),
        (r"\bhow does\b", 0.6),
        (r"\bwhat is\b", 0.4),
        (r"\bvideo\b", 0.6),
        (r"\byoutube\b", 0.7),
        (r"\breddit\b", 0.7),
        (r"\bpaper\b", 0.6),
        (r"\bdocumentation\b", 0.5),
        (r"\btrend\b", 0.6),
        (r"\bbenchmark\b", 0.7),
        (r"\bexample\b", 0.4),
        (r"\bfield.*intelligence\b", 1.0),
        (r"\bevidence\b", 0.7),
        (r"\bsources?\b", 0.5),
        (r"\bsurvey\b", 0.7),
    ],
    GDEMode.REFACTOR: [
        (r"\brefactor\b", 1.0),
        (r"\brestructur", 0.9),
        (r"\bclean.*up\b", 0.7),
        (r"\bimprove.*structure", 0.8),
        (r"\bmodulari", 0.8),
        (r"\bdecouple\b", 0.8),
        (r"\bextract\b", 0.6),
        (r"\bsplit\b", 0.5),
        (r"\bmove.*to\b", 0.5),
        (r"\brename\b", 0.5),
        (r"\bsimplif", 0.6),
        (r"\bplan.*refactor", 1.0),
        (r"\brefactoring.*plan", 1.0),
        (r"\breduce.*coupling", 0.9),
        (r"\bcoupling\b", 0.7),
        (r"\bgod.*class", 0.9),
    ],
    GDEMode.GATE: [
        (r"\bgate\b", 1.0),
        (r"\bcheck.*rules?\b", 0.8),
        (r"\bvalidat", 0.7),
        (r"\bpolic", 0.8),
        (r"\bcomplian", 0.8),
        (r"\bsecurity.*check", 0.9),
        (r"\blicense\b", 0.7),
        (r"\bpermission", 0.6),
        (r"\bapproval\b", 0.7),
        (r"\brisk\b", 0.6),
        (r"\bsafe.*to\b", 0.6),
        (r"\bok.*to.*proceed", 0.8),
    ],
    GDEMode.BUILD: [
        (r"\bbuild\b", 1.0),
        (r"\bscaffold\b", 1.0),
        (r"\binit\b", 0.9),
        (r"\bnew.*project\b", 1.0),
        (r"\bcreate.*project\b", 1.0),
        (r"\bstart.*project\b", 0.9),
        (r"\bcreate\b", 0.6),
        (r"\bgenerat", 0.7),
        (r"\bnew.*module\b", 0.8),
        (r"\bnew.*class\b", 0.7),
        (r"\bnew.*endpoint\b", 0.8),
        (r"\bnew.*feature\b", 0.7),
        (r"\bimplement\b", 0.6),
        (r"\badd\b", 0.3),
        (r"\bwrite.*code", 0.7),
        (r"\bboilerplate\b", 0.8),
        (r"\btemplate\b", 0.6),
        (r"\bproject.*from.*scratch\b", 1.0),
        (r"\bsetup.*project\b", 0.9),
    ],
    GDEMode.DOCUMENT: [
        (r"\bdocument\b", 1.0),
        (r"\bdoc\b", 0.8),
        (r"\breadme\b", 0.9),
        (r"\bwriteup\b", 0.8),
        (r"\bwrite.*up\b", 0.7),
        (r"\bexplain\b", 0.6),
        (r"\bdescribe\b", 0.6),
        (r"\bsummar", 0.5),
        (r"\breport\b", 0.5),
        (r"\bchannel.*notes", 0.7),
        (r"\bchangelog\b", 0.8),
        (r"\brelease.*notes", 0.8),
        (r"\bapi.*doc", 0.9),
        (r"\bdocstring", 0.8),
        (r"\bc4\b", 1.0),
        (r"\barchitecture.*diagram", 1.0),
        (r"\bgenerate.*diagram", 0.9),
        (r"\bdiagram\b", 0.8),
        (r"\bmermaid\b", 0.9),
    ],
    GDEMode.COMMITTEE: [
        (r"\bcommittee\b", 1.0),
        (r"\bmulti.*perspective", 0.9),
        (r"\bsecond.*opinion\b", 1.0),
        (r"\bget.*perspective", 1.0),
        (r"\ball.*angle", 0.9),
        (r"\bdivergen", 0.8),
        (r"\bcomplex\b", 0.5),
        (r"\buncertain\b", 0.7),
        (r"\bnot sure\b", 0.6),
        (r"\bdon.t know\b", 0.6),
        (r"\badvice\b", 0.5),
        (r"\bshould i\b", 0.5),
        (r"\bhelp me decide\b", 0.8),
        (r"\bwhat.*should\b", 0.5),
        (r"\bmultiple.*view", 1.0),
        (r"\bviewpoint", 1.0),
        (r"\bpros.*cons\b", 0.9),
        (r"\btrade.*off", 0.9),
        (r"\bmicroservice.*vs\b", 0.9),
        (r"\bwhether.*to.*use\b", 0.7),
    ],
}

# Pre-compiled for performance
_COMPILED: dict[GDEMode, list[tuple[re.Pattern[str], float, str]]] = {
    mode: [
        (re.compile(pat, re.IGNORECASE), weight, pat)
        for pat, weight in signals
    ]
    for mode, signals in _MODE_SIGNALS.items()
}

# Maximum score achievable in the top-N signals (used for normalisation).
# We use the sum of the top-5 highest-weight signals so that matching 5 strong
# signals yields confidence ≈ 1.0, rather than requiring ALL signals to match.
_TOP_N = 5

_MAX_SCORE: dict[GDEMode, float] = {
    mode: sum(sorted((w for _, w in signals), reverse=True)[:_TOP_N])
    for mode, signals in _MODE_SIGNALS.items()
}


# ---------------------------------------------------------------------------
# Clarifying questions per mode
# ---------------------------------------------------------------------------

_CLARIFYING_QUESTIONS: dict[GDEMode, list[str]] = {
    GDEMode.RECOVERY: [
        "Which part of the project seems unhealthy? (e.g., imports, architecture, drift)",
        "Is this a full-project scan or focused on a specific module?",
    ],
    GDEMode.RESEARCH: [
        "What topic or library should be researched?",
        "Should I include video sources, Reddit, or only technical docs?",
    ],
    GDEMode.REFACTOR: [
        "Which module or area should be refactored?",
        "Is this a plan-only pass or should I produce a full execution plan?",
    ],
    GDEMode.GATE: [
        "Which policy or rule set should I check against?",
        "Is this a security gate, license gate, or architecture gate?",
    ],
    GDEMode.BUILD: [
        "What should be built? (module name, class, endpoint, etc.)",
        "Should I use an existing scaffold template or start from scratch?",
    ],
    GDEMode.DOCUMENT: [
        "What should be documented? (module, API, changelog, README?)",
        "Should the output be Markdown, DOCX, or inline docstrings?",
    ],
    GDEMode.COMMITTEE: [
        "What decision needs the Architecture Committee's perspective?",
        "Are there specific trade-offs you want evaluated?",
    ],
}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


@dataclass
class _ModeScore:
    mode: GDEMode
    raw_score: float
    matched_signals: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        max_s = _MAX_SCORE[self.mode]
        if max_s == 0:
            return 0.0
        return min(1.0, self.raw_score / max_s)


def classify(text: str) -> Intent:
    """Classify free-text input into a GDEMode and return a full Intent.

    Args:
        text: Raw user input string. May be multi-sentence or very short.

    Returns:
        Intent with mode, confidence, matched signals, and (if low-confidence)
        clarifying questions to surface to the user.
    """
    if not text or not text.strip():
        return Intent(
            raw_text=text,
            mode=GDEMode.COMMITTEE,
            confidence=MIN_CONFIDENCE,
            signals=[],
            clarifying_questions=_CLARIFYING_QUESTIONS[GDEMode.COMMITTEE],
            params={},
        )

    normalized = text.strip()

    # Score each mode
    scores: list[_ModeScore] = []
    for mode, compiled_signals in _COMPILED.items():
        ms = _ModeScore(mode=mode, raw_score=0.0)
        for pattern, weight, pat_str in compiled_signals:
            if pattern.search(normalized):
                ms.raw_score += weight
                ms.matched_signals.append(pat_str)
        scores.append(ms)

    # Sort descending by confidence
    scores.sort(key=lambda s: s.confidence, reverse=True)
    top = scores[0]
    second = scores[1] if len(scores) > 1 else None

    # Ambiguity check: if two modes are too close AND both have meaningful signal,
    # escalate to COMMITTEE. Skip check if top confidence is already low
    # (COMMITTEE fallback handles that separately).
    if (
        second is not None
        and top.raw_score > 0
        and second.raw_score > 0
        and top.confidence >= CLARIFY_THRESHOLD
        and (top.confidence - second.confidence) < AMBIGUITY_MARGIN
        and top.mode is not GDEMode.COMMITTEE
    ):
        # Build combined signals from both candidates
        combined_signals = list(dict.fromkeys(top.matched_signals + second.matched_signals))
        return Intent(
            raw_text=normalized,
            mode=GDEMode.COMMITTEE,
            confidence=max(MIN_CONFIDENCE, (top.confidence + second.confidence) / 2),
            signals=combined_signals,
            clarifying_questions=_CLARIFYING_QUESTIONS[GDEMode.COMMITTEE],
            params={"ambiguous_between": [top.mode.value, second.mode.value]},
        )

    # No signals matched at all → COMMITTEE with minimum confidence
    if top.raw_score == 0:
        return Intent(
            raw_text=normalized,
            mode=GDEMode.COMMITTEE,
            confidence=MIN_CONFIDENCE,
            signals=[],
            clarifying_questions=_CLARIFYING_QUESTIONS[GDEMode.COMMITTEE],
            params={},
        )

    final_confidence = max(MIN_CONFIDENCE, top.confidence)
    questions = (
        _CLARIFYING_QUESTIONS.get(top.mode, [])
        if final_confidence < CLARIFY_THRESHOLD
        else []
    )

    return Intent(
        raw_text=normalized,
        mode=top.mode,
        confidence=final_confidence,
        signals=top.matched_signals,
        clarifying_questions=questions,
        params={},
    )
