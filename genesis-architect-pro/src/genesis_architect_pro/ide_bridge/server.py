"""Genesis Companion — IDE Bridge HTTP server.

Listens on localhost:47292/ide-event for cursor events from the
VS Code / JetBrains extension. Matches (file, line) against the
last known engine index and emits ide.line_event over WebSocket.

Runs in a daemon thread alongside the WebSocket server.
Never exposes file contents — paths only.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from genesis_architect_pro.streaming.events import default_emitter, ide_line_event

_HOST = "127.0.0.1"
_PORT = 47292
_log = logging.getLogger("genesis.ide_bridge")

# Pattern index type: {file_path: [(line, pattern, severity, suggestion)]}
PatternIndex = dict[str, list[tuple[int, str, str, str]]]


class IDEBridgeServer:
    """HTTP server that receives IDE cursor events and emits streaming hints.

    Args:
        pattern_index: Pre-built index from the last GDE engine run.
        session_id: Current GDE session ID (for event attribution).
        port: Port to listen on (default 47292).
    """

    def __init__(
        self,
        pattern_index: PatternIndex | None = None,
        session_id: str = "",
        port: int = _PORT,
    ) -> None:
        self._index: PatternIndex = pattern_index or {}
        self._session_id = session_id
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def update_index(self, index: PatternIndex, session_id: str = "") -> None:
        """Hot-swap the pattern index after a new GDE run."""
        self._index = index
        if session_id:
            self._session_id = session_id

    def start(self) -> None:
        """Start the IDE bridge server in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        bridge = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    event = json.loads(body)
                    bridge._handle(event)
                    self.send_response(200)
                except Exception:
                    self.send_response(400)
                finally:
                    self.end_headers()

            def log_message(self, *args):
                pass  # suppress default HTTP logging

        def _run():
            self._server = HTTPServer((_HOST, self._port), _Handler)
            self._server.serve_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="genesis-ide-bridge")
        self._thread.start()
        _log.info("Genesis IDE Bridge listening on http://%s:%d", _HOST, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    def _handle(self, event: dict) -> None:
        file_path = event.get("file", "")
        line = int(event.get("line", 0))
        if not file_path or line <= 0:
            return

        patterns = self._match(file_path, line)
        for pattern, severity, suggestion in patterns:
            default_emitter.emit(
                ide_line_event(
                    file=file_path,
                    line=line,
                    pattern=pattern,
                    severity=severity,
                    suggestion=suggestion,
                    session_id=self._session_id,
                )
            )

    def _match(self, file_path: str, line: int) -> list[tuple[str, str, str]]:
        """Return matching (pattern, severity, suggestion) tuples for this location."""
        # Exact path match first, then basename match
        hits = self._index.get(file_path) or self._index.get(Path(file_path).name, [])
        results = []
        for entry_line, pattern, severity, suggestion in hits:
            # entry_line == 0 means file-level (all lines); else exact line
            if entry_line == 0 or abs(entry_line - line) <= 5:
                results.append((pattern, severity, suggestion))
        return results[:2]  # max 2 hints per cursor event


def build_index_from_engine_results(engine_results: dict) -> PatternIndex:
    """Build a PatternIndex from GDE engine output dictionaries.

    Called after a COMMITTEE / RECOVERY GDE run to populate the IDE bridge.
    """
    index: PatternIndex = {}

    # Anti-patterns → file-level entries
    patterns_out = engine_results.get("antipattern_detector", {}).get("output", {})
    for finding in patterns_out.get("patterns", []):
        for affected_file in finding.get("affected_files", []):
            index.setdefault(affected_file, []).append((
                0,                              # file-level
                finding.get("pattern_type", "ANTI_PATTERN"),
                finding.get("severity", "MEDIUM"),
                finding.get("suggested_fix", "See anti-pattern report"),
            ))

    # Fragility map → volatile/fragile modules
    fragility_out = engine_results.get("fragility_classifier", {}).get("output", {})
    for module_path, status in fragility_out.get("fragility_map", {}).items():
        if status in ("VOLATILE", "FRAGILE"):
            severity = "CRITICAL" if status == "VOLATILE" else "HIGH"
            index.setdefault(module_path, []).append((
                0,
                status,
                severity,
                f"Module is {status} — high churn or missing tests. See fragility map.",
            ))

    return index
