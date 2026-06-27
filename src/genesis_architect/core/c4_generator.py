#!/usr/bin/env python3
"""
c4_generator.py - Genesis Architect (free core)

Generates C4 architecture documentation (Mermaid diagrams) from:
  - .genesis/evidence.json  (archetype, language, components)
  - .genesis/import_graph.json (module dependencies)

Produces: docs/architecture/C4_ARCHITECTURE.md
  - Level 1: Context diagram (System + external actors)   [FREE]
  - Level 2: Container diagram (top-level directories)     [FREE]
  - Level 3: Component diagram (modules + relationships)   [PRO]

Free core ships Levels 1-2. Pro EXTENDS this by injecting the Level 3 component
diagram via the `component_section` argument to generate_c4_doc.

All diagrams use Mermaid syntax (GitHub renders natively).
No external tools required.

Usage:
  python scripts/c4_generator.py [project_path]
  python scripts/c4_generator.py [project_path] --output docs/architecture/C4_ARCHITECTURE.md
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_id(s: str) -> str:
    """Make a Mermaid-safe node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", s).strip("_") or "node"


def _load_evidence(project_path: Path) -> dict:
    ev_path = project_path / ".genesis" / "evidence.json"
    if ev_path.exists():
        try:
            return json.loads(ev_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_graph(project_path: Path) -> dict:
    g_path = project_path / ".genesis" / "import_graph.json"
    if g_path.exists():
        try:
            return json.loads(g_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _project_name(project_path: Path, evidence: dict) -> str:
    name = evidence.get("exec_summary", "")
    if name:
        # First line
        name = name.splitlines()[0].strip().rstrip(".")
        if len(name) < 60:
            return name
    # Fallback: directory name
    return project_path.name.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Level 1: Context Diagram
# ---------------------------------------------------------------------------

EXTERNAL_SIGNALS = {
    "database": ["postgres", "mysql", "sqlite", "mongodb", "redis", "supabase", "neon"],
    "auth": ["oauth", "jwt", "auth0", "clerk", "supabase auth"],
    "storage": ["s3", "gcs", "azure blob", "cloudinary", "minio"],
    "email": ["sendgrid", "ses", "mailgun", "resend", "smtp"],
    "ai": ["openai", "anthropic", "groq", "gemini", "ollama", "claude"],
    "queue": ["rabbitmq", "kafka", "sqs", "celery", "redis queue"],
    "payments": ["stripe", "paypal", "braintree"],
    "monitoring": ["sentry", "datadog", "prometheus", "grafana", "newrelic"],
}


def _detect_external_systems(evidence: dict, graph: dict) -> list[tuple[str, str]]:
    """Detect external systems referenced in evidence or imports."""
    found: list[tuple[str, str]] = []
    text = (evidence.get("arch_rationale", "") + " " + evidence.get("exec_summary", "")).lower()
    all_imports = set()
    for mod_data in graph.get("modules", {}).values():
        all_imports.update(mod_data.get("imports", []))
    import_text = " ".join(all_imports).lower()
    combined = text + " " + import_text

    for system_type, keywords in EXTERNAL_SIGNALS.items():
        for kw in keywords:
            if kw in combined:
                found.append((system_type, kw))
                break  # one per type

    return found


def _generate_context_diagram(project_name: str, archetype: str,
                               external: list[tuple[str, str]]) -> str:
    lines = [
        "```mermaid",
        "C4Context",
        f'  title System Context: {project_name}',
        "",
        '  Person(user, "User", "Primary user of the system")',
        f'  System(sys, "{project_name}", "{archetype.title()} system")',
    ]

    for i, (sys_type, kw) in enumerate(external):
        nid = _sanitise_id(f"ext_{sys_type}")
        lines.append(f'  System_Ext({nid}, "{kw.title()}", "External {sys_type}")')

    lines.append("")
    lines.append('  Rel(user, sys, "Uses")')
    for sys_type, kw in external:
        nid = _sanitise_id(f"ext_{sys_type}")
        lines.append(f'  Rel(sys, {nid}, "Uses")')

    lines += ["```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Level 2: Container Diagram
# ---------------------------------------------------------------------------

def _detect_containers(project_path: Path, graph: dict) -> list[dict]:
    """Map top-level directories to C4 containers."""
    containers = []
    seen = set()

    # From import graph modules
    for mod in graph.get("modules", {}):
        parts = mod.replace("\\", "/").split("/")
        if len(parts) >= 2:
            top = parts[0]
            if top not in seen and top not in (".", ""):
                seen.add(top)
                containers.append({
                    "id": _sanitise_id(top),
                    "name": top,
                    "description": _infer_container_desc(top),
                })

    # Also check actual directories
    if project_path.exists():
        for d in project_path.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name not in ("node_modules", "venv", ".venv", "__pycache__"):
                if d.name not in seen:
                    seen.add(d.name)
                    containers.append({
                        "id": _sanitise_id(d.name),
                        "name": d.name,
                        "description": _infer_container_desc(d.name),
                    })

    return containers[:12]  # cap output


def _infer_container_desc(name: str) -> str:
    n = name.lower()
    descs = {
        "src": "Application source code",
        "tests": "Test suite",
        "docs": "Documentation",
        "scripts": "Utility scripts",
        "config": "Configuration files",
        "migrations": "Database migrations",
        "api": "API layer",
        "domain": "Domain/business logic",
        "infra": "Infrastructure adapters",
        "infrastructure": "Infrastructure adapters",
        "frontend": "Frontend application",
        "backend": "Backend application",
        "workers": "Background workers",
        "jobs": "Scheduled jobs",
    }
    for k, v in descs.items():
        if k in n:
            return v
    return f"{name.title()} layer"


def _generate_container_diagram(project_name: str, containers: list[dict],
                                 archetype: str) -> str:
    lines = [
        "```mermaid",
        "C4Container",
        f'  title Container Diagram: {project_name}',
        "",
        '  Person(user, "User", "Uses the system")',
        "",
    ]
    for c in containers:
        lines.append(f'  Container({c["id"]}, "{c["name"]}", "{c["description"]}")')

    lines.append("")
    lines.append('  Rel(user, src, "Uses")')
    # Link obvious pairs
    pairs = [("api", "domain"), ("api", "src"), ("frontend", "api"), ("src", "infra")]
    existing_ids = {c["id"] for c in containers}
    for src, dst in pairs:
        if src in existing_ids and dst in existing_ids:
            lines.append(f'  Rel({src}, {dst}, "Calls")')

    lines += ["```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Level 3: Component Diagram
# ---------------------------------------------------------------------------

# Level 3 (component diagram) lives in Pro. Free injects it via the
# `component_section` argument to generate_c4_doc.


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_c4_doc(project_path: str | Path,
                    output_path: str | Path | None = None,
                    component_section: str | None = None) -> str:
    """
    Generate C4_ARCHITECTURE.md content (Levels 1-2).
    Returns the content string and optionally writes to output_path.

    Free core emits Level 1 (Context) and Level 2 (Containers). Pro passes a
    rendered Level 3 (Components) diagram via `component_section`, which is
    appended when provided.
    """
    root = Path(project_path).resolve()
    evidence = _load_evidence(root)
    graph = _load_graph(root)

    archetype = evidence.get("archetype", "service")
    language = evidence.get("language", graph.get("language", "unknown"))
    project_name = _project_name(root, evidence)
    external = _detect_external_systems(evidence, graph)
    containers = _detect_containers(root, graph)

    sections = [
        "# C4 Architecture",
        "<!-- Generated by Genesis Architect c4_generator.py -->",
        f"<!-- Project: {project_name} | Language: {language} | Archetype: {archetype} -->",
        "",
        "## Level 1: System Context",
        "",
        "> Who uses the system and what external systems does it depend on?",
        "",
        _generate_context_diagram(project_name, archetype, external),
        "## Level 2: Containers",
        "",
        "> What major buildable/deployable units make up the system?",
        "",
        _generate_container_diagram(project_name, containers, archetype),
    ]

    if component_section:
        sections += [
            "## Level 3: Components",
            "",
            "> What are the main source modules and how do they relate?",
            "> Showing top modules by connectivity. Arrows = import relationships.",
            "",
            component_section,
        ]

    sections += [
        "---",
        "",
        "_Generated by Genesis Architect. Refresh with: `genesis audit .`_",
        "_Diagrams use [Mermaid C4 syntax](https://mermaid.js.org/syntax/c4.html) - rendered natively on GitHub._",
    ]

    content = "\n".join(sections)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    return content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - C4 Architecture Generator"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: docs/architecture/C4_ARCHITECTURE.md)",
    )
    args = parser.parse_args()

    root = Path(args.project_path).resolve()
    out = args.output or str(root / "docs" / "architecture" / "C4_ARCHITECTURE.md")

    content = generate_c4_doc(root, output_path=out)
    print(f"C4 architecture document written to: {out}")


if __name__ == "__main__":
    main()
