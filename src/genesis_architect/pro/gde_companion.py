"""Genesis Decision Engine — Companion layer (Phase 0 + Phase 1).

Phase 0: Gate miss-rate instrumentation.
    Reads .genesis/gde_session.json and .genesis/gde_decision_log.jsonl and
    computes how often approval gates are left unanswered for >5 minutes.
    This is the data that justifies (or rules out) a persistent UI overlay.

Phase 1: Two lightweight ambient surfaces, both zero-new-runtime:
    1. OS notifications via ``plyer`` (single optional pip dep).
       Fires when a BLOCK_AND_ASK or HARD_BLOCK gate is presented.
    2. Health page served by Python stdlib ``http.server`` on a fixed port.
       A self-contained HTML file that polls gde_session.json every 2 s.

Neither surface requires FastAPI, Node, Electron, Docker, or any system lib.

Public API
----------
CompanionInstrumentation   — gate miss-rate analysis from session files
GateNotifier               — OS notifications for gate events (plyer optional)
HealthPageServer           — stdlib HTTP server for the health page
"""

from __future__ import annotations

import datetime
import http.server
import json
import pathlib
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GATE_MISS_THRESHOLD_SECONDS = 300  # 5 minutes
_DEFAULT_PORT = 7433
_PORT_SCAN_RANGE = 10               # try 7433–7442 if default is taken
_SESSION_FILE = pathlib.Path(".genesis") / "gde_session.json"
_DECISION_LOG = pathlib.Path(".genesis") / "gde_decision_log.jsonl"


# ---------------------------------------------------------------------------
# Phase 0 — instrumentation
# ---------------------------------------------------------------------------


@dataclass
class GateMissStats:
    """Gate miss-rate statistics computed from session files."""

    total_gates_presented: int = 0
    missed_gates: int = 0           # presented but no response within threshold
    miss_rate: float = 0.0          # missed / total (0.0 – 1.0)
    avg_response_seconds: float = 0.0
    sessions_analysed: int = 0
    threshold_seconds: int = _GATE_MISS_THRESHOLD_SECONDS

    @property
    def companion_justified(self) -> bool:
        """True if miss rate exceeds 15% — council threshold for building Companion."""
        return self.miss_rate > 0.15 and self.total_gates_presented >= 5


class CompanionInstrumentation:
    """Reads session + decision log files and computes gate miss-rate stats.

    Usage::

        stats = CompanionInstrumentation(project_dir=Path(".")).analyse()
        if stats.companion_justified:
            print(f"Miss rate {stats.miss_rate:.0%} — Companion is justified")
    """

    def __init__(
        self,
        project_dir: pathlib.Path | str = ".",
        threshold_seconds: int = _GATE_MISS_THRESHOLD_SECONDS,
    ) -> None:
        self.project_dir = pathlib.Path(project_dir)
        self.threshold_seconds = threshold_seconds

    def analyse(self) -> GateMissStats:
        """Compute gate miss-rate from the current project's session file."""
        stats = GateMissStats(threshold_seconds=self.threshold_seconds)
        session_file = self.project_dir / _SESSION_FILE
        if not session_file.exists():
            return stats

        try:
            raw = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            return stats

        stats.sessions_analysed = 1
        gate_sections = (
            raw.get("gate_report", {}).get("blocks", [])
            + raw.get("gate_report", {}).get("hard_blocks", [])
        )

        response_times: list[float] = []

        for gate in gate_sections:
            presented_at = gate.get("presented_at", "")
            responded_at = gate.get("responded_at", "")
            if not presented_at:
                continue

            stats.total_gates_presented += 1

            if not responded_at:
                # Gate was never responded to — definite miss
                stats.missed_gates += 1
                continue

            try:
                t_presented = datetime.datetime.fromisoformat(presented_at)
                t_responded = datetime.datetime.fromisoformat(responded_at)
                delta = (t_responded - t_presented).total_seconds()
                if delta > self.threshold_seconds:
                    stats.missed_gates += 1
                else:
                    response_times.append(delta)
            except ValueError:
                stats.missed_gates += 1

        if stats.total_gates_presented > 0:
            stats.miss_rate = stats.missed_gates / stats.total_gates_presented
        if response_times:
            stats.avg_response_seconds = sum(response_times) / len(response_times)

        return stats


# ---------------------------------------------------------------------------
# Phase 1a — OS notifications
# ---------------------------------------------------------------------------


