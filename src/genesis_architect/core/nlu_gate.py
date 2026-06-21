"""NLU gate - maps natural language to Genesis workflows and Phase 5 A/B/C/D choices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Phase 5 scaffold-tier choice (A/B/C/D) - unchanged from original
# ---------------------------------------------------------------------------

_MINIMALIST_PATTERNS = [
    r"\bminimali[sz]t\b", r"\bsimple\b", r"\bsmall\b", r"\blight\b",
    r"\ba\b", r"\boption a\b", r"\bchoice a\b",
]
_SCALABLE_PATTERNS = [
    r"\bscalab\w*\b", r"\bfull\b", r"\bcomplete\b", r"\bproduction\b",
    r"\bb\b", r"\boption b\b", r"\bchoice b\b",
]
_QUICK_PATTERNS = [r"\bquick\b", r"\bfast\b", r"\bc\b", r"\boption c\b"]
_HYBRID_PATTERNS = [r"\bhybrid\b", r"\bmix\b", r"\bboth\b", r"\bd\b", r"\boption d\b"]

_CHOICES = {
    "A": ("minimalist", _MINIMALIST_PATTERNS),
    "B": ("scalable", _SCALABLE_PATTERNS),
    "C": ("quick", _QUICK_PATTERNS),
    "D": ("hybrid", _HYBRID_PATTERNS),
}


def _classify_choice(text: str) -> str | None:
    t = text.lower().strip()
    for letter, (_, patterns) in _CHOICES.items():
        for pat in patterns:
            if re.search(pat, t):
                return letter
    return None


def prompt_choice(ask_fn, confirm_fn) -> str:
    """
    ask_fn()     -> str   (reads user input for the choice)
    confirm_fn() -> bool  (reads "y/n" confirmation)

    Returns the chosen letter A/B/C/D, or raises SystemExit after 3 failures.
    """
    attempts = 0
    while attempts < 3:
        raw = ask_fn().strip()
        letter = raw.upper() if raw.upper() in _CHOICES else _classify_choice(raw)

        if letter:
            label = _CHOICES[letter][0]
            print(f"I'll take that as {letter} ({label}) - correct? [y/n]")
            if confirm_fn():
                return letter
        else:
            print(f"I couldn't understand '{raw}'. Please choose A, B, C, or D.")

        attempts += 1

    print("Start over from Phase 1? [y/n]")
    return "__restart__"


# ---------------------------------------------------------------------------
# Full intent routing (pre-Phase 0 natural language detection)
# ---------------------------------------------------------------------------

class Intent(Enum):
    FAST_BUILD = "fast-build"
    PROFESSIONAL = "professional"
    FOUNDER = "founder"
    AUDIT = "audit"
    RECOVERY = "recovery"
    RESUME = "resume"
    VALIDATION = "validation"
    RESEARCH_ONLY = "research-only"
    UNKNOWN = "unknown"


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IntentResult:
    intent: Intent
    confidence: Confidence
    matched_phrase: str
    route_description: str


# Patterns: (compiled regex, weight) - weight 2 = strong signal, 1 = weak
_INTENT_PATTERNS: dict[Intent, list[tuple[str, int]]] = {
    Intent.FAST_BUILD: [
        (r"\bjust build\b", 2),
        (r"\bbuild (?:me |it |this )?(?:quick|fast|now)\b", 2),
        (r"\bquick(?:ly)? (?:working|version|mvp|prototype)\b", 2),
        (r"\bworking version\b", 2),
        (r"\bhackathon\b", 2),
        (r"\bprototype\b", 1),
        (r"\bget it running\b", 2),
        (r"\bmake it work\b", 2),
        (r"\bjust start\b", 1),
        (r"\bno research\b", 2),
        (r"\bskip (?:the )?research\b", 2),
    ],
    Intent.PROFESSIONAL: [
        (r"\bstructured\b", 1),
        (r"\bproduction[- ]ready\b", 2),
        (r"\bteam project\b", 2),
        (r"\bproper (?:setup|project|scaffold)\b", 2),
        (r"\benterprise\b", 2),
        (r"\bfull (?:setup|research|analysis)\b", 1),
        (r"\bscalable project\b", 2),
    ],
    Intent.FOUNDER: [
        (r"\bworth building\b", 2),
        (r"\bshould i build\b", 2),
        (r"\bis there (?:a )?(?:market|demand)\b", 2),
        (r"\bcompetitor[s]?\b", 2),
        (r"\bmonetize\b", 2),
        (r"\bviable\b", 1),
        (r"\bproduct strategy\b", 2),
        (r"\bidea validation\b", 2),
        (r"\btarget (?:user|audience|market)\b", 2),
        (r"\bcheck (?:if (?:it'?s? )?worth|the market)\b", 2),
    ],
    Intent.AUDIT: [
        (r"\breview this\b", 2),
        (r"\baudit\b", 2),
        (r"\bwhat(?:'s| is) wrong\b", 2),
        (r"\bcheck (?:this )?(?:project|code|codebase)\b", 2),
        (r"\bwhat are the issues\b", 2),
        (r"\bbefore i (?:continue|release|ship|merge)\b", 2),
        (r"\blook at my code\b", 2),
        (r"\bcode (?:review|check)\b", 2),
    ],
    Intent.RECOVERY: [
        (r"\bbroken\b", 2),
        (r"\bfailing\b", 1),
        (r"\bcrashed\b", 2),
        (r"\bsomething is wrong\b", 2),
        (r"\bfigure out what(?:'?s| is) wrong\b", 2),
        (r"\bfix this project\b", 2),
        (r"\bdebug this\b", 2),
        (r"\bstopped working\b", 2),
        (r"\bnot working\b", 1),
        (r"\bproject is (?:broken|failing|crashed)\b", 2),
    ],
    Intent.RESUME: [
        (r"\bcontinue(?: from)?\b", 2),
        (r"\bwhere (?:we |I )?left off\b", 2),
        (r"\bpick up\b", 2),
        (r"\bresume\b", 2),
        (r"\bwhere (?:we )?stopped\b", 2),
        (r"\bwhat(?:'s| is) next\b", 1),
        (r"\bcarry on\b", 2),
        (r"\bcontinue (?:from |where )\b", 2),
    ],
    Intent.VALIDATION: [
        (r"\bdoes this work\b", 2),
        (r"\btest this\b", 1),
        (r"\bverify\b", 1),
        (r"\bcheck if it runs\b", 2),
        (r"\bsmoke test\b", 2),
        (r"\bis it working\b", 2),
        (r"\brun the tests\b", 2),
        (r"\bvalidate\b", 1),
    ],
    Intent.RESEARCH_ONLY: [
        (r"\bjust (?:do )?research\b", 2),
        (r"\bonly (?:do )?research\b", 2),
        (r"\bdon(?:'t| not) build\b", 2),
        (r"\binvestigate\b", 1),
        (r"\bfind out (?:about|how)\b", 1),
        (r"\bwhat do (?:projects|apps) like this do\b", 2),
        (r"\bno (?:code|scaffold|build)\b", 2),
    ],
}

_ROUTE_DESCRIPTIONS: dict[Intent, str] = {
    Intent.FAST_BUILD: "Fast MVP mode - 5 min research cap, then building immediately",
    Intent.PROFESSIONAL: "Professional mode - structured research and validation",
    Intent.FOUNDER: "Founder mode - market research, competitor analysis, product strategy",
    Intent.AUDIT: "Audit mode - analyzing existing codebase for pitfalls and issues",
    Intent.RECOVERY: "Recovery mode - reading project state and diagnosing what is broken",
    Intent.RESUME: "Resume mode - restoring context and continuing from last completed step",
    Intent.VALIDATION: "Validation mode - running smoke tests and MVP validation checks",
    Intent.RESEARCH_ONLY: "Research-only mode - Phases 2-4, no scaffold generated",
    Intent.UNKNOWN: "Presenting experience selection menu",
}


def detect_intent(text: str) -> IntentResult:
    """
    Classify the user's natural language input into a Genesis workflow intent.

    Returns an IntentResult with the matched intent, confidence level, the phrase
    that triggered the match, and a human-readable route description.
    """
    t = text.lower().strip()

    scores: dict[Intent, tuple[int, str]] = {}  # intent -> (score, first matched phrase)

    for intent, patterns in _INTENT_PATTERNS.items():
        total = 0
        first_match = ""
        for pat, weight in patterns:
            m = re.search(pat, t)
            if m:
                total += weight
                if not first_match:
                    first_match = m.group(0)
        if total > 0:
            scores[intent] = (total, first_match)

    if not scores:
        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=Confidence.LOW,
            matched_phrase="",
            route_description=_ROUTE_DESCRIPTIONS[Intent.UNKNOWN],
        )

    best_intent = max(scores, key=lambda i: scores[i][0])
    best_score, matched_phrase = scores[best_intent]

    # Determine confidence: high if score >= 2 and no close second-place competitor
    second_scores = [s for i, (s, _) in scores.items() if i != best_intent]
    second_best = max(second_scores, default=0)

    if best_score >= 2 and best_score > second_best:
        confidence = Confidence.HIGH
    elif best_score >= 1:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    return IntentResult(
        intent=best_intent,
        confidence=confidence,
        matched_phrase=matched_phrase,
        route_description=_ROUTE_DESCRIPTIONS[best_intent],
    )


def announce_routing(result: IntentResult, original_text: str) -> str:
    """
    Build the announcement message Genesis shows before acting on an intent.
    Returns the message string; caller is responsible for printing it.
    """
    if result.intent == Intent.UNKNOWN:
        return "Let me understand what you need. What kind of Genesis experience are you looking for?"

    phrase_note = f" because you said '{result.matched_phrase}'" if result.matched_phrase else ""
    base = (
        f"I read that as {result.intent.value}{phrase_note}. "
        f"{result.route_description}."
    )

    if result.confidence == Confidence.MEDIUM:
        base += " Say 'no' or describe differently to change course."

    return base
