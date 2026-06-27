#!/usr/bin/env python3
"""
c4_generator.py - Genesis Architect PRO (advanced extension)

Levels 1-2 (Context, Containers) live in the FREE core
(genesis_architect.core.c4_generator). Pro EXTENDS them - it does not duplicate
them - by adding Level 3 (Components): a connectivity-ranked component diagram.

Pro's generate_c4_doc renders the Level 3 section and passes it to the free-core
generator via its `component_section` hook. All Level 1-2 logic and helpers are
re-used from free core - zero duplication.
"""

from pathlib import Path

from genesis_architect.core import c4_generator as _base
from genesis_architect.core.c4_generator import (  # noqa: F401
    _sanitise_id,
    _load_graph,
    _load_evidence,
    _project_name,
    _generate_context_diagram,
    _generate_container_diagram,
)


# ---------------------------------------------------------------------------
# PRO: Level 3 component diagram
# ---------------------------------------------------------------------------

def _generate_component_diagram(project_name: str, graph: dict,
                                  max_nodes: int = 20) -> str:
    modules = graph.get("modules", {})
    if not modules:
        return "_No source modules found for component diagram._\n"

    # Pick most connected modules (highest fan_in + fan_out)
    scored = sorted(
        modules.items(),
        key=lambda x: x[1].get("fan_in", 0) + x[1].get("fan_out", 0),
        reverse=True,
    )
    selected = scored[:max_nodes]
    selected_keys = {k for k, _ in selected}

    lines = [
        "```mermaid",
        "C4Component",
        f'  title Component Diagram: {project_name} (top {len(selected)} modules)',
        "",
    ]

    for mod, data in selected:
        nid = _sanitise_id(mod.replace("/", "_").replace(".", "_"))
        label = Path(mod).name
        layer = data.get("layer", "unknown")
        lines.append(f'  Component({nid}, "{label}", "{layer}")')

    lines.append("")
    # Edges (only between selected nodes)
    for mod, data in selected:
        src_id = _sanitise_id(mod.replace("/", "_").replace(".", "_"))
        for imp in data.get("imports", []):
            if imp in selected_keys:
                dst_id = _sanitise_id(imp.replace("/", "_").replace(".", "_"))
                lines.append(f'  Rel({src_id}, {dst_id}, "imports")')

    lines += ["```", ""]
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# PRO: generate_c4_doc - delegate to free core, injecting Level 3
# ---------------------------------------------------------------------------

def generate_c4_doc(project_path, output_path=None):
    """Pro C4 doc: free Levels 1-2 + injected Level 3 (Components)."""
    root = Path(project_path).resolve()
    graph = _load_graph(root)
    evidence = _load_evidence(root)
    project_name = _project_name(root, evidence)
    component_section = _generate_component_diagram(project_name, graph)
    return _base.generate_c4_doc(
        root, output_path=output_path, component_section=component_section,
    )