class GateNotifier:
    """Fire OS desktop notifications when a gate blocks the GDE.

    Requires ``plyer`` (``pip install plyer``) but degrades gracefully if it
    is not installed — the GDE continues normally, notifications are skipped.

    Usage::

        notifier = GateNotifier(project_name="my-api")
        notifier.notify_gate("SECURITY_RISK", "Security risk in proposed changes")
        notifier.notify_approval_needed(pending_writes=3)
    """

    def __init__(self, project_name: str = "Genesis") -> None:
        self.project_name = project_name
        self._plyer_available = self._check_plyer()

    @staticmethod
    def _check_plyer() -> bool:
        try:
            import plyer  # noqa: F401
            return True
        except ImportError:
            return False

    def available(self) -> bool:
        return self._plyer_available

    def notify(self, title: str, message: str, timeout: int = 8) -> bool:
        """Send a desktop notification. Returns True if sent, False if plyer missing."""
        if not self._plyer_available:
            return False
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Genesis PRO",
                timeout=timeout,
            )
            return True
        except Exception:
            return False

    def notify_gate(self, gate_id: str, reason: str) -> bool:
        """Notify that a gate has fired and needs attention."""
        return self.notify(
            title=f"Genesis PRO — {self.project_name}",
            message=f"Gate: {gate_id}\n{reason}\nOpen the health page to respond.",
        )

    def notify_approval_needed(self, pending_writes: int) -> bool:
        """Notify that approval is needed before writes are committed."""
        return self.notify(
            title="Genesis PRO — Approval needed",
            message=f"{pending_writes} write operation(s) pending.\nRun `genesis decide` or open the health page.",
        )

    def notify_session_complete(self, mode: str, confidence: float) -> bool:
        """Notify that a GDE session completed."""
        return self.notify(
            title="Genesis PRO — Session complete",
            message=f"Mode: {mode.upper()} | Confidence: {confidence:.0%}",
            timeout=5,
        )


# ---------------------------------------------------------------------------
# Phase 1b — Health page server (stdlib only)
# ---------------------------------------------------------------------------

