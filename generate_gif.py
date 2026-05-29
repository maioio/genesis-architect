"""
Generate demo.gif directly with Pillow - no Electron, no display server needed.
Terminal scrolling: fixed canvas (32 rows), content scrolls up as it grows.
"""
from PIL import Image, ImageDraw, ImageFont
import re, os

FONT_SIZE   = 15
FONT_PATH   = "C:/Windows/Fonts/cascadiacode.ttf"
FONT        = ImageFont.truetype(FONT_PATH, FONT_SIZE)

_bbox       = FONT.getbbox("M")
CHAR_W      = _bbox[2] - _bbox[0]
CHAR_H      = _bbox[3] - _bbox[1]
LINE_H      = CHAR_H + 5

VISIBLE_ROWS = 28         # rows shown at once (terminal viewport)
COLS         = 88
PAD_X        = 20
PAD_TOP      = 40
PAD_BOT      = 20

CANVAS_W     = PAD_X * 2 + COLS * CHAR_W
CANVAS_H     = PAD_TOP + VISIBLE_ROWS * LINE_H + PAD_BOT

BG          = "#0d0f14"
SURFACE     = "#161922"
BORDER      = "#2a3045"
TITLE_TEXT  = "#8892a4"

PALETTE = {
    "0":  "#e8eaf0",
    "90": "#4a5568",
    "91": "#ff7fac",
    "92": "#64ffda",
    "93": "#ffd166",
    "94": "#4fc3f7",
    "95": "#ae89fe",
    "96": "#64ffda",
    "97": "#ffffff",
    "32": "#64ffda",
    "33": "#ffd166",
    "36": "#64ffda",
    "37": "#e8eaf0",
}

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def parse_line(raw: str):
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
            for part in code.split(";"):
                if part in PALETTE:
                    current_color = PALETTE[part]
        last = m.end()
    if last < len(raw):
        segments.append((raw[last:], current_color))
    return segments


