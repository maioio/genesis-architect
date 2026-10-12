"""Public capability catalog: the user-facing layer on top of ``capability_map``.

``capability_map.CAPABILITIES`` answers "which module has a door?". This module
adds what a reader needs before trusting a feature: which family it belongs to,
how mature it is, what it writes, whether it touches the network or an LLM, and
which optional dependency it needs. ``COMMANDS`` classifies every top-level
``genesis`` command.

Single chain of truth:  source modules -> capability_map -> this catalog ->
``data/public-capabilities.json`` -> docs and README -> drift tests. Nothing here
repeats a title or a command: those are read from ``capability_map`` so they
cannot disagree.

Vocabulary
----------
maturity: ``stable`` (default install, tested), ``optional`` (needs an extra or an
          external tool), ``experimental`` (no direct test coverage yet).
writes:   ``none`` (writes nothing), ``state`` (only ``.genesis/`` and generated
          reports in the project), ``project`` (can create or delete files
          elsewhere in the project or on disk; always opt-in or dry-run first).
network:  ``none``, ``optional`` (works offline, uses the network when enabled),
          ``required``.
"""

from __future__ import annotations

from dataclasses import dataclass

from genesis_architect.pro.capability_map import CAPABILITIES, INTERNAL

FAMILIES: dict[str, str] = {
    "research": "Research & Evidence",
    "recovery": "Existing Codebase Recovery",
    "architecture": "Architecture Intelligence",
    "decision": "Decision & Planning",
    "security": "Security & Dependencies",
    "memory": "Memory & Learning",
    "automation": "Automation & Sync",
    "companion": "Companion, UI & Voice",
    "agents": "Agents & MCP",
}


@dataclass(frozen=True)
class Meta:
    family: str
    maturity: str = "stable"
    writes: str = "state"
    network: str = "none"
    llm: str = "no"          # no | optional | required
    extra: str | None = None  # optional dependency or external tool
    note: str | None = None   # limitation worth stating publicly


_R, _P = "none", "project"

META: dict[str, Meta] = {
    # Research & Evidence
    "research_orchestrator": Meta("research", network="optional", note="Live search needs network; --json-data runs offline on supplied results."),
    "pitfall_ranker": Meta("research", writes=_R),
    "video_research": Meta("research", maturity="optional", network="required", extra="yt-dlp, ffmpeg"),
    "video_to_pitfall": Meta("research", maturity="optional", extra="ffmpeg"),
    "research_outline": Meta("research"),
    "field_intelligence": Meta("research"),
    "source_registry": Meta("research"),
    "source_anchor": Meta("research", writes=_R),
    "evidence_pack": Meta("research"),
    "product_intelligence": Meta("research", note="Telemetry is opt-in and off by default."),
    # Existing Codebase Recovery
    "recovery_scan": Meta("recovery"),
    "recovery_report": Meta("recovery"),
    "fragility_classifier": Meta("recovery"),
    "drift_detector": Meta("recovery", writes=_R),
    "drift_scorer": Meta("recovery", writes=_R),
    "decay_regressor": Meta("recovery", writes=_R),
    "git_analyzer": Meta("recovery", writes=_R, extra="git"),
    # Architecture Intelligence
    "import_graph": Meta("architecture"),
    "import_audit": Meta("architecture", writes=_R),
    "architecture_scorer": Meta("architecture"),
    "antipattern_detector": Meta("architecture", writes=_R),
    "c4_generator": Meta("architecture", writes=_R),
    "knowledge_graph": Meta("architecture"),
    "refactoring_planner": Meta("architecture", writes=_R),
    # Decision & Planning
    "decision_engine": Meta("decision"),
    "red_team_critic": Meta("decision", llm="optional", network="optional", extra="anthropic (committee extra)", note="Deterministic checks always run; the LLM pass is additive and disclosed when skipped."),
    "engine_bootstrap": Meta("decision", writes=_R),
    "rules_engine": Meta("decision", writes=_R),
    "intent_classifier": Meta("decision", writes=_R),
    # Security & Dependencies
    "security_templates": Meta("security", note="Generates a checklist and threat model; it is not a vulnerability scanner."),
    "secrets_scanner": Meta("security", writes=_R),
    "dependency_scanner": Meta("security", writes=_R),
    "package_registry": Meta("security", writes=_R, network="optional"),
    "dependency_index": Meta("security", writes=_R),
    "stdlib_filter": Meta("security", writes=_R),
    # Memory & Learning
    "cross_session_memory": Meta("memory"),
    "memory_engine": Meta("memory"),
    "learning_engine": Meta("memory"),
    "progress_report": Meta("memory"),
    # Automation & Sync
    "genesis_sync": Meta("automation", note="Auto-applies only the GREEN zone; --dry-run reports without writing."),
    "skill_fetcher": Meta("automation", writes=_P, network="required", extra="git", note="Clones into a short-lived sandbox (default and maximum 2 hours)."),
    "ephemeral_purge": Meta("automation", writes=_P, note="Dry run by default; --apply removes expired worktrees and locks."),
    "first_run": Meta("automation", writes=_R),
    # Companion, UI & Voice
    "companion_ui": Meta("companion"),
    "companion_window": Meta("companion", maturity="experimental", extra="pywebview", note="Native floating window; falls back to the browser page when pywebview is unavailable."),
    "gde_companion": Meta("companion", maturity="optional", extra="plyer (notifications)", note="Local health page uses the standard library only."),
    "ui_workspace": Meta("companion"),
    "model_store": Meta("companion", maturity="optional", network="required", extra="voice extra", note="--setup downloads local STT/TTS models into ~/.genesis/models."),
    # Agents & MCP
    "mcp_advisor": Meta("agents", writes=_R, note="Recommends MCP servers and skills; installs nothing."),
    "mcp_tools": Meta("agents", writes=_R, note="Exposes four read-only tools over MCP."),
}


