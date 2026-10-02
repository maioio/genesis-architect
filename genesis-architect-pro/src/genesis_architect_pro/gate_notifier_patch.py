"""Genesis Companion — GateNotifier monkey-patch for gde_gate_engine.

Wraps evaluate_gates to call GateNotifier.notify_gate() after any
BLOCK_AND_ASK (soft_block or hard_block) outcome. Mirrors the pattern
used in streaming/runner_patch.py.

Usage::

    from genesis_architect_pro.gate_notifier_patch import install, uninstall
    from genesis_architect_pro.gde_companion import GateNotifier

    notifier = GateNotifier(project_name="my-project")
    install(notifier)     # call once at Companion startup
    uninstall()           # call at shutdown (optional)

The patch is idempotent: calling install() with the same notifier twice
has no effect. Calling it with a different notifier replaces the active one.
"""

from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger("genesis.gate_notifier_patch")

_active_notifier: Optional["GateNotifier"] = None  # type: ignore[type-arg]  # noqa: F821
_INSTALLED = False


def install(notifier: "GateNotifier") -> bool:  # noqa: F821
    """Install the GateNotifier hook into gde_gate_engine.evaluate_gates.

    Returns True if installed, False if the gate engine module is unavailable.
    Idempotent: re-calling with the same notifier is a no-op.
    """
    global _active_notifier, _INSTALLED

    if _INSTALLED and _active_notifier is notifier:
        return True

    try:
        import genesis_architect_pro.gde_gate_engine as gate_module
    except ImportError:
        _log.warning("gate_notifier_patch: gde_gate_engine not found, skipping install")
        return False

    original_evaluate = getattr(gate_module, "evaluate_gates", None)
    if original_evaluate is None:
        _log.warning("gate_notifier_patch: evaluate_gates not found in gde_gate_engine")
        return False

    # Unwrap any previous patch before re-wrapping
    if getattr(original_evaluate, "_genesis_notifier_patched", False):
        original_evaluate = original_evaluate._original  # type: ignore[attr-defined]

    def _patched_evaluate(ctx):  # type: ignore[no-untyped-def]
        report = original_evaluate(ctx)

        # Notify on blocks and hard_blocks only (not warnings — too noisy)
        for gate in report.hard_blocks + report.blocks:
            try:
                _active_notifier.notify_gate(gate.gate_id, gate.reason)
            except Exception as exc:
                _log.debug("gate_notifier_patch: notify_gate error: %s", exc)

        return report

    _patched_evaluate._genesis_notifier_patched = True  # type: ignore[attr-defined]
    _patched_evaluate._original = original_evaluate      # type: ignore[attr-defined]
    gate_module.evaluate_gates = _patched_evaluate

    _active_notifier = notifier
    _INSTALLED = True
    _log.info("gate_notifier_patch: installed (notifier=%r)", notifier.project_name)
    return True


def uninstall() -> None:
    """Restore the original evaluate_gates function."""
    global _active_notifier, _INSTALLED
    if not _INSTALLED:
        return

    try:
        import genesis_architect_pro.gde_gate_engine as gate_module
    except ImportError:
        return

    current = getattr(gate_module, "evaluate_gates", None)
    if current is not None and getattr(current, "_genesis_notifier_patched", False):
        gate_module.evaluate_gates = current._original  # type: ignore[attr-defined]

    _active_notifier = None
    _INSTALLED = False
    _log.info("gate_notifier_patch: uninstalled")


def is_installed() -> bool:
    return _INSTALLED