_HEALTH_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Genesis PRO — Project Health</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e;
    --green: #3fb950; --yellow: #d29922; --red: #f85149; --blue: #58a6ff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font: 14px/1.5 "SF Mono", "Fira Code", monospace; }
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 14px; font-weight: 600; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 12px; background: var(--border); }
  .badge.ok  { background: #1a3a1f; color: var(--green); }
  .badge.warn{ background: #3a2a00; color: var(--yellow); }
  .badge.err { background: #3a0000; color: var(--red); }
  main { padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 900px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 12px; }
  .metric { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); }
  .metric:last-child { border-bottom: none; }
  .metric .val { font-weight: 600; }
  .metric .val.ok   { color: var(--green); }
  .metric .val.warn { color: var(--yellow); }
  .metric .val.err  { color: var(--red); }
  .gate-list { list-style: none; }
  .gate-list li { padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
  .gate-list li:last-child { border-bottom: none; }
  .gate-list .tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-right: 6px; }
  .tag.block { background: #3a0000; color: var(--red); }
  .tag.warn  { background: #3a2a00; color: var(--yellow); }
  .tag.pass  { background: #1a3a1f; color: var(--green); }
  #status-line { padding: 8px 20px; background: var(--surface); border-top: 1px solid var(--border); font-size: 12px; color: var(--muted); position: fixed; bottom: 0; width: 100%; }
  .spinner { display: inline-block; width: 8px; height: 8px; border: 1px solid var(--muted); border-top-color: var(--blue); border-radius: 50%; animation: spin .8s linear infinite; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { color: var(--muted); font-size: 12px; }
  .action-btn { display: inline-block; margin-top: 10px; padding: 6px 14px; background: var(--border); border: none; border-radius: 6px; color: var(--text); font-family: inherit; font-size: 12px; cursor: pointer; }
  .action-btn:hover { background: #3a4049; }
</style>
</head>
<body>
<header>
  <h1>Genesis PRO — Project Health</h1>
  <span id="session-badge" class="badge">Loading…</span>
</header>
<main id="main">
  <div class="card" id="card-session">
    <h2>Session</h2>
    <div class="metric"><span>Mode</span><span class="val" id="mode">—</span></div>
    <div class="metric"><span>Stage</span><span class="val" id="stage">—</span></div>
    <div class="metric"><span>Confidence</span><span class="val" id="confidence">—</span></div>
    <div class="metric"><span>Risk</span><span class="val" id="risk">—</span></div>
    <div class="metric"><span>Session ID</span><span class="val" id="session-id" style="font-size:11px;color:var(--muted)">—</span></div>
    <div class="metric"><span>Started</span><span class="val" id="started-at" style="font-size:11px;color:var(--muted)">—</span></div>
  </div>
  <div class="card" id="card-gates">
    <h2>Gates</h2>
    <ul class="gate-list" id="gate-list"><li class="empty">No gates fired</li></ul>
  </div>
  <div class="card" id="card-engines">
    <h2>Engines</h2>
    <div id="engine-list"><span class="empty">No engines ran</span></div>
  </div>
  <div class="card" id="card-writes">
    <h2>Pending Writes</h2>
    <div id="writes-list"><span class="empty">None</span></div>
    <div id="approval-hint"></div>
  </div>
</main>
<div id="status-line"><span class="spinner"></span><span id="status-text">Connecting…</span></div>
<script>
const POLL_MS = 2000;
let lastMod = null;

function cls(val) {
  if (val === undefined || val === null) return '';
  const s = String(val).toLowerCase();
  if (['critical','failed','error','hard_block','block'].some(x => s.includes(x))) return 'err';
  if (['warn','degraded','medium'].some(x => s.includes(x))) return 'warn';
  if (['pass','success','ok','good','excellent','stable'].some(x => s.includes(x))) return 'ok';
  return '';
}

function fmt(v) { return v ?? '—'; }
function fmtConf(v) { return v !== undefined ? Math.round(v * 100) + '%' : '—'; }
function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}
function gateTag(action) {
  if (!action) return '';
  const a = action.toLowerCase();
  if (a.includes('hard') || a.includes('block')) return '<span class="tag block">BLOCK</span>';
  if (a.includes('warn')) return '<span class="tag warn">WARN</span>';
  return '<span class="tag pass">PASS</span>';
}

async function poll() {
  try {
    const r = await fetch('/session.json?_=' + Date.now());
    if (!r.ok) { setStatus('Session file not found — waiting…', false); return; }
    const d = await r.json();

    document.getElementById('session-badge').textContent = d.stage ?? 'idle';
    document.getElementById('session-badge').className = 'badge ' + cls(d.stage);
    document.getElementById('mode').textContent = fmt(d.mode);
    document.getElementById('mode').className = 'val';
    document.getElementById('stage').textContent = fmt(d.stage);
    document.getElementById('stage').className = 'val ' + cls(d.stage);
    const conf = d.overall_confidence;
    document.getElementById('confidence').textContent = fmtConf(conf);
    document.getElementById('confidence').className = 'val ' + (conf >= 0.6 ? 'ok' : conf >= 0.4 ? 'warn' : 'err');
    document.getElementById('risk').textContent = fmt(d.project_risk_level);
    document.getElementById('risk').className = 'val ' + cls(d.project_risk_level);
    document.getElementById('session-id').textContent = (d.session_id ?? '').slice(0, 8) + '…';
    document.getElementById('started-at').textContent = fmtTime(d.session_started_at);

    // Gates
    const gr = d.gate_report ?? {};
    const gates = [
      ...(gr.hard_blocks ?? []),
      ...(gr.blocks ?? []),
      ...(gr.warnings ?? []),
    ];
    const gl = document.getElementById('gate-list');
    if (gates.length === 0) {
      gl.innerHTML = '<li class="empty">No gates fired</li>';
    } else {
      gl.innerHTML = gates.map(g =>
        `<li>${gateTag(g.action)}<strong>${g.gate_id}</strong> — ${g.reason ?? ''}</li>`
      ).join('');
    }

    // Engines
    const engines = d.engine_results ?? {};
    const keys = Object.keys(engines);
    const el = document.getElementById('engine-list');
    if (keys.length === 0) {
      el.innerHTML = '<span class="empty">No engines ran</span>';
    } else {
      el.innerHTML = keys.map(k => {
        const e = engines[k];
        return `<div class="metric"><span>${k}</span><span class="val ${cls(e.status)}">${e.status ?? '—'}</span></div>`;
      }).join('');
    }

    // Writes
    const writes = d.pending_write_operations ?? [];
    const wl = document.getElementById('writes-list');
    const hint = document.getElementById('approval-hint');
    if (writes.length === 0) {
      wl.innerHTML = '<span class="empty">None</span>';
      hint.innerHTML = '';
    } else {
      wl.innerHTML = writes.map(w =>
        `<div class="metric"><span style="font-size:12px">${w.operation_id}</span><span class="val warn">${w.target_path}</span></div>`
      ).join('');
      hint.innerHTML = '<button class="action-btn" onclick="copyApprove()">Copy approve command</button>';
    }

    setStatus('Live — last updated ' + new Date().toLocaleTimeString(), true);
  } catch (e) {
    setStatus('Error: ' + e.message, false);
  }
}

function setStatus(msg, ok) {
  document.getElementById('status-text').textContent = msg;
}

function copyApprove() {
  navigator.clipboard.writeText('genesis decide --yes "approve pending writes"');
}

setInterval(poll, POLL_MS);
poll();
</script>
</body>
</html>
"""


def _find_free_port(start: int = _DEFAULT_PORT, scan: int = _PORT_SCAN_RANGE) -> int:
    for port in range(start, start + scan):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start  # fallback — may fail, caller handles


class _CompanionHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler: serves the health page and proxies gde_session.json."""

    project_dir: pathlib.Path = pathlib.Path(".")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_html(_HEALTH_HTML)
        elif path == "/session.json":
            self._serve_session()
        else:
            self.send_error(404)

    def _serve_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_session(self) -> None:
        session_file = self.project_dir / _SESSION_FILE
        if not session_file.exists():
            self.send_error(404, "Session file not found")
            return
        try:
            body = session_file.read_bytes()
        except OSError:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # suppress access log spam
        pass


class HealthPageServer:
    """Serves the Genesis PRO health page on a local port.

    Uses only Python stdlib (``http.server``, ``threading``, ``socket``).
    Zero new dependencies.

    Usage::

        server = HealthPageServer(project_dir=Path("."))
        server.start()       # launches in background thread
        print(server.url)    # "http://127.0.0.1:7433"
        server.open_browser() # opens automatically if possible
        # …
        server.stop()
    """

    def __init__(
        self,
        project_dir: pathlib.Path | str = ".",
        port: int = _DEFAULT_PORT,
        auto_find_port: bool = True,
    ) -> None:
        self.project_dir = pathlib.Path(project_dir)
        self.port = _find_free_port(port) if auto_find_port else port
        self._server: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        """Start the health page server in a daemon background thread."""
        if self._server is not None:
            return  # already running

        handler = _make_handler(self.project_dir)
        self._server = http.server.HTTPServer(("127.0.0.1", self.port), handler)
        self._server.allow_reuse_address = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="genesis-health-page",
        )
        self._thread.start()

    def stop(self) -> None:
        """Shut down the server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    def open_browser(self) -> bool:
        """Open the health page in the default browser. Returns True on success."""
        import webbrowser
        try:
            webbrowser.open(self.url)
            return True
        except Exception:
            return False

    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()


def _make_handler(project_dir: pathlib.Path) -> type:
    """Create a handler class with project_dir bound as a class variable."""
    class Handler(_CompanionHandler):
        pass
    Handler.project_dir = project_dir  # type: ignore[attr-defined]
    return Handler


# ---------------------------------------------------------------------------
# CLI entry point — `genesis companion`
# ---------------------------------------------------------------------------


def main(project_dir: pathlib.Path | str = ".") -> None:
    """Start the health page server and print the URL.

    Intended for use as ``genesis companion`` CLI command.
    Blocks until Ctrl-C.
    """
    project_dir = pathlib.Path(project_dir)
    server = HealthPageServer(project_dir=project_dir)
    server.start()
    print(f"Genesis PRO health page: {server.url}")
    print("Press Ctrl-C to stop.\n")

    # Gate miss-rate report on startup
    stats = CompanionInstrumentation(project_dir).analyse()
    if stats.total_gates_presented > 0:
        print(
            f"Gate miss-rate: {stats.miss_rate:.0%} "
            f"({stats.missed_gates}/{stats.total_gates_presented} gates "
            f"unanswered >{stats.threshold_seconds//60} min)"
        )
        if stats.companion_justified:
            print("→ Miss rate >15%. Companion overlay is justified by usage data.")
        else:
            print("→ Miss rate ≤15%. CLI + notifications are sufficient for now.")
    else:
        print("No gate data yet — run a session first.")

    server.open_browser()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("\nHealth page stopped.")
