#!/usr/bin/env python3
"""WCAG contrast ratio checker.

Usage:
  python scripts/contrast_check.py "#0f172a" "#ffffff"

Outputs the contrast ratio and whether it passes WCAG AA for:
- normal text (>= 4.5:1)
- large text (>= 3:1)

Exit codes:
- 0 if passes normal text threshold
- 1 otherwise
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RGB:
    r: float  # 0..1
    g: float  # 0..1
    b: float  # 0..1


HEX_RE = re.compile(r"^#?(?P<h>[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex_colour(s: str) -> RGB:
    m = HEX_RE.match(s.strip())
    if not m:
        raise ValueError(f"Invalid hex colour: {s!r}. Expected #RGB or #RRGGBB.")
    h = m.group("h")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return RGB(r, g, b)


def srgb_to_linear(c: float) -> float:
    # WCAG uses the sRGB companding function.
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r_lin = srgb_to_linear(rgb.r)
    g_lin = srgb_to_linear(rgb.g)
    b_lin = srgb_to_linear(rgb.b)
    # ITU-R BT.709
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(c1: RGB, c2: RGB) -> float:
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip())
        return 2

    fg_s, bg_s = argv[1], argv[2]
    try:
        fg = parse_hex_colour(fg_s)
        bg = parse_hex_colour(bg_s)
    except ValueError as e:
        print(f"Error: {e}")
        return 2

    ratio = contrast_ratio(fg, bg)

    normal_ok = ratio >= 4.5
    large_ok = ratio >= 3.0

    print(f"Foreground: {fg_s}  Background: {bg_s}")
    print(f"Contrast ratio: {ratio:.2f}:1")
    print(f"Normal text (>= 4.5): {'PASS' if normal_ok else 'FAIL'}")
    print(f"Large text  (>= 3.0): {'PASS' if large_ok else 'FAIL'}")

    return 0 if normal_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