def render_frame(lines: list[str]) -> Image.Image:
    """Fixed canvas. Shows last VISIBLE_ROWS lines (scrolls like a real terminal)."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([0, 0, CANVAS_W, PAD_TOP - 1], fill=SURFACE)
    draw.line([0, PAD_TOP - 1, CANVAS_W, PAD_TOP - 1], fill=BORDER, width=1)
    for cx, col in [(16, "#ff5f57"), (30, "#febc2e"), (44, "#28c840")]:
        draw.ellipse([cx - 5, 12, cx + 5, 22], fill=col)
    draw.text((62, 11), "terminal  -  genesis init", font=FONT, fill=TITLE_TEXT)

    # Show last VISIBLE_ROWS lines (terminal scroll behavior)
    visible = lines[-VISIBLE_ROWS:] if len(lines) > VISIBLE_ROWS else lines

    y = PAD_TOP + 6
    for line in visible:
        x = PAD_X
        for text, color in parse_line(line):
            if text:
                draw.text((x, y), text, font=FONT, fill=color)
                x += len(text) * CHAR_W
        y += LINE_H

    return img


MINT   = "\x1b[96m"
BWHITE = "\x1b[97m"
BGRAY  = "\x1b[90m"
GREEN  = "\x1b[92m"
YELLOW = "\x1b[93m"
CYAN   = "\x1b[94m"
PURPLE = "\x1b[95m"
RESET  = "\x1b[0m"

SCRIPT = [
    ("", 400),
    (MINT + "$ " + BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 900),
    ("", 200),
    (PURPLE + "Genesis Architect  v3.0.0  -  Research first. Build once." + RESET, 300),
    ("", 100),
    (CYAN + "Phase 1" + RESET + BGRAY + "  Scanning GitHub repositories..." + RESET, 350),
    (BGRAY + "  Searching: fastapi celery redis task queue..." + RESET, 450),
    (BWHITE + "  tiangolo/fastapi" + BGRAY + "            (73,841 stars)" + RESET, 120),
    (BWHITE + "  celery/celery" + BGRAY + "               (24,312 stars)" + RESET, 90),
    (BWHITE + "  encode/starlette" + BGRAY + "            ( 9,821 stars)" + RESET, 90),
    (BWHITE + "  pydantic/pydantic" + BGRAY + "           ( 8,803 stars)" + RESET, 90),
    (BWHITE + "  arq/arq" + BGRAY + "                     ( 2,105 stars)" + RESET, 90),
    (BGRAY + "  ... and 11 more" + RESET, 200),
    ("", 100),
    (CYAN + "Phase 2" + RESET + BGRAY + "  Mining GitHub Issues for pitfalls..." + RESET, 350),
    (BGRAY + "  celery/celery          -> 20 bug issues" + RESET, 200),
    (BGRAY + "  tiangolo/fastapi       -> 20 bug issues" + RESET, 180),
    (BGRAY + "  encode/starlette       ->  7 bug issues" + RESET, 140),
    (GREEN  + "  Found 47 issues to analyze" + RESET, 250),
    ("", 100),
    (CYAN + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 350),
    (BGRAY + "  Cache: 0 fresh entries for this query" + RESET, 200),
    (BGRAY + "  Generating fresh analysis" + RESET, 150),
    ("", 100),
    (CYAN + "Phase 3b" + RESET + "  " + MINT + "Smart Fork Analysis" + RESET + BGRAY + "  (ranked by merged PRs, not stars)" + RESET, 500),
    (BGRAY + "  Scanning forks of celery/celery..." + RESET, 600),
    (MINT + "  1.  " + BWHITE + "ask-celery/celery-redis-retry" + BGRAY + "    12 merged PRs  (last 6mo)" + RESET, 220),
    (MINT + "  2.  " + BWHITE + "contrib/celery-starlette-fix" + BGRAY + "      8 merged PRs  (last 6mo)" + RESET, 180),
    (MINT + "  3.  " + BWHITE + "oss/celery-broker-reconnect" + BGRAY + "       5 merged PRs  (last 6mo)" + RESET, 180),
    (YELLOW + "  Extracted 3 additional pitfalls from active forks" + RESET, 300),
    ("", 100),
    (CYAN + "Phase 4" + RESET + BGRAY + "  Choose your architecture:" + RESET, 300),
    ("", 80),
    (BGRAY + "  A)  " + BWHITE + "Minimalist" + BGRAY + "   simple, small, easy to maintain" + RESET, 80),
    (BGRAY + "  B)  " + BWHITE + "Scalable  " + BGRAY + "   full production setup, CI/CD, modular" + RESET, 80),
    (BGRAY + "  C)  " + BWHITE + "Quick     " + BGRAY + "   fastest possible scaffold" + RESET, 80),
    (BGRAY + "  D)  " + BWHITE + "Hybrid    " + BGRAY + "   minimalist core + scalable extensions" + RESET, 80),
    ("", 80),
    (BGRAY + "  Your choice (A/B/C/D or describe in words): " + BWHITE + "give me the scalable approach" + RESET, 1200),
    ("", 200),
    (MINT + "  I'll take that as " + BWHITE + "B (scalable)" + MINT + " - correct? [y/n]" + RESET, 400),
    (BGRAY + "  Confirm [y/n]: " + BWHITE + "y" + RESET, 600),
    ("", 100),
    (GREEN + "  Building Scalable scaffold..." + RESET, 200),
    ("", 100),
    (CYAN + "Phase 5" + RESET + BGRAY + "  Analyzing with LLM and generating scaffold..." + RESET, 700),
    (BGRAY + "  Synthesizing patterns from 47 issues + 3 active forks..." + RESET, 900),
    (BGRAY + "  Writing RESEARCH.md..." + RESET, 400),
    (BGRAY + "  Writing PITFALLS.md..." + RESET, 350),
    ("", 100),
    (GREEN + "Genesis Architect complete." + RESET, 400),
    ("", 100),
    (MINT + "  Created: " + BWHITE + "fastapi_task_queue/RESEARCH.md" + RESET, 100),
    (MINT + "  Created: " + BWHITE + "fastapi_task_queue/PITFALLS.md" + RESET, 100),
    ("", 100),
    (BGRAY + "  Run `genesis companion` to stay in active development mode." + RESET, 150),
    (YELLOW + "  Tip: solutions cached in .genesis/vault/ - next run is instant." + RESET, 250),
    ("", 500),
    # ---- Second run: vault HIT ----
    (MINT + "$ " + BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 900),
    ("", 150),
    (PURPLE + "Genesis Architect  v3.0.0" + RESET, 100),
    ("", 100),
    (CYAN + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 300),
    (GREEN + "  Cache hit!  " + BWHITE + "Fresh solution found" + BGRAY + "  (cached 2 minutes ago)" + RESET, 300),
    (BGRAY + "  Skipping LLM call - using cached analysis" + RESET, 150),
    ("", 100),
    (GREEN + "Genesis Architect complete." + RESET + BGRAY + "  (vault run - instant)" + RESET, 500),
    ("", 300),
    (MINT + "$ " + RESET, 1000),
]


def build_gif(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    frames = []
    durations = []
    lines: list[str] = []

    for text, hold_ms in SCRIPT:
        lines.append(text)
        img = render_frame(lines)
        frames.append(img)
        durations.append(max(hold_ms, 60))

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=durations,
        loop=0,
    )
    size_mb = os.path.getsize(output_path) / 1_000_000
    print(f"Canvas: {CANVAS_W}x{CANVAS_H}px  |  {len(frames)} frames  |  {size_mb:.1f} MB")
    print(f"Saved {output_path}")


if __name__ == "__main__":
    build_gif("docs/assets/demo.gif")
