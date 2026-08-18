"""The capability map: every engine, and the command that reaches it.

This module exists because of a specific, expensive failure. An agent using
Genesis needed the recovery scan before extending code it had not diagnosed,
and the engine was there - but nothing in `genesis --help` or the README
named it, so the engine was found by running `ls src/` and reading the
package. Capability the product already has is worth nothing if the surface
never mentions it.

Two rules keep this honest:

1. Every module in the package is either mapped to a command here or listed
   in ``INTERNAL`` as plumbing. ``unmapped_modules()`` reports anything that
   is in neither, and a test asserts the set is empty - so adding a module
   forces the decision "does this deserve a door?" instead of leaving it to
   be discovered by accident later.
2. An entry with ``command=None`` is a declared gap, printed as such. A
   capability with no way to reach it should read as an admission, not be
   quietly omitted from the list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    module: str
    title: str
    what: str
    command: str | None   # None = no CLI door yet (printed as a gap)

    @property
    def reachable(self) -> bool:
        return self.command is not None


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------

CAPABILITIES: tuple[Capability, ...] = (
    # --- diagnosis ---
    Capability("recovery_scan", "Recovery Scan",
               "Diagnoses an existing codebase: drift, broken imports, decay",
               "genesis recover [PATH]"),
    Capability("recovery_report", "Recovery Report",
               "Renders the recovery scan as a prioritised report",
               "genesis recover [PATH]"),
    Capability("import_graph", "Import Graph",
               "Multi-language dependency graph with cycle detection",
               "genesis recover [PATH]"),
    Capability("import_audit", "Import Audit",
               "Finds imports that resolve to nothing",
               "genesis recover [PATH]"),
    Capability("architecture_scorer", "Architecture Scorer",
               "0-100 quality score across 4 dimensions, 6 adaptive profiles",
               "genesis recover [PATH]"),
    Capability("antipattern_detector", "Anti-Pattern Detector",
               "7 structural detectors: god-class, hub-file, circular deps, dead code",
               "genesis recover [PATH]"),
    Capability("fragility_classifier", "Fragility Classifier",
               "STABLE / FRAGILE / VOLATILE per module, from git churn + coverage",
               "genesis recover [PATH]"),
    Capability("drift_detector", "Drift Detector",
               "Detects divergence between the plan and the code on disk",
               "genesis recover [PATH]"),
    Capability("drift_scorer", "Drift Scorer",
               "Scores how far the project has drifted, with a trend",
               "genesis recover [PATH]"),
    Capability("decay_regressor", "Decay Regressor",
               "Projects where quality is heading if nothing changes",
               "genesis recover [PATH]"),
    Capability("git_analyzer", "Git Analyzer",
               "Churn, hotspots, and authorship signals from git history",
               "genesis recover [PATH]"),

    # --- research ---
    Capability("research_orchestrator", "Research Orchestrator",
               "Merges four research streams, ranks them, enforces the research floor",
               'genesis research "<topic>" [--json-data FILE]'),
    Capability("pitfall_ranker", "Pitfall Ranker",
               "Dedupes and scores pitfalls; ranks without needing engagement counts",
               'genesis research "<topic>" --json-data FILE'),
    Capability("video_research", "Media Research",
               "Builds YouTube/Reddit/Instagram queries and parses the results",
               'genesis research "<topic>" --video'),
    Capability("video_to_pitfall", "Video to Pitfall",
               "Turns a /watch analysis into cited PITFALLS.md entries",
               'genesis research "<topic>" --absorb FILE'),
    Capability("research_outline", "Research Outline",
               "States what to research before investigating: an items x fields "
               "grid, saved as outline.json/fields.json",
               "genesis decide \"research <topic>\""),
    Capability("field_intelligence", "Field Intelligence",
               "Practitioner signal from Reddit Answers and similar surfaces",
               "genesis decide \"research <topic>\""),
    Capability("source_registry", "Source Registry",
               "Which sources are trusted for which kind of claim",
               "genesis decide \"research <topic>\""),
    Capability("source_anchor", "Source Anchor",
               "Pins every claim to a retrievable source",
               "genesis decide \"research <topic>\""),
    Capability("evidence_pack", "Evidence Pack",
               "Bundles the evidence behind a decision for review",
               "genesis decide \"research <topic>\""),
    Capability("product_intelligence", "Product Intelligence",
               "Competitive and positioning signal for the vision",
               "genesis decide \"research <topic>\""),

    # --- security & dependencies ---
    Capability("security_templates", "Security Templates",
               "STRIDE threat model + OWASP Top 10 checklist, archetype-aware",
               "genesis harden [PATH]"),
    Capability("secrets_scanner", "Secrets Scanner",
               "Finds committed credentials and tokens",
               "genesis harden [PATH]"),
    Capability("dependency_scanner", "Dependency Scanner",
               "Maps third-party imports per module and looks up their CVEs",
               "genesis deps [PATH]"),
    Capability("package_registry", "Package Registry",
               "Validates packages against PyPI/npm/crates.io/Maven/NuGet + OSV",
               "genesis deps [PATH] --package NAME"),
    Capability("dependency_index", "Dependency Index",
               "Caches the resolved dependency graph between runs",
               "genesis deps [PATH]"),
    Capability("stdlib_filter", "Stdlib Filter",
               "Separates standard-library imports from third-party ones",
               "genesis deps [PATH]"),

    # --- planning & refactoring ---
    Capability("refactoring_planner", "Refactoring Planner",
               "Tier-1/2 refactor steps with projected score impact",
               "genesis decide \"refactor <target>\""),
    Capability("c4_generator", "C4 Generator",
               "C4 Level 1-3 architecture diagrams as GitHub-native Mermaid",
               "genesis decide \"document the architecture\""),
    Capability("knowledge_graph", "Knowledge Graph",
               "Links code, CVEs, risks, and decisions into one queryable graph",
               "genesis decide \"diagnose the project\""),
    Capability("decision_engine", "Decision Engine",
               "Routes an instruction to the right engines and gates the writes",
               "genesis decide \"<instruction>\""),
    Capability("red_team_critic", "Red Team Critic",
               "Attacks the plan and separates evidence from inference",
               "genesis decide \"<instruction>\""),
    Capability("rules_engine", "Rules Engine",
               "Hard and soft project rules, enforced at the gate",
               "genesis decide \"<instruction>\""),

    # --- memory & session ---
    Capability("cross_session_memory", "Cross-Session Memory",
               "Restores research/build context from a previous session",
               "genesis memory --sessions"),
    Capability("memory_engine", "Project Memory",
               "The per-project .genesis/*.md memory files",
               "genesis memory"),
    Capability("learning_engine", "Learning Engine",
               "Learns from accepted and rejected findings over time",
               "genesis telemetry"),
    Capability("progress_report", "Progress Report",
               "What changed since the last session",
               "genesis memory --status"),

    # --- workspace & companion ---
    Capability("companion_ui", "Companion UI",
               "The Genesis health page served locally",
               "genesis companion"),
    Capability("companion_window", "Companion Window",
               "The Floating Assistant shell",
               "genesis companion --ui"),
    Capability("gde_companion", "Companion Backend",
               "WebSocket + IDE bridge backing the Companion",
               "genesis companion --serve"),
    Capability("ui_workspace", "Canvas Workspace",
               "Self-contained HTML workspace for the current project",
               "genesis ui"),
    Capability("genesis_sync", "Autonomous Sync",
               "Gate + findings + auto-apply for the GREEN zone",
               "genesis sync"),
    Capability("mcp_advisor", "MCP Advisor",
               "Recommends MCP servers and skills for this project",
               "genesis advise"),
    Capability("mcp_tools", "MCP Tools",
               "Exposes Genesis engines as MCP tools",
               "genesis advise"),
    Capability("skill_fetcher", "Skill Fetcher",
               "Fetches a whitelisted skill pack into an ephemeral sandbox",
               "genesis fetch [SOURCE]"),
    Capability("ephemeral_purge", "Auto-Purge",
               "Reports and removes expired ephemeral resources",
               "genesis purge [--apply]"),
    Capability("first_run", "Readiness Check",
               "Install and optional-dependency readiness",
               "genesis doctor"),
    Capability("model_store", "Model Store",
               "Local STT/TTS model download and cache",
               "genesis companion --setup"),
    Capability("intent_classifier", "Intent Classifier",
               "Maps a plain-English instruction onto a mode",
               "genesis decide --classify-only \"<instruction>\""),
)

# Plumbing: shared types, registries, adapters, and wiring. These have no
# capability of their own to reach, so they are deliberately doorless.
INTERNAL: frozenset[str] = frozenset({
    "engine_registry",
    "gate_notifier_patch",
    "gde_cli",
    "gde_engine_adapters",
    "gde_engine_registration",
    "gde_gate_engine",
    "gde_knowledge_graph_adapter",
    "gde_planner",
    "gde_runner",
    "gde_session",
    "gde_types",
    "capability_map",
})


# ---------------------------------------------------------------------------
# Drift guard
# ---------------------------------------------------------------------------

def _package_modules() -> set[str]:
    from pathlib import Path

    package_dir = Path(__file__).parent
    return {
        path.stem for path in package_dir.glob("*.py")
        if not path.stem.startswith("_")
    }


def unmapped_modules() -> set[str]:
    """Modules that are neither mapped to a command nor declared internal.

    The README's engine table drifted from reality because nothing checked it.
    This is the check: a module that appears here is one the surface does not
    account for, and the accompanying test fails until it does.
    """
    mapped = {c.module for c in CAPABILITIES}
    return _package_modules() - mapped - INTERNAL


def stale_entries() -> set[str]:
    """Mapped modules that no longer exist in the package."""
    return {c.module for c in CAPABILITIES} - _package_modules()


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def gaps() -> tuple[Capability, ...]:
    """Capabilities with no CLI door yet."""
    return tuple(c for c in CAPABILITIES if not c.reachable)


def format_map(*, show_modules: bool = False) -> str:
    """The capability map as a readable table, grouped by command."""
    lines = [
        "",
        "Genesis engines and the commands that reach them",
        "=" * 62,
        "",
    ]

    by_command: dict[str, list[Capability]] = {}
    for cap in CAPABILITIES:
        by_command.setdefault(cap.command or "(no command yet)", []).append(cap)

    for command in sorted(by_command, key=lambda c: (c == "(no command yet)", c)):
        lines.append(f"  {command}")
        for cap in by_command[command]:
            suffix = f"   [{cap.module}]" if show_modules else ""
            lines.append(f"      {cap.title:<26} {cap.what}{suffix}")
        lines.append("")

    missing = gaps()
    if missing:
        lines.append(f"  {len(missing)} capability/ies have no command yet.")
        lines.append("")

    unmapped = unmapped_modules()
    if unmapped:
        # Printed rather than hidden: an unaccounted module is exactly the
        # condition that made engines undiscoverable in the first place.
        lines.append(f"  Not yet accounted for in this map: {', '.join(sorted(unmapped))}")
        lines.append("")

    lines.append(f"  {len(CAPABILITIES)} engines mapped. "
                 f"Run `genesis <command> --help` for any command above.")
    lines.append("")
    return "\n".join(lines)


def to_dict() -> dict:
    """Machine-readable capability map."""
    return {
        "engines": [
            {"module": c.module, "title": c.title, "what": c.what,
             "command": c.command, "reachable": c.reachable}
            for c in CAPABILITIES
        ],
        "internal_modules": sorted(INTERNAL),
        "gaps": [c.module for c in gaps()],
        "unmapped_modules": sorted(unmapped_modules()),
        "stale_entries": sorted(stale_entries()),
    }
