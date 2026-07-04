"""Genesis Companion streaming — WebSocket server.

Runs on localhost:47291 (genesis-companion reserved port).
Accepts one connection at a time from the Companion UI (Tauri WebView).
Drains the StreamEmitter queue and broadcasts to the connected client.
Handles inbound messages (user.intent, user.approval, user.voice_*).

Security:
  - Loopback only (127.0.0.1) — never binds to 0.0.0.0
  - Session token handshake: client must send {"type": "auth", "token": <token>}
    as first message; wrong token closes the connection immediately
  - Token is a random 32-byte hex string generated at server start

Usage::

    from genesis_architect_pro.streaming.server import CompanionServer

    server = CompanionServer()
    token = server.token          # pass to the Tauri shell at launch
    asyncio.run(server.serve())   # blocks until stopped

Or non-blocking (in a background thread)::

    server = CompanionServer()
    server.start_in_background()
    # ...
    server.stop()
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
from typing import Callable

from genesis_architect_pro.streaming.events import (
    StreamEmitter,
    StreamMessage,
    default_emitter,
)

try:
    import websockets
    # websockets >= 14 uses ServerConnection; < 14 used WebSocketServerProtocol
    try:
        from websockets.asyncio.server import ServerConnection as _WSConn
    except ImportError:
        from websockets.server import WebSocketServerProtocol as _WSConn  # type: ignore[assignment]
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    _WSConn = object  # type: ignore[assignment,misc]

_HOST = "127.0.0.1"
_PORT = 47291
_log = logging.getLogger("genesis.streaming")


# ---------------------------------------------------------------------------
# Inbound message handler type
# ---------------------------------------------------------------------------

InboundHandler = Callable[[StreamMessage], None]


def _control_envelope(msg_type: str) -> str:
    """A minimal but schema-valid envelope for control messages (auth.ok /
    auth.fail). The client validates every frame against {id, type, ts,
    payload}; a bare {type} would be dropped."""
    import json
    import time
    import uuid

    return json.dumps({
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "ts": time.time(),
        "payload": {},
    })


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class CompanionServer:
    """WebSocket server for the Genesis PRO Companion.

    Args:
        port: Port to listen on (default 47291).
        emitter: StreamEmitter to drain (default: module-level default_emitter).
        on_message: Optional sync callback invoked for each inbound message.
    """

    def __init__(
        self,
        port: int = _PORT,
        emitter: StreamEmitter | None = None,
        on_message: InboundHandler | None = None,
    ) -> None:
        if not _WS_AVAILABLE:
            raise RuntimeError(
                "websockets library not installed. "
                "Run: pip install genesis-architect-pro[companion]"
            )
        self._port = port
        self._emitter = emitter or default_emitter
        self._on_message = on_message
        self._token = secrets.token_hex(32)
        self._stop_event: asyncio.Event | None = None
        self._server = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def token(self) -> str:
        """Auth token that the Tauri shell must present on connect."""
        return self._token

    @property
    def port(self) -> int:
        return self._port

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def serve(self) -> None:
        """Start serving. Blocks until stop() is called."""
        self._stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        self._emitter.attach(loop)

        async with websockets.serve(
            self._handle_connection,
            _HOST,
            self._port,
            ping_interval=20,
            ping_timeout=10,
        ) as server:
            self._server = server
            _log.info("Genesis Companion WebSocket listening on ws://%s:%d", _HOST, self._port)
            await self._stop_event.wait()

        self._emitter.detach()

    def start_in_background(self) -> None:
        """Start the server in a daemon thread. Returns immediately."""
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self.serve())

        self._thread = threading.Thread(target=_run, daemon=True, name="genesis-ws-server")
        self._thread.start()

    def stop(self) -> None:
        """Signal the server to shut down."""
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    # ------------------------------------------------------------------
    # Connection handler
    # ------------------------------------------------------------------

    async def _handle_connection(self, ws: "_WSConn") -> None:
        """Handle one client connection: auth → drain queue + forward inbound."""
        # Auth handshake — first message must be {"type":"auth","token":"..."}
        import json
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg = json.loads(raw)
            if msg.get("type") != "auth" or msg.get("token") != self._token:
                # Tell the client explicitly so it stops waiting, then close.
                try:
                    await ws.send(_control_envelope("auth.fail"))
                except Exception:
                    pass
                await ws.close(1008, "unauthorized")
                _log.warning("Companion: auth failed from %s", ws.remote_address)
                return
        except Exception:
            await ws.close(1008, "auth timeout or bad message")
            return

        # Acknowledge — the client waits for auth.ok before it considers itself
        # connected. Without this it holds a live socket but shows "connecting"
        # forever. The message must be a full envelope (id + ts) or the client's
        # schema validation drops it.
        try:
            await ws.send(_control_envelope("auth.ok"))
        except Exception:
            return

        _log.info("Companion: client connected %s", ws.remote_address)

        # Run outbound (queue → ws) and inbound (ws → handler) concurrently
        outbound = asyncio.create_task(self._drain_outbound(ws))
        inbound = asyncio.create_task(self._receive_inbound(ws))

        done, pending = await asyncio.wait(
            [outbound, inbound],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        _log.info("Companion: client disconnected %s", ws.remote_address)

    async def _drain_outbound(self, ws: "_WSConn") -> None:
        """Drain the emitter queue and send each message to the client.

        When the queue is idle we simply loop again — the send() on the next
        message (or the concurrent inbound task) surfaces a real disconnect.
        We must NOT poke a version-specific 'closed' attribute here: newer
        `websockets` renamed it, and touching it raised AttributeError, killing
        this task ~1s after every connect and closing the socket. That was the
        green↔yellow flapping.
        """
        queue = self._emitter.queue
        if queue is None:
            return
        while True:
            try:
                msg: StreamMessage = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # idle — keep waiting; do not touch the socket
            try:
                await ws.send(msg.to_json())
            except Exception:
                break  # real send failure → connection is gone

    async def _receive_inbound(self, ws: "_WSConn") -> None:
        """Receive messages from the UI and dispatch to on_message handler."""
        try:
            async for raw in ws:
                try:
                    msg = StreamMessage.from_json(raw)
                    _log.debug("Companion inbound: %s", msg.type)
                    if self._on_message:
                        # Run sync handler in thread pool to avoid blocking the loop
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, self._on_message, msg)
                except Exception as exc:
                    _log.warning("Companion: bad inbound message: %s", exc)
        except Exception:
            pass  # connection closed


# ---------------------------------------------------------------------------
# Convenience: broadcast a message to whatever client is connected
# ---------------------------------------------------------------------------

def emit(message: StreamMessage) -> None:
    """Emit a message via the module-level default emitter."""
    default_emitter.emit(message)
