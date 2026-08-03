"""Genesis Decision Engine — planner.

Converts a classified Intent into an ExecutionPlan.

Responsibilities:
- Select engines for the requested mode
- Resolve execution order (topological sort via registry)
- Group into parallel phases
- Identify gates required for the plan
- Estimate total duration
- Collect all write_operation declarations

No engine execution happens here. This is pure planning.
"""

from __future__ import annotations

from genesis_architect.pro.engine_registry import EngineRegistry, get_default_registry
from genesis_architect.pro.gde_types import (
    ExecutionPlan,
    GDEMode,
    Intent,
)

# Gates that are always evaluated regardless of mode
_UNIVERSAL_GATES = ["PLAN_WRITE", "RULES_FAIL"]

# Per-mode gate requirements (in addition to universal gates)
_MODE_GATES: dict[GDEMode, list[str]] = {
    GDEMode.RECOVERY: ["CONFIDENCE_LOW", "DRIFT_CRITICAL"],
    GDEMode.RESEARCH: ["CONFIDENCE_LOW"],
    GDEMode.REFACTOR: ["CONFIDENCE_LOW", "DRIFT_CRITICAL", "WRITE_SCOPE"],
    GDEMode.GATE: ["CONFIDENCE_LOW", "POLICY_VIOLATION"],
    GDEMode.BUILD: ["CONFIDENCE_LOW", "WRITE_SCOPE", "SECURITY_RISK"],
    GDEMode.DOCUMENT: ["CONFIDENCE_LOW"],
    GDEMode.COMMITTEE: ["CONFIDENCE_LOW", "DRIFT_CRITICAL", "WRITE_SCOPE"],
}


def build_plan(
    intent: Intent,
    registry: EngineRegistry | None = None,
) -> ExecutionPlan:
    """Build an ExecutionPlan for the given Intent.

    Args:
        intent: Classified intent (mode + confidence).
        registry: Engine registry to use. Defaults to the module-level registry.

    Returns:
        ExecutionPlan with ordered parallel phases, required gates, and
        write-operation declarations.
    """
    reg = registry if registry is not None else get_default_registry()
    mode = intent.mode

    # Get parallel execution groups for this mode (already topologically sorted)
    try:
        phases_raw = reg.parallel_groups_for_mode(mode)
    except Exception:
        phases_raw = []

    # Collect write operations declared across all engines in this plan
    all_write_ops: list[str] = []
    total_duration = 0
    for group in phases_raw:
        group_max_duration = 0
        for desc in group:
            all_write_ops.extend(desc.write_operations)
            group_max_duration = max(group_max_duration, desc.timeout_seconds)
        total_duration += group_max_duration

    # Gates: universal + mode-specific
    required_gates = list(_UNIVERSAL_GATES)
    for gate_id in _MODE_GATES.get(mode, []):
        if gate_id not in required_gates:
            required_gates.append(gate_id)

    return ExecutionPlan(
        mode=mode,
        phases=phases_raw,
        required_gate_ids=required_gates,
        estimated_duration_seconds=total_duration,
        write_operations_pending=list(dict.fromkeys(all_write_ops)),  # dedup, order-stable
    )
