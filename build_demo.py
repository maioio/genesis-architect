"""Build demo.yml for Terminalizer - mocks a full genesis init session."""
import yaml

ESC = ""

def e(code): return ESC + code

RESET   = e("[0m")
BOLD    = e("[1m")
BGRAY   = e("[90m")
BWHITE  = e("[97m")
GREEN   = e("[32m")
CYAN    = e("[36m")
YELLOW  = e("[33m")
MINT    = e("[96m")
PURPLE  = e("[95m")

NL = "\r\n"


def line(text="", delay=80):
    return {"delay": delay, "content": text + NL}


def pause(ms=500):
    return {"delay": ms, "content": ""}


def inline(text, delay=80):
    return {"delay": delay, "content": text}


records = [
    # Opening prompt
    pause(400),
    inline(MINT + "$ " + RESET, 60),
    inline(BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 1200),
    line("", 500),
    line(""),

    # Header
    line(PURPLE + BOLD + "Genesis Architect" + RESET + BGRAY + "  v3.0.0  Research first. Build once." + RESET, 120),
    line(""),

    # Phase 1 - GitHub scan
    line(CYAN + BOLD + "Phase 1" + RESET + BGRAY + "  Scanning GitHub repositories..." + RESET, 250),
    line(BGRAY + "  Searching: fastapi celery redis task queue..." + RESET, 400),
    line(BWHITE + "  tiangolo/fastapi" + BGRAY + "            (73841 " + YELLOW + "star" + BGRAY + ")" + RESET, 120),
    line(BWHITE + "  celery/celery" + BGRAY + "               (24312 " + YELLOW + "star" + BGRAY + ")" + RESET, 80),
    line(BWHITE + "  encode/starlette" + BGRAY + "            ( 9821 " + YELLOW + "star" + BGRAY + ")" + RESET, 80),
    line(BWHITE + "  pydantic/pydantic" + BGRAY + "           ( 8803 " + YELLOW + "star" + BGRAY + ")" + RESET, 80),
    line(BWHITE + "  arq/arq" + BGRAY + "                    ( 2105 " + YELLOW + "star" + BGRAY + ")" + RESET, 80),
    line(BGRAY + "  ... and 11 more" + RESET, 100),
    line(""),

    # Phase 2 - Issue mining
    line(CYAN + BOLD + "Phase 2" + RESET + BGRAY + "  Mining GitHub Issues for pitfalls..." + RESET, 300),
    line(BGRAY + "  celery/celery          -> 20 bug issues" + RESET, 200),
    line(BGRAY + "  tiangolo/fastapi       -> 20 bug issues" + RESET, 180),
    line(BGRAY + "  encode/starlette       ->  7 bug issues" + RESET, 160),
    line(GREEN  + "  Found 47 issues to analyze" + RESET, 120),
    line(""),

    # Phase 3 - Vault check (miss)
    line(CYAN + BOLD + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 300),
    line(BGRAY + "  Cache: 0 fresh entries for this query" + RESET, 200),
    line(BGRAY + "  Generating fresh analysis" + RESET, 150),
    line(""),

    # Smart Fork Analysis
    line(CYAN + BOLD + "Phase 3b" + RESET + "  " + MINT + BOLD + "Smart Fork Analysis" + RESET + BGRAY + " (ranked by merged PRs, not stars)" + RESET, 450),
    line(BGRAY + "  Scanning forks of celery/celery..." + RESET, 600),
    line(MINT + "  1." + BWHITE + "  ask-celery/celery-redis-retry" + BGRAY + "    12 merged PRs last 6mo" + RESET, 220),
    line(MINT + "  2." + BWHITE + "  contrib/celery-starlette-fix" + BGRAY + "     8 merged PRs last 6mo" + RESET, 180),
    line(MINT + "  3." + BWHITE + "  oss/celery-broker-reconnect" + BGRAY + "      5 merged PRs last 6mo" + RESET, 180),
    line(YELLOW + "  Extracted 3 additional pitfalls from active forks" + RESET, 200),
    line(""),

    # Phase 4 - NLU architecture choice
    line(CYAN + BOLD + "Phase 4" + RESET + BGRAY + "  Choose your architecture:" + RESET, 300),
    line(""),
    line(BGRAY + "  A)" + BWHITE + " Minimalist" + BGRAY + "   simple, small, easy to maintain" + RESET, 80),
    line(BGRAY + "  B)" + BWHITE + " Scalable  " + BGRAY + "   full production setup, CI/CD, modular" + RESET, 80),
    line(BGRAY + "  C)" + BWHITE + " Quick     " + BGRAY + "   fastest possible scaffold" + RESET, 80),
    line(BGRAY + "  D)" + BWHITE + " Hybrid    " + BGRAY + "   minimalist core + scalable extensions" + RESET, 80),
    line(""),
    inline(BGRAY + "  Your choice (A/B/C/D or describe in words): " + RESET, 200),
    pause(700),
    # User types natural language (NLU in action)
    inline(BWHITE + "give me the scalable approach" + RESET, 1200),
    line("", 500),
    line(""),
    line(MINT + "  I'll take that as " + BOLD + "B (scalable)" + RESET + MINT + " - correct? [y/n]" + RESET, 200),
    inline(BGRAY + "  Confirm [y/n]: " + RESET, 200),
    pause(600),
    inline(BWHITE + "y" + RESET, 300),
    line("", 300),
    line(""),
    line(GREEN + "  Building Scalable scaffold..." + RESET, 150),
    line(""),

    # Phase 5 - LLM + generation
    line(CYAN + BOLD + "Phase 5" + RESET + BGRAY + "  Analyzing with LLM and generating scaffold..." + RESET, 600),
    line(BGRAY + "  Synthesizing ecosystem patterns..." + RESET, 800),
    line(BGRAY + "  Extracting pitfalls from 47 issues + 3 active forks..." + RESET, 700),
    line(BGRAY + "  Writing RESEARCH.md..." + RESET, 400),
    line(BGRAY + "  Writing PITFALLS.md..." + RESET, 300),
    line(""),

    # Result
    line(GREEN + BOLD + "Genesis Architect complete." + RESET, 200),
    line(""),
    line(MINT + "  Created: " + BWHITE + "fastapi_task_queue/RESEARCH.md" + RESET, 100),
    line(MINT + "  Created: " + BWHITE + "fastapi_task_queue/PITFALLS.md" + RESET, 100),
    line(""),
    line(BGRAY + "  Next: cd fastapi_task_queue and review RESEARCH.md" + RESET, 100),
    line(BGRAY + "  Run " + MINT + "`genesis companion`" + BGRAY + " to stay in active development mode." + RESET, 100),
    line(""),
    line(YELLOW + BOLD + "  Tip:" + RESET + YELLOW + " Solutions cached in .genesis/vault/ - next run will be instant." + RESET, 200),
    line(""),

    # Second run showing vault HIT
    pause(1000),
    inline(MINT + "$ " + RESET, 60),
    inline(BWHITE + "genesis init " + YELLOW + '"a FastAPI task queue with Celery and Redis"' + RESET, 1200),
    line("", 500),
    line(""),
    line(PURPLE + BOLD + "Genesis Architect" + RESET + BGRAY + "  v3.0.0" + RESET, 80),
    line(""),
    line(CYAN + BOLD + "Phase 3" + RESET + BGRAY + "  Checking knowledge vault..." + RESET, 300),
    line(GREEN + BOLD + "  Cache hit!" + RESET + GREEN + "  Fresh solution from vault (cached 2 min ago)" + RESET, 150),
    line(BGRAY + "  Skipping LLM call - using cached analysis" + RESET, 100),
    line(""),
    line(GREEN + BOLD + "Genesis Architect complete." + RESET + BGRAY + "  (vault run - instant)" + RESET, 200),
    line(""),

    # Final prompt
    pause(1500),
    inline(MINT + "$ " + RESET, 60),
    pause(1000),
]

