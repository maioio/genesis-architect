"""
UI Engine for Genesis Architect (Pro).

Two presentation modes from the v2 plan, built with ZERO customer setup:

  - **Compact Floating Assistant** — a small status panel: current state, the one
    recommended action, warnings (CVEs/drift), a link to the Canvas.
  - **Full Canvas Workspace** — the deep, read-mostly view: architecture score,
    dependency/knowledge graph, recovery map, drift, evidence packs, reports.

Design decision (honors the no-setup packaging promise): instead of requiring a
Tauri/React build (Node toolchain), the UI is rendered as a SINGLE self-contained
HTML file that reads the JSON/Markdown artifacts the engines already write under
`.genesis/`. It opens directly in any browser — no server, no Node, no build.
The same generated file is what a future desktop (Tauri) shell would embed, so
no engine work is blocked and nothing is thrown away.

This module is pure presentation: it reads engine artifacts and emits HTML. It
contains no business logic and never raises on missing/partial data — absent
artifacts render as honest "not available yet" states (honesty clause).
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Reading engine artifacts (all optional; missing -> None)
# ---------------------------------------------------------------------------

def _genesis(project_root: Path) -> Path:
    return Path(project_root) / ".genesis"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (json.JSONDecodeError, OSError):
        return None


@dataclass
class WorkspaceState:
    """A snapshot of what the engines currently know, for the UI to render."""
    architecture_score: float | None = None
    score_label: str = ""
    graph_nodes: int = 0
    graph_edges: int = 0
    cve_count: int = 0
    drift_count: int = 0
    risk_count: int = 0
    recommended_action: str = ""
    status: str = "idle"
    warnings: list | None = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def collect_state(project_root: Path | str = ".") -> WorkspaceState:
    """Assemble a WorkspaceState from whatever artifacts exist under .genesis/.
    Everything is optional; nothing is fabricated."""
    g = _genesis(Path(project_root))
    st = WorkspaceState()

    score = _read_json(g / "model.json") or _read_json(g / "score.json")
    if isinstance(score, dict):
        total = score.get("total", score.get("architecture_score"))
        if isinstance(total, (int, float)):
            st.architecture_score = float(total)
            st.score_label = str(score.get("score_label", score.get("label", "")))

    graph = _read_json(g / "knowledge" / "graph.json")
    if isinstance(graph, dict):
        nodes = graph.get("nodes") or {}
        edges = graph.get("edges") or []
        st.graph_nodes = len(nodes)
        st.graph_edges = len(edges)
        st.cve_count = sum(1 for n in nodes.values()
                           if isinstance(n, dict) and n.get("type") == "cve")
        st.drift_count = sum(1 for n in nodes.values()
                             if isinstance(n, dict) and n.get("type") == "drift")
        st.risk_count = sum(1 for n in nodes.values()
                            if isinstance(n, dict) and n.get("type") == "risk")

    # derive warnings + recommended action (honest, data-driven)
    if st.cve_count:
        st.warnings.append(f"{st.cve_count} CVE node(s) in the graph")
    if st.drift_count:
        st.warnings.append(f"drift in {st.drift_count} module(s)")
    if st.architecture_score is not None and st.architecture_score < 60:
        st.warnings.append(f"architecture score low ({st.architecture_score:.0f})")

    if st.cve_count:
        st.recommended_action = "Open security / recovery report"
    elif st.drift_count:
        st.recommended_action = "Open drift map"
    elif st.architecture_score is None:
        st.recommended_action = "Run an analysis (genesis recover .)"
    else:
        st.recommended_action = "Review architecture"
    st.status = "ready" if st.architecture_score is not None else "no analysis yet"
    return st


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _esc(s: object) -> str:
    return html.escape(str(s))


def _floating_assistant_html(st: WorkspaceState) -> str:
    warn_html = "".join(
        f'<div class="ga-warn">⚠ {_esc(w)}</div>' for w in st.warnings
    ) or '<div class="ga-ok">No warnings.</div>'
    score = (f'{st.architecture_score:.0f}' if st.architecture_score is not None
             else "—")
    action = _esc(st.recommended_action)
    return f"""
  <div class="ga-fab" id="gaFab" onclick="gaToggle()">G</div>
  <div class="ga-panel" id="gaPanel">
    <div class="ga-head">
      <span class="ga-brand">Genesis</span>
      <span class="ga-x" onclick="gaToggle()">×</span>
    </div>
    <div class="ga-pill">{_esc(st.status)}</div>
    <div class="ga-score"><span>{score}</span><label>arch score {_esc(st.score_label)}</label></div>
    <div class="ga-action">→ {action}</div>
    <div class="ga-warns">{warn_html}</div>
    <a class="ga-open" href="#canvas">Open Canvas ↧</a>
  </div>"""


def _canvas_html(st: WorkspaceState, project_root: Path) -> str:
    g = _genesis(project_root)
    have_graph = (g / "knowledge" / "graph.json").exists()

    def card(title: str, value: str, sub: str = "", muted: bool = False) -> str:
        cls = "gc-card muted" if muted else "gc-card"
        return (f'<div class="{cls}"><div class="gc-v">{_esc(value)}</div>'
                f'<div class="gc-t">{_esc(title)}</div>'
                f'<div class="gc-s">{_esc(sub)}</div></div>')

    score = (f'{st.architecture_score:.0f}/100' if st.architecture_score is not None
             else "not run")
    cards = "".join([
        card("Architecture score", score, st.score_label,
             muted=st.architecture_score is None),
        card("Knowledge graph", f"{st.graph_nodes} nodes",
             f"{st.graph_edges} edges", muted=not have_graph),
        card("Open CVEs", str(st.cve_count),
             "in graph" if have_graph else "no graph yet", muted=not st.cve_count),
        card("Drift", str(st.drift_count), "modules", muted=not st.drift_count),
        card("Risk zones", str(st.risk_count), "do-not-touch", muted=not st.risk_count),
    ])
    empty = ("" if have_graph else
             '<p class="gc-empty">No analysis artifacts yet. Run '
             '<code>genesis recover .</code> to populate the Canvas. '
             '(Honest empty state — nothing is fabricated.)</p>')
    return f"""
  <section id="canvas" class="gc-wrap">
    <h2 class="gc-h">Canvas Workspace</h2>
    <div class="gc-grid">{cards}</div>
    {empty}
  </section>"""


_CSS = """
:root{--bg:#0d1017;--panel:#141922;--rim:#232d42;--head:#e4ecf8;--dim:#8da3c0;
--muted:#3d4f6e;--acc:#5b8ef0;--acc2:#3ecf8e;--amber:#f59e0b;--purple:#9b7bf7}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',system-ui,sans-serif}
body{background:var(--bg);color:var(--head);padding:40px 5% 120px}
h1{font-size:28px;letter-spacing:-1px;margin-bottom:6px}
.sub{color:var(--dim);margin-bottom:36px;font-size:15px}
/* floating assistant */
.ga-fab{position:fixed;right:24px;bottom:24px;width:52px;height:52px;border-radius:14px;
background:linear-gradient(135deg,var(--acc),var(--purple));color:#fff;display:grid;
place-items:center;font-weight:800;font-size:20px;cursor:pointer;z-index:1000;
box-shadow:0 8px 30px rgba(91,142,240,.4)}
.ga-panel{position:fixed;right:24px;bottom:88px;width:300px;background:var(--panel);
border:1px solid var(--rim);border-radius:16px;padding:18px;z-index:1000;display:none;
box-shadow:0 20px 60px rgba(0,0,0,.5)}
.ga-panel.open{display:block}
.ga-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.ga-brand{font-weight:800;color:var(--acc)}
.ga-x{cursor:pointer;color:var(--dim);font-size:20px}
.ga-pill{display:inline-block;font-size:11px;letter-spacing:1px;text-transform:uppercase;
color:var(--acc2);border:1px solid var(--rim);border-radius:100px;padding:3px 10px;margin-bottom:14px}
.ga-score{display:flex;align-items:baseline;gap:8px;margin-bottom:14px}
.ga-score span{font-size:34px;font-weight:900}
.ga-score label{color:var(--dim);font-size:12px}
.ga-action{font-size:14px;color:var(--head);margin-bottom:12px}
.ga-warn{font-size:12.5px;color:var(--amber);margin-bottom:4px}
.ga-ok{font-size:12.5px;color:var(--acc2)}
.ga-open{display:block;margin-top:14px;font-size:13px;color:var(--acc);text-decoration:none}
/* canvas */
.gc-wrap{margin-top:40px}
.gc-h{font-size:20px;margin-bottom:18px}
.gc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.gc-card{background:var(--panel);border:1px solid var(--rim);border-radius:14px;padding:20px}
.gc-card.muted{opacity:.5}
.gc-v{font-size:26px;font-weight:800;color:var(--head)}
.gc-t{font-size:13px;color:var(--dim);margin-top:6px}
.gc-s{font-size:11px;color:var(--muted);margin-top:2px}
.gc-empty{margin-top:24px;color:var(--dim);font-size:14px}
.gc-empty code{background:#07090d;border:1px solid var(--rim);border-radius:6px;
padding:2px 8px;color:var(--acc2);font-family:monospace}
"""

_JS = """
function gaToggle(){document.getElementById('gaPanel').classList.toggle('open');}
"""


def render_workspace(project_root: Path | str = ".") -> str:
    """Return a single self-contained HTML document (Floating Assistant + Canvas)
    rendered from the current .genesis/ artifacts. No external assets, no build."""
    root = Path(project_root)
    st = collect_state(root)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Genesis Architect — Workspace</title>
<style>{_CSS}</style></head>
<body>
  <h1>Genesis Architect — Workspace</h1>
  <p class="sub">Live view of this project's engine outputs. Read-only; actions go through approval gates.</p>
  {_canvas_html(st, root)}
  {_floating_assistant_html(st)}
  <script>{_JS}</script>
</body></html>"""


def write_workspace(project_root: Path | str = ".",
                    out_name: str = "workspace.html") -> Path | None:
    """Generate the workspace HTML and write it to .genesis/ui/<out_name>.
    Returns the path, or None on I/O error. Opens directly in a browser."""
    root = Path(project_root)
    target = _genesis(root) / "ui" / out_name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_workspace(root), encoding="utf-8")
        return target
    except OSError:
        return None
