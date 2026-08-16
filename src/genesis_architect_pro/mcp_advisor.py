"""Dual-Level MCP & Skill Advisor — recommends external tooling, with evidence.

Two levels, deliberately different in what they are allowed to reason from:

  GLOBAL  — cross-project intelligence. Reads the learning engine's recorded
            outcomes (`.genesis/learning/outcomes.jsonl`) and recommends tools
            for the domains this operator actually works in.
  LOCAL   — project-level discovery. Inspects repository structure and
            dependency manifests and recommends tools tailored to what is
            genuinely in the tree.

Deterministic by construction: signal detection is file existence plus manifest
parsing, and the catalog is a static table. No LLM, no network, no guessing —
the same repository always yields the same advice.

Evidence discipline: a recommendation may only fire from a signal that was
actually observed, and it carries the concrete file that proved it. There is no
path in this module that produces a suggestion without naming its evidence,
because advice whose basis cannot be inspected is indistinguishable from a
guess.

Nothing here installs anything. The advisor explains what a tool would buy and
how Genesis would drive it once present; acting on that stays the user's call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    """A recommendable tool. `orchestration` is the promise Genesis makes about
    what it will actually do with the tool once it exists."""

    tool_id: str
    kind: str            # "mcp_server" | "skill"
    title: str
    optimizes: str       # what it makes faster/possible
    orchestration: str   # how Genesis drives it once installed
    install_hint: str


CATALOG: dict[str, ToolSpec] = {
    "github": ToolSpec(
        tool_id="github", kind="mcp_server", title="GitHub MCP",
        optimizes="Issue mining, PR review and release inspection without leaving the session.",
        orchestration="Feeds the research orchestrator's stream C (issue mining) and lets "
                      "`genesis decide` read real PR/issue history instead of inferring it.",
        install_hint="claude mcp add github",
    ),
    "docker": ToolSpec(
        tool_id="docker", kind="mcp_server", title="Docker MCP",
        optimizes="Reproducible builds and throwaway environments for risky changes.",
        orchestration="Lets the GATE mode validate a change inside a container before "
                      "APPROVE, rather than trusting a local-only run.",
        install_hint="claude mcp add docker",
    ),
    "playwright": ToolSpec(
        tool_id="playwright", kind="mcp_server", title="Playwright MCP",
        optimizes="Real browser automation for login-gated flows and JS-heavy pages.",
        orchestration="Used only for interaction-dependent checks; static pages stay on "
                      "the cheaper fetchers per the routing rules.",
        install_hint="claude mcp add playwright",
    ),
    "chrome-devtools": ToolSpec(
        tool_id="chrome-devtools", kind="mcp_server", title="Chrome DevTools MCP",
        optimizes="Console/network inspection and Lighthouse audits against a live page.",
        orchestration="On any extension bug report, Genesis opens the extension and reads "
                      "the real console/network trace before proposing a fix.",
        install_hint="claude mcp add chrome-devtools",
    ),
    "context7": ToolSpec(
        tool_id="context7", kind="mcp_server", title="Context7 MCP",
        optimizes="Current library/framework docs, so version-specific APIs aren't recalled from memory.",
        orchestration="Consulted before writing code against any pinned dependency — the "
                      "same discipline this repo already applies to fast-moving SDKs.",
        install_hint="claude mcp add context7",
    ),
    "exa": ToolSpec(
        tool_id="exa", kind="mcp_server", title="Exa MCP",
        optimizes="Semantic web search for ecosystem and prior-art discovery.",
        orchestration="Drives stream B of the research orchestrator; results are ranked by "
                      "pitfall_ranker alongside GitHub issues rather than trusted raw.",
        install_hint="claude mcp add exa",
    ),
    "tavily": ToolSpec(
        tool_id="tavily", kind="mcp_server", title="Tavily MCP",
        optimizes="Second independent search backend, so one provider outage isn't a blind spot.",
        orchestration="Run in parallel with Exa for topic search; disagreement between them "
                      "is surfaced rather than silently resolved.",
        install_hint="claude mcp add tavily",
    ),
    "neon": ToolSpec(
        tool_id="neon", kind="mcp_server", title="Neon / Postgres MCP",
        optimizes="Schema inspection, migration planning and query tuning against a real database.",
        orchestration="Lets the architecture model anchor data-layer responsibilities to "
                      "actual schema instead of inferring them from ORM code.",
        install_hint="claude mcp add neon",
    ),
    "21st": ToolSpec(
        tool_id="21st", kind="mcp_server", title="21st.dev Component MCP",
        optimizes="Vetted UI component search, so frontend work starts from real patterns.",
        orchestration="Consulted during UI build tasks before hand-rolling a component.",
        install_hint="claude mcp add 21st",
    ),
    "figma": ToolSpec(
        tool_id="figma", kind="mcp_server", title="Figma MCP",
        optimizes="Design-to-code fidelity: real tokens, spacing and components from the source design.",
        orchestration="Pulls design context so generated UI matches the design system rather "
                      "than approximating it.",
        install_hint="Connect Figma in claude.ai connector settings",
    ),
    "software-architecture-skills": ToolSpec(
        tool_id="software-architecture-skills", kind="skill",
        title="Software Architecture Skills (45ck)",
        optimizes="ADR writing, tradeoff analysis and quality-attribute scenarios as repeatable artifacts.",
        orchestration="Genesis's DOCUMENT mode emits C4 diagrams; these skills supply the "
                      "written decision record that should accompany them.",
        install_hint="https://github.com/45ck/software-architecture-skills",
    ),
    "deep-research-skills": ToolSpec(
        tool_id="deep-research-skills", kind="skill",
        title="Deep Research Skills (Weizhena)",
        optimizes="Two-phase research — outline first, then deep investigation with human review.",
        orchestration="Structures the RESEARCH mode's scouting phase before an Evidence Pack "
                      "is assembled, so gathering is planned rather than opportunistic.",
        install_hint="https://github.com/Weizhena/Deep-Research-skills",
    ),
}


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


@dataclass
class ProjectSignals:
    """What was actually observed in the tree. `evidence` maps each signal to
    the concrete path that proved it."""

    languages: set[str] = field(default_factory=set)
    frameworks: set[str] = field(default_factory=set)
    has_github_remote: bool = False
    has_docker: bool = False
    has_ci: bool = False
    has_tests: bool = False
    is_chrome_extension: bool = False
    has_database: bool = False
    evidence: dict[str, str] = field(default_factory=dict)

    def note(self, signal: str, proof: Path | str) -> None:
        self.evidence[signal] = str(proof)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def detect_signals(project_dir: Path) -> ProjectSignals:
    """Inspect a repository and report only what is genuinely there."""
    root = Path(project_dir)
    signals = ProjectSignals()
    if not root.is_dir():
        return signals

    # --- Node / JS ecosystem ---
    package_json = root / "package.json"
    if package_json.is_file():
        signals.languages.add("javascript")
        signals.note("javascript", package_json)
        data = _read_json(package_json) or {}
        deps = {}
        for key in ("dependencies", "devDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                deps.update(section)
        for name, framework in (
            ("react", "react"), ("vue", "vue"), ("svelte", "svelte"),
            ("next", "next"), ("expo", "expo"), ("react-native", "react-native"),
        ):
            if name in deps:
                signals.frameworks.add(framework)
                signals.note(f"framework:{framework}", package_json)
        if "prisma" in deps or "@prisma/client" in deps:
            signals.has_database = True
            signals.note("database", package_json)

    # --- Python ---
    for candidate in ("pyproject.toml", "requirements.txt", "setup.py"):
        path = root / candidate
        if path.is_file():
            signals.languages.add("python")
            signals.note("python", path)
            break

    # --- Other languages ---
    for candidate, language in (("go.mod", "go"), ("Cargo.toml", "rust")):
        path = root / candidate
        if path.is_file():
            signals.languages.add(language)
            signals.note(language, path)

    # --- Docker ---
    for candidate in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                      "compose.yml", "compose.yaml"):
        path = root / candidate
        if path.is_file():
            signals.has_docker = True
            signals.note("docker", path)
            break

    # --- CI ---
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        try:
            if any(workflows.iterdir()):
                signals.has_ci = True
                signals.note("ci", workflows)
        except OSError:
            pass

    # --- Chrome extension (manifest_version is the reliable marker) ---
    manifest = root / "manifest.json"
    if manifest.is_file():
        data = _read_json(manifest) or {}
        if "manifest_version" in data:
            signals.is_chrome_extension = True
            signals.note("chrome_extension", manifest)

    # --- Database ---
    if not signals.has_database:
        for candidate in ("alembic.ini", "prisma", "migrations"):
            path = root / candidate
            if path.exists():
                signals.has_database = True
                signals.note("database", path)
                break

    # --- Tests ---
    for candidate in ("tests", "test", "__tests__", "spec"):
        path = root / candidate
        if path.is_dir():
            signals.has_tests = True
            signals.note("tests", path)
            break

    # --- GitHub remote ---
    git_config = root / ".git" / "config"
    if git_config.is_file():
        try:
            text = git_config.read_text(encoding="utf-8", errors="replace")
            if "github.com" in text:
                signals.has_github_remote = True
                signals.note("github_remote", git_config)
        except OSError:
            pass

    return signals


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


@dataclass
class ToolRecommendation:
    """A single suggestion. Named distinctly from learning_engine.Recommendation,
    which is a different thing (research profile selection)."""

    tool_id: str
    kind: str
    scope: str            # "global" | "local"
    title: str
    why: str
    optimizes: str
    orchestration: str
    evidence: list[str] = field(default_factory=list)
    already_available: bool = False
    install_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "tool_id": self.tool_id, "kind": self.kind, "scope": self.scope,
            "title": self.title, "why": self.why, "optimizes": self.optimizes,
            "orchestration": self.orchestration, "evidence": self.evidence,
            "already_available": self.already_available,
            "install_hint": self.install_hint,
        }


@dataclass
class AdvisorReport:
    local: list[ToolRecommendation] = field(default_factory=list)
    global_: list[ToolRecommendation] = field(default_factory=list)
    signals: ProjectSignals = field(default_factory=ProjectSignals)
    notes: list[str] = field(default_factory=list)

    @property
    def actionable(self) -> list[ToolRecommendation]:
        """Recommendations for tools that are not already available."""
        return [r for r in self.local + self.global_ if not r.already_available]


def _rec(tool_id: str, scope: str, why: str, evidence: list[str]) -> ToolRecommendation | None:
    spec = CATALOG.get(tool_id)
    if spec is None:
        return None
    return ToolRecommendation(
        tool_id=spec.tool_id, kind=spec.kind, scope=scope, title=spec.title,
        why=why, optimizes=spec.optimizes, orchestration=spec.orchestration,
        evidence=evidence, install_hint=spec.install_hint,
    )


def advise_local(project_dir: Path, signals: ProjectSignals | None = None) -> list[ToolRecommendation]:
    """Recommendations derived strictly from what is in this repository."""
    sig = signals if signals is not None else detect_signals(project_dir)
    out: list[ToolRecommendation] = []

    def add(tool_id: str, why: str, *signal_keys: str) -> None:
        evidence = [f"{key} → {sig.evidence[key]}" for key in signal_keys if key in sig.evidence]
        if not evidence:
            return  # never emit advice without the evidence that triggered it
        rec = _rec(tool_id, "local", why, evidence)
        if rec is not None:
            out.append(rec)

    if sig.has_github_remote:
        add("github", "This repo has a GitHub remote, so issue/PR history is real "
                      "evidence Genesis can mine instead of inferring.", "github_remote")

    if sig.has_docker:
        add("docker", "Docker files are present, so changes can be validated in a "
                      "throwaway environment before they touch the host.", "docker")

    if sig.is_chrome_extension:
        add("chrome-devtools", "manifest_version marks this a Chrome extension; extension "
                               "bugs are diagnosed from the live console/network trace, "
                               "not from reading source.", "chrome_extension")

    if sig.frameworks & {"react", "vue", "svelte", "next"}:
        key = next(iter(sorted(sig.frameworks & {"react", "vue", "svelte", "next"})))
        add("21st", "A frontend framework is in the dependency manifest, so UI work "
                    "should start from vetted components rather than hand-rolled ones.",
            f"framework:{key}")
        add("figma", "Frontend project — design context keeps generated UI matching the "
                     "design system instead of approximating it.", f"framework:{key}")

    if sig.frameworks & {"react-native", "expo"}:
        key = "expo" if "expo" in sig.frameworks else "react-native"
        add("context7", "Expo/React Native APIs move fast enough that recalling them from "
                        "memory is unreliable; pinned-version docs are the fix.",
            f"framework:{key}")

    if sig.has_database:
        add("neon", "Database tooling is present, so schema can be inspected directly "
                    "rather than inferred from ORM models.", "database")

    if sig.languages and not sig.frameworks & {"react-native", "expo"}:
        key = next(iter(sorted(sig.languages)))
        add("context7", "A dependency manifest is present; version-specific API details "
                        "should come from current docs, not from memory.", key)

    if sig.languages:
        key = next(iter(sorted(sig.languages)))
        add("software-architecture-skills",
            "A real codebase benefits from written decision records alongside the C4 "
            "diagrams Genesis already generates in DOCUMENT mode.", key)

    # Deduplicate by tool_id, keeping the first (most specific) reason.
    seen: set[str] = set()
    deduped: list[ToolRecommendation] = []
    for rec in out:
        if rec.tool_id in seen:
            continue
        seen.add(rec.tool_id)
        deduped.append(rec)
    return deduped


# Which task kinds imply which tooling. Deterministic, and deliberately small —
# a mapping nobody can audit is worse than one that covers less.
_TASK_KIND_TOOLS: dict[str, tuple[str, ...]] = {
    "research": ("exa", "tavily", "deep-research-skills"),
    "library_evaluation": ("exa", "context7"),
    "deep_research": ("exa", "tavily", "deep-research-skills"),
    "architecture": ("software-architecture-skills",),
    "architecture_review": ("software-architecture-skills",),
    "security": ("github",),
    "security_review": ("github",),
    "migration": ("context7",),
    "migration_planner": ("context7",),
}


def advise_global(project_dir: Path) -> tuple[list[ToolRecommendation], list[str]]:
    """Recommendations derived from recorded cross-task history.

    Returns (recommendations, notes). Notes explain an empty result rather than
    letting silence imply "nothing to suggest".
    """
    from genesis_architect_pro.learning_engine import read_outcomes

    notes: list[str] = []
    try:
        outcomes = read_outcomes(project_dir)
    except Exception:  # noqa: BLE001 — advice must never break on unreadable history
        return [], ["Learning history could not be read; global advice skipped."]

    if not outcomes:
        return [], ["No recorded task history yet — global advice needs outcomes in "
                    ".genesis/learning/outcomes.jsonl before it can say anything real."]

    counts: dict[str, int] = {}
    for outcome in outcomes:
        kind = (outcome.task_kind or "").strip().lower()
        if kind:
            counts[kind] = counts.get(kind, 0) + 1

    out: list[ToolRecommendation] = []
    seen: set[str] = set()
    for kind, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        for tool_id in _TASK_KIND_TOOLS.get(kind, ()):
            if tool_id in seen:
                continue
            rec = _rec(
                tool_id, "global",
                f"{count} recorded {kind!r} task(s) across this history — a domain you "
                f"work in repeatedly, so the tooling pays for itself.",
                [f"outcomes.jsonl → {count}× task_kind={kind!r}"],
            )
            if rec is not None:
                seen.add(tool_id)
                out.append(rec)

    if not out:
        notes.append(
            f"{len(outcomes)} outcome(s) recorded, but none map to a tool in the catalog."
        )
    return out, notes


# ---------------------------------------------------------------------------
# Already-installed detection
# ---------------------------------------------------------------------------


def installed_mcp_servers() -> set[str]:
    """Best-effort read of configured MCP servers, so the advisor doesn't
    recommend what is already present. Unreadable config yields an empty set —
    over-recommending is a far cheaper failure than crashing on a config file."""
    names: set[str] = set()

    # An explicit override is authoritative: if it is set, the real user config
    # is never consulted, even when the override yields nothing. Falling back
    # would make behaviour depend on whatever happens to be on the machine,
    # which defeats the point of being able to pin it.
    override = os.environ.get("GENESIS_MCP_CONFIG")
    candidates = [Path(override)] if override else [Path.home() / ".claude.json"]

    for path in candidates:
        if not path.is_file():
            continue
        data = _read_json(path)
        if data is None:
            continue
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            names.update(str(k) for k in servers)
        projects = data.get("projects")
        if isinstance(projects, dict):
            for entry in projects.values():
                if isinstance(entry, dict) and isinstance(entry.get("mcpServers"), dict):
                    names.update(str(k) for k in entry["mcpServers"])
        if names:
            break
    return names


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------


def advise(
    project_dir: Path,
    *,
    include_global: bool = True,
    include_local: bool = True,
    check_installed: bool = True,
) -> AdvisorReport:
    """Produce the full dual-level report."""
    root = Path(project_dir)
    report = AdvisorReport()
    report.signals = detect_signals(root)

    if include_local:
        report.local = advise_local(root, report.signals)
    if include_global:
        report.global_, notes = advise_global(root)
        report.notes.extend(notes)

    if check_installed:
        try:
            installed = installed_mcp_servers()
        except Exception:  # noqa: BLE001
            installed = set()
        if installed:
            for rec in report.local + report.global_:
                if rec.kind == "mcp_server" and rec.tool_id in installed:
                    rec.already_available = True

    if not report.signals.evidence:
        report.notes.append(
            "No recognisable project signals found — local advice needs a dependency "
            "manifest, git config, or similar to reason from."
        )
    return report


def format_report(report: AdvisorReport) -> str:
    """Render the advisor report for the terminal."""
    lines = ["", "  Genesis Tooling Advisor", ""]

    if report.signals.evidence:
        lines.append("  Detected in this project:")
        for signal, proof in sorted(report.signals.evidence.items()):
            lines.append(f"    {signal:<24} {proof}")
        lines.append("")

    for scope, items in (("LOCAL", report.local), ("GLOBAL", report.global_)):
        if not items:
            continue
        lines.append(f"  {scope} recommendations ({len(items)}):")
        lines.append("")
        for rec in items:
            marker = "  [already available] " if rec.already_available else "  "
            lines.append(f"  {marker}{rec.title}  ({rec.kind})")
            lines.append(f"      {'Why:':<11}{rec.why}")
            lines.append(f"      {'Optimizes:':<11}{rec.optimizes}")
            lines.append(f"      {'Genesis:':<11}{rec.orchestration}")
            for item in rec.evidence:
                lines.append(f"      {'Evidence:':<11}{item}")
            if not rec.already_available and rec.install_hint:
                lines.append(f"      {'Install:':<11}{rec.install_hint}")
            lines.append("")

    for note in report.notes:
        lines.append(f"  Note: {note}")
    if report.notes:
        lines.append("")

    actionable = report.actionable
    if actionable:
        lines.append(f"  {len(actionable)} tool(s) suggested. Nothing was installed — "
                     f"that stays your call.")
    else:
        lines.append("  Nothing to suggest beyond what you already have.")
    lines.append("")
    return "\n".join(lines)
