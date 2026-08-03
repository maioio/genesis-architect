"""
Genesis — downloadable HTML progress reports.

Generates a self-contained HTML report of a build phase (what shipped, tests,
what works vs. what's next), in the live-site design language. Used to produce a
report after each Companion build phase.

Pure presentation; no external assets except fonts. Deterministic.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class ReportItem:
    label: str
    status: str = "done"        # done | partial | next | blocked
    detail: str = ""


@dataclass
class PhaseReport:
    title: str
    subtitle: str = ""
    version: str = ""
    tests_passing: int | None = None
    shipped: list = field(default_factory=list)      # list[ReportItem]
    works_now: list = field(default_factory=list)     # list[str]
    coming_next: list = field(default_factory=list)   # list[str]
    notes: list = field(default_factory=list)         # list[str]
    date_: str = ""


_STATUS = {
    "done": ("✓", "#1a7f4b", "done"),
    "partial": ("◐", "#b26a00", "partial"),
    "next": ("→", "#0b62f5", "next"),
    "blocked": ("✕", "#c0392b", "blocked"),
}


def _esc(s: object) -> str:
    return _html.escape(str(s))


def render_report(r: PhaseReport) -> str:
    d = r.date_ or date.today().isoformat()

    def items(rows: list) -> str:
        out = []
        for it in rows:
            glyph, color, word = _STATUS.get(it.status, _STATUS["done"])
            out.append(
                f'<div class="row"><span class="st" style="color:{color}">{glyph}</span>'
                f'<div><b>{_esc(it.label)}</b>'
                f'<span class="badge" style="color:{color};border-color:{color}33">{word}</span>'
                + (f'<div class="dt">{_esc(it.detail)}</div>' if it.detail else "")
                + "</div></div>"
            )
        return "".join(out)

    def bullets(items_: list) -> str:
        return "".join(f"<li>{_esc(x)}</li>" for x in items_)

    tests = (f'<span class="chip">✓ {r.tests_passing} tests passing</span>'
             if r.tests_passing is not None else "")
    ver = f'<span class="chip">{_esc(r.version)}</span>' if r.version else ""

    works = (f'<section><h2>What works right now</h2><ul class="clean">'
             f'{bullets(r.works_now)}</ul></section>' if r.works_now else "")
    nxt = (f'<section><h2>Coming next</h2><ul class="clean">'
           f'{bullets(r.coming_next)}</ul></section>' if r.coming_next else "")
    notes = (f'<section class="notes"><h2>Notes</h2><ul class="clean">'
             f'{bullets(r.notes)}</ul></section>' if r.notes else "")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(r.title)} — Genesis Progress Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..600;1,9..144,400..600&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--paper:#f4f2ec;--ink:#16140f;--ink2:#4a463d;--muted:#7c776b;--line:#dcd8cd;
--accent:#0b62f5;--card:#fbfaf7;--white:#fff;
--sans:'Geist',sans-serif;--mono:'Geist Mono',monospace;--serif:'Fraunces',serif}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.6;padding:56px 20px}}
.wrap{{max-width:820px;margin:0 auto;background:var(--white);border:1px solid var(--line);border-radius:18px;
padding:48px clamp(24px,5vw,56px);box-shadow:0 2px 4px #16140f08,0 24px 48px -12px #16140f1f}}
.mark{{display:inline-flex;align-items:center;gap:10px;font-family:var(--mono);font-size:12px;letter-spacing:.18em;
text-transform:uppercase;color:var(--accent);margin-bottom:18px}}
.mark::before{{content:'';width:22px;height:1px;background:var(--accent)}}
h1{{font-family:var(--serif);font-weight:400;font-size:clamp(30px,5vw,46px);letter-spacing:-.02em;line-height:1.05;margin-bottom:8px}}
.sub{{color:var(--ink2);font-size:17px;margin-bottom:18px}}
.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:34px}}
.chip{{font-family:var(--mono);font-size:12px;color:var(--ink2);border:1px solid var(--line);border-radius:999px;
padding:5px 12px;background:var(--card)}}
h2{{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
margin:30px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.row{{display:flex;gap:12px;padding:11px 0;border-bottom:1px solid var(--line)}}
.row:last-child{{border-bottom:none}}
.st{{font-size:16px;flex-shrink:0;margin-top:1px;width:18px;text-align:center}}
.row b{{font-weight:600}}
.badge{{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.05em;
border:1px solid;border-radius:999px;padding:1px 8px;margin-left:9px;vertical-align:2px}}
.dt{{color:var(--muted);font-size:13.5px;margin-top:3px}}
ul.clean{{list-style:none}}
ul.clean li{{padding:7px 0 7px 22px;position:relative;font-size:14.5px;color:var(--ink2)}}
ul.clean li::before{{content:'—';position:absolute;left:0;color:var(--accent)}}
.notes{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 20px 16px;margin-top:30px}}
.foot{{margin-top:36px;font-family:var(--mono);font-size:11px;color:var(--muted);text-align:center}}
@media print{{body{{padding:0;background:#fff}}.wrap{{border:none;box-shadow:none}}}}
</style></head>
<body><div class="wrap">
  <div class="mark">Genesis Architect PRO · Progress Report</div>
  <h1>{_esc(r.title)}</h1>
  {f'<p class="sub">{_esc(r.subtitle)}</p>' if r.subtitle else ''}
  <div class="meta"><span class="chip">{_esc(d)}</span>{ver}{tests}</div>
  <section><h2>Shipped this phase</h2>{items(r.shipped)}</section>
  {works}{nxt}{notes}
  <div class="foot">Genesis Architect PRO — private build report · pro/main</div>
</div></body></html>"""


def write_report(r: PhaseReport, out_dir: Path | str = ".",
                 name: str = "") -> Path | None:
    """Write the report to <out_dir>/<name>.html. Returns the path or None."""
    safe = (name or r.title).lower().replace(" ", "_")
    safe = "".join(c for c in safe if c.isalnum() or c in "-_")[:80] or "report"
    target = Path(out_dir) / f"{safe}.html"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_report(r), encoding="utf-8")
        return target
    except OSError:
        return None
