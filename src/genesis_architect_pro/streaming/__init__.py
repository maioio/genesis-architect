"""Genesis Companion streaming layer.

Public API::

    from genesis_architect_pro.streaming import CompanionServer, emit, install_hooks

    # 1. Install event hooks into the GDE runner (once at startup)
    install_hooks()

    # 2. Start WebSocket server
    server = CompanionServer()
    server.start_in_background()
    token = server.token  # give to Tauri shell

    # 3. Emit events manually (optional — hooks handle engine events automatically)
    from genesis_architect_pro.streaming import events
    emit(events.session_done(session_id="...", confidence=0.82, risk_level="low", mode="recovery"))

    # 4. Stop
    server.stop()
"""

from genesis_architect_pro.streaming.events import (
    StreamEmitter,
    StreamMessage,
    MessageType,
    default_emitter,
    engine_start,
    engine_progress,
    engine_done,
    engine_failed,
    gate_fired,
    gate_approval_required,
    session_confidence,
    session_done,
    committee_advisor,
    committee_synthesis,
    diff_ready,
    ide_line_event,
)
from genesis_architect_pro.streaming.server import CompanionServer, emit
from genesis_architect_pro.streaming.runner_patch import install as install_hooks, uninstall as uninstall_hooks, is_installed

__all__ = [
    # Server
    "CompanionServer",
    "emit",
    # Hooks
    "install_hooks",
    "uninstall_hooks",
    "is_installed",
    # Emitter
    "StreamEmitter",
    "StreamMessage",
    "MessageType",
    "default_emitter",
    # Event constructors
    "engine_start",
    "engine_progress",
    "engine_done",
    "engine_failed",
    "gate_fired",
    "gate_approval_required",
    "session_confidence",
    "session_done",
    "committee_advisor",
    "committee_synthesis",
    "diff_ready",
    "ide_line_event",
]
