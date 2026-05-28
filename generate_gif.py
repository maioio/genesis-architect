"""
Generate demo.gif directly with Pillow - no Electron, no display server needed.
Renders a mock terminal session showing Genesis Architect features.
"""
from PIL import Image, ImageDraw, ImageFont
import re, os

# --- Layout ---
COLS        = 90
FONT_SIZE   = 14
FONT_PATH   = "C:/Windows/Fonts/cascadiacode.ttf"
FONT        = ImageFont.truetype(FONT_PATH, FONT_SIZE)
BOLD_FONT   = ImageFont.truetype(FONT_PATH, FONT_SIZE)   # same face, styling via color

CHAR_W, CHAR_H = FONT.getbbox("M")[2], FONT.getbbox("M")[3] + 2
LINE_H      = CHAR_H + 3
PAD_X       = 16
PAD_TOP     = 40   # titlebar
PAD_BOT     = 12

BG          = "#0d0f14"
SURFACE     = "#161922"
BORDER      = "#2a3045"
TITLE_TEXT  = "#8892a4"

# ANSI palette (matches the landing page theme)
PALETTE = {
    "0":  "#e8eaf0",   # reset / default fg
    "90": "#4a5568",   # dark gray
    "91": "#ff7fac",
    "92": "#64ffda",   # bright green / mint
    "93": "#ffd166",   # yellow
    "94": "#4fc3f7",   # blue
    "95": "#ae89fe",   # purple
    "96": "#64ffda",   # cyan / mint
    "97": "#ffffff",   # bright white
    "32": "#64ffda",
    "33": "#ffd166",
    "36": "#64ffda",
    "37": "#e8eaf0",
}

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def parse_line(raw: str):
    """Parse ANSI-colored string into list of (text, color) tuples."""
    segments = []
    current_color = PALETTE["0"]
    last = 0
    for m in ANSI_RE.finditer(raw):
        if m.start() > last:
            segments.append((raw[last:m.start()], current_color))
        code = m.group(1)
        if code == "0" or code == "":
            current_color = PALETTE["0"]
        elif code in PALETTE:
            current_color = PALETTE[code]
        elif ";" in code:
            # bold + color: take the color part
            for part in code.split(";"):
                if part in PALETTE:
                    current_color = PALETTE[part]
        last = m.end()
    if last < len(raw):
        segments.append((raw[last:], current_color))
    return segments


def render_frame(lines: list[str], highlight_last: int = 0) -> Image.Image:
    """Render a list of pre-colored text lines into a PIL Image."""
    visible = lines[-28:] if len(lines) > 28 else lines
    h = PAD_TOP + len(visible) * LINE_H + PAD_BOT
    w = PAD_X * 2 + COLS * CHAR_W
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([0, 0, w, PAD_TOP - 1], fill=SURFACE)
    draw.line([0, PAD_TOP - 1, w, PAD_TOP - 1], fill=BORDER)
    for i, (cx, col) in enumerate([(16, "#ff5f57"), (30, "#febc2e"), (44, "#28c840")]):
        draw.ellipse([cx - 5, 12, cx + 5, 22], fill=col)
    draw.text((60, 10), "terminal  —  genesis init", font=FONT, fill=TITLE_TEXT)

    # Lines
    y = PAD_TOP + 4
    for line in visible:
        x = PAD_X
        segments = parse_line(line)
        for text, color in segments:
            draw.text((x, y), text, font=FONT, fill=color)
            x += len(text) * CHAR_W
        y += LINE_H

    return img


# ---- Script (lines with delays in ms) ----
MINT   = "\x1b[96m"
BWHITE = "\x1b[97m"
BGRAY  = "\x1b[90m"
GREEN  = "\x1b[92m"
YELLOW = "\x1b[93m"
CYAN   = "\x1b[94m"
PURPLE = "\x1b[95m"
RESET  = "\x1b[0m"

