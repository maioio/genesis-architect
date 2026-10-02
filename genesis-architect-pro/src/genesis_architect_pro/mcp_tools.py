"""
mcp_tools.py - Genesis Architect PRO

Exposes Genesis's read-only analysis capabilities as MCP tools so agents
(Claude Code, Cursor, any MCP client) can call them. Aligns with the v2 platform
strategy: Claude Code first, core/adapter split.

Design:
- The TOOLS are plain Python functions returning JSON-able dicts. They are
  read-only wrappers over existing engines (score, anti-patterns, drift,
  recovery, gate). They work and are testable WITHOUT the MCP SDK installed.
- `build_mcp_server()` wraps them as an MCP server ONLY if the `mcp` SDK is
  present. No hard dependency (dependency-light).
- No mutation, no auto-fix, no network. Deterministic.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Tool implementations (pure, read-only, SDK-independent)
# ---------------------------------------------------------------------------

def tool_architecture_score(project_dir: str = ".") -> dict:
    """Return the 0-100 architecture score and dimension breakdown."""
    from genesis_architect_pro.architecture_scorer import score_project, score_label
    score = score_project(Path(project_dir))
    return {
        "total": score.get("total"),
        "label": score_label(score.get("total", 0)),
        "modularity": score.get("modularity"),
        "coupling": score.get("coupling"),
        "cohesion": score.get("cohesion"),
        "layering": score.get("layering"),
        "profile": score.get("profile"),
        "cycle_count": score.get("cycle_count"),
    }


def tool_anti_patterns(project_dir: str = ".") -> dict:
    """Return detected anti-patterns grouped by severity."""
    from genesis_architect_pro.antipattern_detector import detect_all
    report = detect_all(Path(project_dir))
    return {
        "critical": getattr(report, "critical_count", 0),
        "high": getattr(report, "high_count", 0),
        "medium": getattr(report, "medium_count", 0),
        "low": getattr(report, "low_count", 0),
        "patterns": [
            {"type": p.type, "severity": p.severity, "file": p.file,
             "description": p.description}
            for p in getattr(report, "patterns", [])[:50]
        ],
    }


def tool_recovery_report(project_dir: str = ".") -> dict:
    """Return the recovery report summary (risk, drift, health)."""
    from genesis_architect_pro.recovery_report import generate_report_for_project
    import dataclasses
    rep = generate_report_for_project(Path(project_dir))
    return dataclasses.asdict(rep) if dataclasses.is_dataclass(rep) else dict(vars(rep))


def tool_gate(project_dir: str = ".") -> dict:
    """Run the architecture regression gate (rules engine). Read-only."""
    from genesis_architect_pro.rules_engine import run_check
    import dataclasses
    rep = run_check(project_dir)
    return dataclasses.asdict(rep)


# Registry of tools: name -> (callable, description). The MCP server and the
# tests both read this single source of truth.
TOOLS: dict[str, dict] = {
    "genesis_architecture_score": {
        "fn": tool_architecture_score,
        "description": "Architecture quality score (0-100) with dimension breakdown.",
    },
    "genesis_anti_patterns": {
        "fn": tool_anti_patterns,
        "description": "Structural anti-patterns grouped by severity.",
    },
    "genesis_recovery_report": {
        "fn": tool_recovery_report,
        "description": "Recovery report: project risk, drift, architecture health.",
    },
    "genesis_gate": {
        "fn": tool_gate,
        "description": "Architecture regression gate: validate .genesis/rules.json.",
    },
}


def list_tools() -> list[dict]:
    """Return tool metadata (name + description). SDK-independent."""
    return [{"name": name, "description": meta["description"]} for name, meta in TOOLS.items()]


def call_tool(name: str, project_dir: str = ".") -> dict:
    """Invoke a tool by name. Raises KeyError if unknown."""
    if name not in TOOLS:
        raise KeyError(f"unknown tool: {name}")
    return TOOLS[name]["fn"](project_dir)


# ---------------------------------------------------------------------------
# Optional MCP server (only if the `mcp` SDK is installed)
# ---------------------------------------------------------------------------

def mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def build_mcp_server():
    """Build an MCP server exposing the Genesis tools.

    Requires the `mcp` SDK. Raises RuntimeError with guidance if missing, so the
    rest of the package never hard-depends on MCP.
    """
    if not mcp_available():
        raise RuntimeError(
            "MCP SDK not installed. Install with: pip install mcp\n"
            "The Genesis analysis tools themselves work without it via "
            "call_tool()/list_tools()."
        )
    from mcp.server.fastmcp import FastMCP  # type: ignore

    server = FastMCP("genesis-architect")
    for name, meta in TOOLS.items():
        fn = meta["fn"]

        def make_handler(f):
            def handler(project_dir: str = ".") -> dict:
                return f(project_dir)
            return handler

        server.tool(name=name, description=meta["description"])(make_handler(fn))
    return server
