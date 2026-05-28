"""Phase 5 NLU gate - maps natural language to A/B/C/D choices."""

import re

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


def _classify(text: str) -> str | None:
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
        letter = raw.upper() if raw.upper() in _CHOICES else _classify(raw)

        if letter:
            label = _CHOICES[letter][0]
            print(f"I'll take that as {letter} ({label}) - correct? [y/n]")
            if confirm_fn():
                return letter
            # user said no - try again
        else:
            print(f"I couldn't understand '{raw}'. Please choose A, B, C, or D.")

        attempts += 1

    print("Start over from Phase 1? [y/n]")
    return "__restart__"
