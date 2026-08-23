"""Companion backend startup — the sequence `--serve` and `--ui` both perform.

Both commands brought the full backend up the same way: the same seven
imports, then the same seven steps in the same order. Two copies of a startup
sequence is a live bug risk on its own, because a fix applied to one can miss
the other, and it was also what pushed the companion module past its fan-out
ceiling.

Only the *startup* is shared here. The two commands tear down differently and
that difference is preserved rather than unified:

    --serve   uninstalls both patches, stops the IDE bridge, stops the server
    --ui      stops the wake listener and the server, and does neither of the
              other two

That asymmetry is in the original code. It may well be a defect — `--ui`
leaves `runner_patch` and `gate_notifier_patch` installed on exit — but
deciding that is a behaviour change, and this module exists to move code, not
to alter it. `stop_backend()` implements the `--serve` teardown exactly and is
used only by `--serve`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CompanionBackend:
    """The live pieces of a started backend.

    Deliberately untyped (`Any`) rather than importing the real classes for
    annotations: every one of them lives behind an optional extra, and
    importing them at module scope would undo the deferred-import discipline
    that keeps `genesis companion --stats` working on an install with no
    websockets.
    """

    server: Any
    ide_bridge: Any
    router: Any
    token: str
    port: int


def start_backend(project_dir: Path) -> CompanionBackend:
    """Bring up the WebSocket server, IDE bridge, gate notifier and router.

    Raises whatever the underlying subsystems raise — most often ImportError
    when the `streaming` extra is absent. The caller decides what that means:
    `--serve` treats it as fatal, `--ui` catches it and degrades to an offline
    UI.
    """
    from genesis_architect.pro import gate_notifier_patch
    from genesis_architect.pro.gde_companion import GateNotifier
    from genesis_architect.pro.ide_bridge.server import IDEBridgeServer
    from genesis_architect.pro.streaming import runner_patch
    from genesis_architect.pro.streaming.events import default_emitter
    from genesis_architect.pro.streaming.inbound import InboundRouter
    from genesis_architect.pro.streaming.server import CompanionServer

    # 1. Start WebSocket server
    ws_server = CompanionServer(emitter=default_emitter)
    ws_server.start_in_background()

    # 2. Install GDE runner streaming patch
    runner_patch.install()

    # 3. Start IDE Bridge
    ide_bridge = IDEBridgeServer()
    ide_bridge.start()

    # 4. Wire GateNotifier
    notifier = GateNotifier(project_name=project_dir.name or "Genesis")
    gate_notifier_patch.install(notifier)

    # 5. Build InboundRouter, wire IDE bridge, register as on_message callback
    router = InboundRouter(
        project_dir=project_dir,
        emitter=default_emitter,
        ide_bridge=ide_bridge,
    )

    # Patch the server's on_message after construction (server.py stores it at
    # init time). We reassign the internal attribute directly since
    # CompanionServer exposes no setter.
    ws_server._on_message = router.handle  # type: ignore[attr-defined]

    return CompanionBackend(
        server=ws_server,
        ide_bridge=ide_bridge,
        router=router,
        token=ws_server.token,
        port=ws_server.port,
    )


def stop_backend(backend: CompanionBackend) -> None:
    """Tear down in reverse order — the `--serve` shutdown, exactly.

    Not used by `--ui`, which has its own narrower shutdown. See the module
    docstring.
    """
    from genesis_architect.pro import gate_notifier_patch
    from genesis_architect.pro.streaming import runner_patch

    runner_patch.uninstall()
    gate_notifier_patch.uninstall()
    backend.ide_bridge.stop()
    backend.server.stop()
