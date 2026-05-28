"""Companion mode - detects exit conditions."""

import re

_EXIT_PHRASES = {
    "done", "exit", "exit companion mode", "quit", "stop",
    "goodbye", "bye", "leave companion mode",
}

_NEW_PROJECT_RE = re.compile(r"^\s*genesis\s+init\b", re.IGNORECASE)

_UNRELATED_SIGNALS = [
    r"\bnew project\b", r"\bstart over\b", r"\bdifferent project\b",
    r"\bunrelated\b", r"\bsomething else\b", r"\banother project\b",
]


def should_exit(user_input: str) -> tuple[bool, str]:
    """
    Returns (should_exit, reason).

    Reasons: 'explicit', 'new_project', 'unrelated', or '' if staying.
    """
    text = user_input.strip().lower()

    if text in _EXIT_PHRASES:
        return True, "explicit"

    if _NEW_PROJECT_RE.search(user_input):
        return True, "new_project"

    for pattern in _UNRELATED_SIGNALS:
        if re.search(pattern, text):
            return True, "unrelated"

    return False, ""


def exit_message(reason: str) -> str:
    if reason == "explicit":
        return "Exiting companion mode. Run `genesis init` to start a new project."
    if reason == "new_project":
        return "Starting a new project. Companion mode closed."
    if reason == "unrelated":
        return "This looks unrelated to the current project. Companion mode closed."
    return ""