@dataclass(frozen=True)
class CommandInfo:
    name: str
    status: str   # PUBLIC | ADVANCED | LEGACY | DEPRECATED
    summary: str
    system: str   # argparse | typer


COMMANDS: tuple[CommandInfo, ...] = (
    CommandInfo("init", "PUBLIC", "Research GitHub, mine pitfalls, scaffold a new project (needs an LLM key or a local Ollama model)", "typer"),
    CommandInfo("research", "PUBLIC", "Multi-source research on a topic", "typer"),
    CommandInfo("resolve", "ADVANCED", "Look up a known solution: local vault first, then Stack Overflow", "typer"),
    CommandInfo("publish", "PUBLIC", "Draft a Show HN post and release notes with an LLM (needs LLM_API_KEY); you post them yourself", "typer"),
    CommandInfo("config", "PUBLIC", "Set, get or show API keys", "typer"),
    CommandInfo("upgrade", "LEGACY", "Kept for compatibility; Genesis has no paid tier", "typer"),
    CommandInfo("decide", "PUBLIC", "Run a full decision session on an instruction", "argparse"),
    CommandInfo("explain", "PUBLIC", "Print the last session's decision log", "argparse"),
    CommandInfo("memory", "PUBLIC", "Show or manage per-project memory in .genesis/", "argparse"),
    CommandInfo("engines", "PUBLIC", "List every engine and the command that reaches it", "argparse"),
    CommandInfo("deps", "PUBLIC", "Third-party dependencies per module, plus advisories", "argparse"),
    CommandInfo("ui", "PUBLIC", "Generate the self-contained HTML canvas workspace", "argparse"),
    CommandInfo("companion", "ADVANCED", "Local health page, notifications and optional voice", "argparse"),
    CommandInfo("sync", "ADVANCED", "Autonomous sync: gate, findings, GREEN-zone auto-apply", "argparse"),
    CommandInfo("doctor", "PUBLIC", "Readiness check for the install", "argparse"),
    CommandInfo("recover", "PUBLIC", "Diagnose drift, broken imports, anti-patterns and decay", "argparse"),
    CommandInfo("harden", "PUBLIC", "STRIDE threat model, OWASP Top 10 checklist, secrets scan", "argparse"),
    CommandInfo("advise", "PUBLIC", "Recommend MCP servers and skills for this project", "argparse"),
    CommandInfo("fetch", "ADVANCED", "Fetch a trusted skill pack into a short-lived sandbox", "argparse"),
    CommandInfo("purge", "ADVANCED", "Remove expired worktrees and locks (dry run by default)", "argparse"),
    CommandInfo("telemetry", "ADVANCED", "Manage opt-in telemetry; the default is off", "argparse"),
    CommandInfo("license", "LEGACY", "Kept for compatibility; no license key is needed", "argparse"),
)


def build_catalog() -> list[dict]:
    """Merge the capability map with ``META``; raises if the two disagree."""
    missing = [c.module for c in CAPABILITIES if c.module not in META]
    extra = sorted(set(META) - {c.module for c in CAPABILITIES})
    if missing or extra:
        raise ValueError(
            f"capability_catalog.META is out of sync with capability_map: "
            f"no META for {sorted(missing)}; META for unmapped {extra}."
        )
    rows = []
    for c in CAPABILITIES:
        m = META[c.module]
        rows.append({
            "id": c.module,
            "name": c.title,
            "summary": c.what,
            "family": m.family,
            "command": c.command,
            "maturity": m.maturity,
            "writes": m.writes,
            "network": m.network,
            "requires_llm": m.llm,
            "optional_dependency": m.extra,
            "source_module": f"src/genesis_architect/pro/{c.module}.py",
            "limitation": m.note,
        })
    return rows


def catalog_summary() -> dict:
    rows = build_catalog()
    return {
        "capabilities": len(rows),
        "internal_modules": len(INTERNAL),
        "families": {k: sum(1 for r in rows if r["family"] == k) for k in FAMILIES},
        "commands": len(COMMANDS),
    }
