#!/usr/bin/env python3
"""
refactoring_planner.py - Genesis Architect PRO

Generates an executable refactoring plan from anti-pattern and fragility data.

Five refactoring rules:
  1. hub-splitter          - split high fan_in hub files
  2. god-class-splitter    - split high fan_out god classes
  3. cycle-breaker         - break circular dependency cycles
  4. dead-code-removal     - delete orphan modules
  5. layer-violation-fix   - move misplaced modules to correct layer

The cycle breaker picks the edge to cut from graph metrics: the cycle member
with the lowest instability (fan_out / (fan_in + fan_out)) should not depend
on its cycle neighbour, so that import is inverted through an interface
extracted into the cycle's shared directory. Without graph metrics it falls
back to a generic shared-types suggestion.

Each step includes:
  - tier (1=critical, 2=important)
  - operations: list of {type, path, description}
  - estimated complexity: LOW | MEDIUM | HIGH
  - score_impact: expected score improvement
  - why: root cause from anti-pattern data

Usage:
  python scripts/refactoring_planner.py [project_path]
  python scripts/refactoring_planner.py [project_path] --json
"""

import argparse
import json
import posixpath
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath

from genesis_architect_pro.antipattern_detector import detect_all, AntiPattern


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RefactorOperation:
    type: str           # CREATE | MODIFY | DELETE | MOVE
    path: str
    description: str


@dataclass
class RefactorStep:
    id: int
    tier: int           # 1 = critical, 2 = important
    rule: str
    priority: str       # CRITICAL | HIGH | MEDIUM
    title: str
    why: str
    operations: list[RefactorOperation] = field(default_factory=list)
    complexity: str = "MEDIUM"    # LOW | MEDIUM | HIGH
    score_impact: int = 0         # estimated score points gained
    # Step 2: confidence annotations (additive, backward-compatible)
    confidence: float = 0.8      # 0.0–1.0 certainty that this step is needed
    confidence_basis: str = ""   # short explanation of confidence level

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class CycleCut:
    """
    The import to invert to break one cycle.

    source stops importing target and depends on interface_name instead;
    target satisfies the interface.
    """
    source: str
    target: str
    interface_name: str
    interface_path: str
    instability: float   # source's fan_out / (fan_in + fan_out)
    fan_in: int
    fan_out: int


@dataclass
class RefactoringPlan:
    steps: list[RefactorStep] = field(default_factory=list)
    tier1_count: int = 0
    tier2_count: int = 0
    total_score_impact: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "tier1_count": self.tier1_count,
            "tier2_count": self.tier2_count,
            "total_score_impact": self.total_score_impact,
            "generated_at": self.generated_at,
        }


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

def _step_confidence(priority: str, anti_pattern: AntiPattern | None = None) -> tuple[float, str]:
    """
    Return (confidence, basis) for a refactoring step.

    If the triggering anti-pattern carries its own confidence, inherit it
    as a floor and boost slightly (step confidence <= detection confidence).
    Otherwise derive from priority tier.
    """
    base_map = {"CRITICAL": 0.95, "HIGH": 0.85, "MEDIUM": 0.75, "LOW": 0.60}
    base = base_map.get(priority, 0.75)

    if anti_pattern is not None:
        ap_conf = getattr(anti_pattern, "confidence", base)
        ap_basis = getattr(anti_pattern, "basis", "")
        # Cap step confidence at the detection confidence
        conf = round(min(base, ap_conf), 2)
        basis = f"derived from {priority} anti-pattern detection (ap_confidence={ap_conf})"
        if ap_basis:
            basis += f"; {ap_basis}"
    else:
        conf = base
        basis = f"rule-based estimate for {priority} priority step"

    return conf, basis


# ---------------------------------------------------------------------------
# Rule generators
# ---------------------------------------------------------------------------

