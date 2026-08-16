"""
Genesis Companion — native floating window shell (pywebview).

The Floating Assistant HTML/CSS/JS in companion_ui.py is the real UI: bubble,
panel, chat, live status, quick actions. What was missing is a *native* host
for it — opening it in an ordinary browser tab (URL bar, tabs, bookmarks) is
not the "system-wide floating bubble" the spec describes
(docs/pro/FLOATING_ASSISTANT_SPEC.md §1, §12).

This module hosts the same HTML in a frameless, always-on-top, borderless
pywebview window sized to exactly the bubble (collapsed) or panel (expanded),
anchored to the bottom-right corner of the primary screen — so it reads as a
small floating widget, not a browser window. No new business logic: it is
presentation-only, same as the spec's technical architecture (§12) mandates.

Falls back honestly: if pywebview (or its native WebView2 runtime on Windows)
is unavailable, the caller should fall back to opening the HTML in a normal
browser tab instead — this module never silently degrades the experience
without saying so.
"""

from __future__ import annotations

from typing import Callable

# Content box sizes (must match the bubble/panel CSS in companion_ui.py).
# A little slack is added for the CSS drop-shadow bleed so it isn't clipped
# by the window bounds.
BUBBLE_SIZE = (372, 92)
PANEL_SIZE = (428, 656)
MARGIN = 24  # matches `right:24px; bottom:24px` in the CSS


class _Api:
    """Exposed to the page as `window.pywebview.api.*`."""

    def __init__(self, window_ref: Callable[[], object]) -> None:
        self._window = window_ref

    def resize_window(self, mode: str) -> None:
        """Grow/shrink the native window to the bubble or panel footprint,
        keeping the bottom-right corner anchored (panel "grows toward screen
        center" from the bubble's edge, per spec §1.2)."""
        win = self._window()
        if win is None:
            return
        size = PANEL_SIZE if mode == "panel" else BUBBLE_SIZE
        screen = _primary_screen()
        x = screen.width - MARGIN - size[0]
        y = screen.height - MARGIN - size[1]
        try:
            win.resize(*size)  # type: ignore[attr-defined]
            win.move(max(0, x), max(0, y))  # type: ignore[attr-defined]
        except Exception:
            pass


def _primary_screen():
    import webview  # type: ignore[import-not-found]
    return webview.screens[0]


def run_floating_window(html: str, *, on_close: Callable[[], None] | None = None) -> bool:
    """Host `html` in a native floating bubble/panel window and block until it
    is closed. Returns True if pywebview started successfully (the caller
    should not also open a browser tab); False if it could not be created at
    all (caller should fall back to a normal browser tab).
    """
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        return False

    screen = _primary_screen()
    x = screen.width - MARGIN - BUBBLE_SIZE[0]
    y = screen.height - MARGIN - BUBBLE_SIZE[1]

    holder: dict[str, object] = {}
    api = _Api(lambda: holder.get("window"))

    try:
        window = webview.create_window(
            "Genesis",
            html=html,
            js_api=api,
            width=BUBBLE_SIZE[0],
            height=BUBBLE_SIZE[1],
            x=max(0, x),
            y=max(0, y),
            frameless=True,
            easy_drag=False,  # we use .pywebview-drag-region instead — the
                               # panel is full of buttons/inputs that must
                               # stay clickable.
            on_top=True,
            resizable=False,
            transparent=True,
            shadow=True,
        )
    except Exception:
        return False

    if window is None:
        return False

    holder["window"] = window
    if on_close is not None:
        window.events.closed += on_close

    webview.start()
    return True