SCRIPT = [
    # (text_to_append, hold_ms)
    ("", 400),
    (MINT + "$ " + BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 900),
    ("", 200),
    (PURPLE + "Genesis Architect  v3.0.0  Research first. Build once." + RESET, 300),
    ("", 100),
    (CYAN + "Phase 1" + RESET + BGRAY + "  Scanning GitHub repositories..." + RESET, 350),
    (BGRAY + "  Searching: fastapi celery redis task queue..." + RESET, 450),
    (BWHITE + "  tiangolo/fastapi" + BGRAY + "            (73841 star)" + RESET, 120),
    (BWHITE + "  celery/celery" + BGRAY + "               (24312 star)" + RESET, 80),
    (BWHITE + "  encode/starlette" + BGRAY + "            ( 9821 star)" + RESET, 80),
    (BWHITE + "  pydantic/pydantic" + BGRAY + "           ( 8803 star)" + RESET, 80),
    (BWHITE + "  arq/arq" + BGRAY + "                    ( 2105 star)" + RESET, 80),
    (BGRAY + "  ... and 11 more" + RESET, 200),
    ("", 100),
    (CYAN + "Phase 2" + RESET + BGRAY + "  Mining GitHub Issues for pitfalls..." + RESET, 350),
    (BGRAY + "  celery/celery          -> 20 bug issues" + RESET, 200),
    (BGRAY + "  tiangolo/fastapi       -> 20 bug issues" + RESET, 180),
    (BGRAY + "  encode/starlette       ->  7 bug issues" + RESET, 140),
    (GREEN  + "  Found 47 issues to analyze" + RESET, 200),
    ("", 100),
    (CYAN + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 350),
    (BGRAY + "  Cache: 0 fresh entries for this query" + RESET, 200),
    (BGRAY + "  Generating fresh analysis" + RESET, 150),
    ("", 100),
    (CYAN + "Phase 3b  " + RESET + MINT + "Smart Fork Analysis" + BGRAY + "  (ranked by merged PRs, not stars)" + RESET, 500),
    (BGRAY + "  Scanning forks of celery/celery..." + RESET, 600),
    (MINT + "  1.  " + BWHITE + "ask-celery/celery-redis-retry" + BGRAY + "    12 merged PRs last 6mo" + RESET, 200),
    (MINT + "  2.  " + BWHITE + "contrib/celery-starlette-fix" + BGRAY + "     8 merged PRs last 6mo" + RESET, 160),
    (MINT + "  3.  " + BWHITE + "oss/celery-broker-reconnect" + BGRAY + "      5 merged PRs last 6mo" + RESET, 160),
    (YELLOW + "  Extracted 3 additional pitfalls from active forks" + RESET, 250),
    ("", 100),
    (CYAN + "Phase 4" + RESET + BGRAY + "  Choose your architecture:" + RESET, 300),
    ("", 80),
    (BGRAY + "  A)  Minimalist   simple, small, easy to maintain" + RESET, 80),
    (BGRAY + "  B)  Scalable     full production setup, CI/CD, modular" + RESET, 80),
    (BGRAY + "  C)  Quick        fastest possible scaffold" + RESET, 80),
    (BGRAY + "  D)  Hybrid       minimalist core + scalable extensions" + RESET, 80),
    ("", 80),
    # NLU in action - user types natural language
    (BGRAY + "  Your choice (A/B/C/D or describe in words): " + BWHITE + "give me the scalable approach" + RESET, 1100),
    ("", 200),
    (MINT + "  I'll take that as " + BWHITE + "B (scalable)" + MINT + " - correct? [y/n]" + RESET, 300),
    (BGRAY + "  Confirm [y/n]: " + BWHITE + "y" + RESET, 500),
    ("", 100),
    (GREEN + "  Building Scalable scaffold..." + RESET, 200),
    ("", 100),
    (CYAN + "Phase 5" + RESET + BGRAY + "  Analyzing with LLM and generating scaffold..." + RESET, 700),
    (BGRAY + "  Synthesizing ecosystem patterns from 47 issues + 3 forks..." + RESET, 800),
    (BGRAY + "  Writing RESEARCH.md..." + RESET, 400),
    (BGRAY + "  Writing PITFALLS.md..." + RESET, 300),
    ("", 100),
    (GREEN + "Genesis Architect complete." + RESET, 300),
    ("", 100),
    (MINT + "  Created: " + BWHITE + "fastapi_task_queue/RESEARCH.md" + RESET, 100),
    (MINT + "  Created: " + BWHITE + "fastapi_task_queue/PITFALLS.md" + RESET, 100),
    ("", 100),
    (BGRAY + "  Run `genesis companion` to stay in active development mode." + RESET, 150),
    (YELLOW + "  Tip: solutions cached in .genesis/vault/ - next run will be instant." + RESET, 200),
    ("", 300),
    # Second run: vault HIT
    (MINT + "$ " + BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 900),
    ("", 150),
    (PURPLE + "Genesis Architect  v3.0.0" + RESET, 100),
    ("", 100),
    (CYAN + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 300),
    (GREEN + "  Cache hit!  " + RESET + GREEN + "Fresh solution found (cached 2 minutes ago)" + RESET, 250),
    (BGRAY + "  Skipping LLM call - using cached analysis" + RESET, 150),
    ("", 100),
    (GREEN + "Genesis Architect complete." + RESET + BGRAY + "  (vault run - instant)" + RESET, 400),
    ("", 200),
    (MINT + "$ " + RESET, 800),
]


def build_gif(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    frames = []
    durations = []
    lines = [""]

    for text, hold_ms in SCRIPT:
        if text == "":
            lines.append("")
        else:
            lines.append(text)

        img = render_frame(lines)
        frames.append(img)
        durations.append(max(hold_ms, 60))

    # Save as animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=durations,
        loop=0,
    )
    size_mb = os.path.getsize(output_path) / 1_000_000
    print(f"Saved {output_path}  ({len(frames)} frames, {size_mb:.1f} MB)")


if __name__ == "__main__":
    build_gif("docs/assets/demo.gif")