def _rule_hub_splitter(patterns: list[AntiPattern], step_id_start: int) -> list[RefactorStep]:
    steps = []
    hubs = [p for p in patterns if p.type == "hub-file"]
    for i, p in enumerate(hubs[:5]):  # cap at 5
        fi = p.metrics.get("fan_in", 0)
        dependents = p.affected_modules[:5]
        priority = "CRITICAL" if fi > 20 else "HIGH"
        conf, basis = _step_confidence(priority, p)
        step = RefactorStep(
            id=step_id_start + i,
            tier=1,
            rule="hub-splitter",
            priority=priority,
            title=f"Split hub file: {p.file}",
            why=p.description,
            operations=[
                RefactorOperation(
                    type="CREATE",
                    path=_suggest_split_path(p.file, "interface"),
                    description=f"Extract stable public interface from {p.file}",
                ),
                RefactorOperation(
                    type="MODIFY",
                    path=p.file,
                    description=f"Keep only implementation in {p.file}, import interface from new module",
                ),
                RefactorOperation(
                    type="MODIFY",
                    path="[all importers]",
                    description=(
                        f"Update {len(dependents)}+ importers to import from "
                        f"the new interface module instead of {p.file}"
                    ),
                ),
            ],
            complexity="HIGH",
            score_impact=min(12, fi // 2),
            confidence=conf,
            confidence_basis=basis,
        )
        steps.append(step)
    return steps


def _rule_god_class_splitter(patterns: list[AntiPattern], step_id_start: int) -> list[RefactorStep]:
    steps = []
    gods = [p for p in patterns if p.type == "god-class"]
    for i, p in enumerate(gods[:5]):
        fo = p.metrics.get("fan_out", 0)
        priority = "CRITICAL" if fo > 30 else "HIGH"
        conf, basis = _step_confidence(priority, p)
        step = RefactorStep(
            id=step_id_start + i,
            tier=1,
            rule="god-class-splitter",
            priority=priority,
            title=f"Split god class: {p.file}",
            why=p.description,
            operations=[
                RefactorOperation(
                    type="CREATE",
                    path=_suggest_split_path(p.file, "core"),
                    description=f"Extract core logic from {p.file} into focused module",
                ),
                RefactorOperation(
                    type="CREATE",
                    path=_suggest_split_path(p.file, "utils"),
                    description=f"Extract utility functions from {p.file}",
                ),
                RefactorOperation(
                    type="MODIFY",
                    path=p.file,
                    description=f"Reduce {p.file} to thin coordinator, delegating to new modules",
                ),
            ],
            complexity="HIGH",
            score_impact=min(15, fo // 2),
            confidence=conf,
            confidence_basis=basis,
        )
        steps.append(step)
    return steps


def _rule_cycle_breaker(patterns: list[AntiPattern], step_id_start: int,
                        modules: dict | None = None) -> list[RefactorStep]:
    """
    One step per import cycle (at most 5).

    With graph metrics for every cycle member (*modules*, the import graph's
    "modules" mapping) the step inverts one chosen import through an
    extracted interface; see choose_cycle_cut. Otherwise it falls back to a
    generic shared-types suggestion and says so in confidence_basis.
    """
    steps = []
    cycles = [p for p in patterns if p.type == "circular-dep"]
    for i, p in enumerate(cycles[:5]):
        cycle = p.metrics.get("cycle", [])
        conf, basis = _step_confidence("CRITICAL", p)
        cut = choose_cycle_cut(cycle, modules or {})
        if cut is not None:
            steps.append(RefactorStep(
                id=step_id_start + i,
                tier=1,
                rule="cycle-breaker",
                priority="CRITICAL",
                title=(
                    f"Break import cycle ({len(p.affected_modules)} modules): "
                    f"cut {cut.source} -> {cut.target}"
                ),
                why=(
                    f"{p.description} Cut {cut.source} -> {cut.target}: {cut.source} is the "
                    f"most stable member of the cycle (instability {cut.instability:.2f}, "
                    f"fan_in {cut.fan_in}, fan_out {cut.fan_out}), so it should depend on an "
                    f"abstraction instead of on {cut.target}."
                ),
                operations=_interface_extraction_ops(cut),
                complexity="MEDIUM",
                score_impact=8,
                confidence=conf,
                confidence_basis=(
                    f"{basis}; cut chosen by lowest instability from import-graph metrics"
                ),
            ))
            continue
        basis += "; no import-graph metrics for the cycle members, generic shared-module suggestion"
        step = RefactorStep(
            id=step_id_start + i,
            tier=1,
            rule="cycle-breaker",
            priority="CRITICAL",
            title=f"Break import cycle ({len(p.affected_modules)} modules)",
            why=p.description,
            operations=[
                RefactorOperation(
                    type="CREATE",
                    path=_suggest_shared_types_path(cycle),
                    description=(
                        "Extract shared types/interfaces into new module. "
                        "None of the cycle participants should import each other."
                    ),
                ),
                RefactorOperation(
                    type="MODIFY",
                    path=cycle[0] if cycle else p.file,
                    description=f"Update {cycle[0] if cycle else p.file} to import from shared module",
                ),
                RefactorOperation(
                    type="MODIFY",
                    path=cycle[1] if len(cycle) > 1 else "[second module]",
                    description=f"Update {cycle[1] if len(cycle) > 1 else 'second module'} to import from shared module",
                ),
            ],
            complexity="MEDIUM",
            score_impact=8,
            confidence=conf,
            confidence_basis=basis,
        )
        steps.append(step)
    return steps


def _rule_dead_code_removal(patterns: list[AntiPattern], step_id_start: int) -> list[RefactorStep]:
    steps = []
    dead = [p for p in patterns if p.type == "dead-code" and p.metrics.get("lines", 0) > 20]
    if dead:
        # Use the least-confident dead-code detection as the floor for the step
        min_conf = min((getattr(p, "confidence", 0.80) for p in dead), default=0.80)
        conf = round(min(0.75, min_conf), 2)
        basis = f"dead-code rule, MEDIUM priority; {len(dead)} orphan module(s) detected"
        step = RefactorStep(
            id=step_id_start,
            tier=2,
            rule="dead-code-removal",
            priority="MEDIUM",
            title=f"Remove {len(dead)} orphan module(s)",
            why=f"{len(dead)} modules have fan_in=0 and are not entry points. Likely dead code.",
            operations=[
                RefactorOperation(
                    type="DELETE",
                    path=p.file,
                    description=f"Delete {p.file} ({p.metrics.get('lines', 0)} lines, no importers)",
                )
                for p in dead[:10]
            ],
            complexity="LOW",
            score_impact=3,
            confidence=conf,
            confidence_basis=basis,
        )
        steps.append(step)
    return steps


def _rule_layer_violation_fix(patterns: list[AntiPattern], step_id_start: int) -> list[RefactorStep]:
    steps = []
    violations = [p for p in patterns if p.type == "leaky-abstraction"]
    if violations:
        conf, basis = _step_confidence("HIGH")
        basis = f"layer-violation rule, HIGH priority; {len(violations)} violation(s) detected"
        step = RefactorStep(
            id=step_id_start,
            tier=2,
            rule="layer-violation-fix",
            priority="HIGH",
            title=f"Fix {len(violations)} layer violation(s)",
            why=(
                f"{len(violations)} cross-layer import violations detected. "
                "Lower layers should not depend on higher layers."
            ),
            operations=[
                RefactorOperation(
                    type="MOVE",
                    path=p.affected_modules[0] if p.affected_modules else p.file,
                    description=(
                        f"Move {p.affected_modules[0] if p.affected_modules else 'module'} "
                        f"to correct layer, or introduce interface. "
                        f"Violation: {p.description[:80]}"
                    ),
                )
                for p in violations[:8]
            ],
            complexity="MEDIUM",
            score_impact=6,
            confidence=conf,
            confidence_basis=basis,
        )
        steps.append(step)
    return steps


# ---------------------------------------------------------------------------
# Cycle cut selection
# ---------------------------------------------------------------------------

_NON_WORD = re.compile(r"[^0-9A-Za-z]+")
# Stems that name a package rather than a module; the directory name is used instead.
_PACKAGE_STEMS = {"__init__", "index", "mod"}


def _cycle_nodes(cycle: list[str]) -> list[str]:
    """Cycle members in import order, without the repeated closing member."""
    nodes = [str(n) for n in cycle]
    if len(nodes) > 1 and nodes[0] == nodes[-1]:
        nodes = nodes[:-1]
    return nodes


def _module_entry(modules: dict, node: str) -> dict | None:
    entry = modules.get(node)
    if entry is None:
        entry = modules.get(node.replace("\\", "/"))
    return entry if isinstance(entry, dict) else None


def _fan(entry: dict, key: str) -> int | None:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _module_stem(module_path: str) -> str:
    p = PurePosixPath(module_path.replace("\\", "/"))
    if p.stem in _PACKAGE_STEMS and p.parent.name:
        return p.parent.name
    return p.stem


def _interface_name(module_path: str) -> str:
    """I + the PascalCase module stem: src/auth_service.py -> IAuthService."""
    words = [w for w in _NON_WORD.split(_module_stem(module_path)) if w]
    pascal = "".join(w[0].upper() + w[1:] for w in words)
    return f"I{pascal or 'Module'}"


def _interface_path(nodes: list[str], target: str) -> str:
    """<deepest directory shared by the cycle members>/<target stem>_interface<ext>."""
    dirs = [posixpath.dirname(n.replace("\\", "/")) for n in nodes]
    try:
        shared = posixpath.commonpath(dirs)
    except ValueError:  # absolute and relative paths mixed
        shared = posixpath.dirname(target.replace("\\", "/"))
    name = f"{_module_stem(target)}_interface{PurePosixPath(target).suffix}"
    return f"{shared}/{name}" if shared else name


def choose_cycle_cut(cycle: list[str], modules: dict) -> CycleCut | None:
    """
    Pick the import to invert to break *cycle*.

    *cycle* is in import order: each member imports the next, and the last
    imports the first (a closing repeat of the first member is allowed).
    *modules* is the import graph's "modules" mapping, read for fan_in,
    fan_out and imports.

    The source is the member with the lowest instability
    I = fan_out / (fan_in + fan_out): the most depended-upon, least dependent
    member, which by the Stable Dependencies Principle should not depend on
    a less stable neighbour. Ties go to lower fan_out, then higher fan_in,
    then path. The cut is the source's import of its successor.

    Returns None when fewer than two distinct members remain or any member
    lacks usable fan_in/fan_out, so the caller falls back instead of guessing.
    """
    nodes = _cycle_nodes(cycle)
    if len(nodes) < 2 or len(set(nodes)) != len(nodes):
        return None
    ranked = []
    for idx, node in enumerate(nodes):
        entry = _module_entry(modules, node)
        if entry is None:
            return None
        fan_in, fan_out = _fan(entry, "fan_in"), _fan(entry, "fan_out")
        if fan_in is None or fan_out is None:
            return None
        total = fan_in + fan_out
        instability = fan_out / total if total else 0.0
        ranked.append((instability, fan_out, -fan_in, node, idx))
    instability, fan_out, neg_fan_in, source, idx = min(ranked)

    target = nodes[(idx + 1) % len(nodes)]
    imports = (_module_entry(modules, source) or {}).get("imports")
    if isinstance(imports, list) and target not in imports and nodes[idx - 1] in imports:
        target = nodes[idx - 1]  # cycle was listed against import order

    return CycleCut(
        source=source,
        target=target,
        interface_name=_interface_name(target),
        interface_path=_interface_path(nodes, target),
        instability=round(instability, 2),
        fan_in=-neg_fan_in,
        fan_out=fan_out,
    )


def _contract_kind(path: str) -> tuple[str, bool]:
    """(what the interface is, whether implementations satisfy it structurally)."""
    ext = PurePosixPath(path).suffix.lower()
    if ext in (".py", ".pyi"):
        return "typing.Protocol", True
    if ext in (".ts", ".tsx", ".mts", ".cts"):
        return "TypeScript interface", True
    if ext in (".js", ".jsx", ".mjs", ".cjs"):
        return "JSDoc @typedef contract", True
    return "abstract interface", False


def _interface_extraction_ops(cut: CycleCut) -> list[RefactorOperation]:
    kind, structural = _contract_kind(cut.target)
    if structural:
        satisfy = (
            f"Keep {cut.target} satisfying {cut.interface_name}. Typing is structural, so "
            "it needs no import; declare the interface explicitly only to have the type "
            "checker enforce it."
        )
    else:
        satisfy = f"Make {cut.target} implement {cut.interface_name} from {cut.interface_path}."
    return [
        RefactorOperation(
            type="CREATE",
            path=cut.interface_path,
            description=(
                f"Define {cut.interface_name} as a {kind} declaring only the members of "
                f"{cut.target} that {cut.source} uses. It must not import any cycle member."
            ),
        ),
        RefactorOperation(
            type="MODIFY",
            path=cut.source,
            description=(
                f"Replace the import of {cut.target} with {cut.interface_name} and receive "
                "the implementation as a constructor or function parameter. This removes "
                f"the {cut.source} -> {cut.target} edge."
            ),
        ),
        RefactorOperation(type="MODIFY", path=cut.target, description=satisfy),
        RefactorOperation(
            type="MODIFY",
            path="[composition root]",
            description=(
                f"Pass the {cut.target} implementation into {cut.source} where the two are "
                "wired together (the entry point or factory that creates it)."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _suggest_split_path(original: str, suffix: str) -> str:
    """Suggest a path for a split-off module."""
    p = Path(original)
    stem = p.stem
    parent = str(p.parent).replace("\\", "/")
    ext = p.suffix
    return f"{parent}/{stem}_{suffix}{ext}"


def _suggest_shared_types_path(cycle: list[str]) -> str:
    """Suggest where to put shared types extracted to break a cycle."""
    if not cycle:
        return "src/shared/types.py"
    first = Path(cycle[0])
    parent = str(first.parent).replace("\\", "/")
    return f"{parent}/shared_types{first.suffix}"


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def _graph_modules(root: Path, language: str | None) -> dict:
    """
    The import graph's per-module metrics, or {} when the graph cannot be read.

    detect_all has just built (and cached) the same graph, so this is normally
    a cache read. On failure the cycle breaker falls back to its generic
    suggestion and records that in the step's confidence_basis.
    """
    try:
        from genesis_architect_pro.import_graph import load_or_build
        graph = load_or_build(root, language=language)
    except Exception:  # noqa: BLE001 - the plan degrades, it does not fail
        return {}
    modules = graph.get("modules") if isinstance(graph, dict) else None
    return modules if isinstance(modules, dict) else {}


def generate_plan(project_path: str | Path, language: str | None = None,
                  rebuild_graph: bool = False) -> RefactoringPlan:
    """Generate a complete refactoring plan for a project."""
    from datetime import UTC, datetime

    root = Path(project_path).resolve()

    ap_report = detect_all(root, language=language, rebuild_graph=rebuild_graph)
    patterns = ap_report.patterns

    all_steps: list[RefactorStep] = []
    step_id = 1

    # Tier 1: blocking / critical
    hub_steps = _rule_hub_splitter(patterns, step_id)
    all_steps.extend(hub_steps)
    step_id += len(hub_steps)

    god_steps = _rule_god_class_splitter(patterns, step_id)
    all_steps.extend(god_steps)
    step_id += len(god_steps)

    cycle_steps = _rule_cycle_breaker(patterns, step_id, _graph_modules(root, language))
    all_steps.extend(cycle_steps)
    step_id += len(cycle_steps)

    # Tier 2: important
    dead_steps = _rule_dead_code_removal(patterns, step_id)
    all_steps.extend(dead_steps)
    step_id += len(dead_steps)

    layer_steps = _rule_layer_violation_fix(patterns, step_id)
    all_steps.extend(layer_steps)

    # Assign sequential IDs
    for i, step in enumerate(all_steps, 1):
        step.id = i

    tier1 = sum(1 for s in all_steps if s.tier == 1)
    tier2 = sum(1 for s in all_steps if s.tier == 2)
    total_impact = sum(s.score_impact for s in all_steps)

    return RefactoringPlan(
        steps=all_steps,
        tier1_count=tier1,
        tier2_count=tier2,
        total_score_impact=total_impact,
        generated_at=datetime.now(UTC).isoformat(),
    )


def render_refactoring_plan_md(plan: RefactoringPlan) -> str:
    """Render REFACTORING_PLAN.md content without writing it to disk."""
    lines = [
        "# Refactoring Plan",
        "<!-- Generated by Genesis Architect PRO refactoring_planner.py -->",
        "",
        "## Overview",
        "",
        "| Tier | Steps | Score Impact |",
        "|------|-------|-------------|",
        f"| Tier 1 - Critical | {plan.tier1_count} | +{sum(s.score_impact for s in plan.steps if s.tier == 1)} pts |",
        f"| Tier 2 - Important | {plan.tier2_count} | +{sum(s.score_impact for s in plan.steps if s.tier == 2)} pts |",
        f"| **Total** | **{len(plan.steps)}** | **+{plan.total_score_impact} pts** |",
        "",
        "> Execute Tier 1 steps first. Each step must pass tests before moving to the next.",
        "",
    ]

    for step in plan.steps:
        tier_label = "**TIER 1 - Critical**" if step.tier == 1 else "Tier 2 - Important"
        lines += [
            f"## Step {step.id}: {step.title}",
            "",
            f"**Priority:** {step.priority}  |  **Rule:** {step.rule}  |  "
            f"{tier_label}  |  **Complexity:** {step.complexity}  |  "
            f"**Score impact:** +{step.score_impact} pts",
            "",
            f"**Why:** {step.why}",
            "",
            "**Operations:**",
            "",
        ]
        for op in step.operations:
            lines.append(f"- `{op.type}` `{op.path}`: {op.description}")
        lines.append("")

    lines += [
        "---",
        "",
        "_Generated by Genesis Architect PRO. Run `genesis recover [path]` to refresh._",
    ]

    return "\n".join(lines)


def write_refactoring_plan_md(plan: RefactoringPlan, output_path: Path) -> None:
    """Render and write REFACTORING_PLAN.md to output_path."""
    output_path.write_text(render_refactoring_plan_md(plan), encoding="utf-8")


def print_plan(plan: RefactoringPlan) -> None:
    print(f"\nRefactoring Plan  ({len(plan.steps)} steps, +{plan.total_score_impact} pts estimated)")
    print(f"  Tier 1 (critical): {plan.tier1_count}  Tier 2 (important): {plan.tier2_count}")
    for step in plan.steps[:10]:
        print(f"\n  [{step.tier}] {step.title}  ({step.priority}, +{step.score_impact} pts)")
        print(f"      {step.why[:100]}")
        for op in step.operations[:2]:
            print(f"      {op.type}: {op.path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Refactoring Planner"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--language", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-plan", default=None,
                        help="Write REFACTORING_PLAN.md to this path")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    plan = generate_plan(args.project_path, language=args.language,
                         rebuild_graph=args.rebuild)

    if args.write_plan:
        write_refactoring_plan_md(plan, Path(args.write_plan))
        print(f"Refactoring plan written to {args.write_plan}", file=sys.stderr)

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        print_plan(plan)


if __name__ == "__main__":
    main()