doc = {
    "config": {
        "command": "cmd",
        "cwd": "C:\\Users\\User",
        "env": {"recording": True},
        "cols": 100,
        "rows": 32,
        "repeat": 0,
        "quality": 100,
        "frameDelay": "auto",
        "maxIdleTime": 3000,
        "frameBox": {
            "type": "floating",
            "title": "Genesis Architect v3.0.0",
            "style": {"border": "0px black solid"},
        },
        "cursorStyle": "block",
        "fontFamily": "Cascadia Code, Consolas, Courier New, monospace",
        "fontSize": 13,
        "lineHeight": 1.2,
        "letterSpacing": 0,
        "theme": {
            "background": "#0d0f14",
            "foreground": "#e8eaf0",
            "cursor": "#7c6af7",
            "black": "#0d0f14",
            "red": "#ff6b6b",
            "green": "#64ffda",
            "yellow": "#ffd166",
            "blue": "#4fc3f7",
            "magenta": "#7c6af7",
            "cyan": "#64ffda",
            "white": "#e8eaf0",
            "brightBlack": "#4a5568",
            "brightRed": "#ff7fac",
            "brightGreen": "#64ffda",
            "brightYellow": "#ffd166",
            "brightBlue": "#4fc3f7",
            "brightMagenta": "#ae89fe",
            "brightCyan": "#64ffda",
            "brightWhite": "#ffffff",
        },
    },
    "records": records,
}

out = yaml.dump(doc, allow_unicode=True, default_flow_style=False, width=10000)
with open("demo.yml", "w", encoding="utf-8") as f:
    f.write(out)

print(f"Written demo.yml with {len(records)} records")
