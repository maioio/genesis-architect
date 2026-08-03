"""
recovery_report.py - Genesis Architect PRO

Read-only, deterministic recovery intelligence report.

Combines all recovery scan outputs into a single structured, actionable report
with machine-readable JSON and optional Markdown rendering.

No writes. No mutations. No auto-reconciliation. No UI integration.

Report structure
----------------
RecoveryReport
  executive_summary      str
  project_risk_level     str  (none/low/medium/high/critical)
  architecture_health    ArchitectureHealth
  drift_summary          DriftSummary
  recommendations        list[Recommendation]  — ordered by priority
  evidence_basis         dict[str, str]        — key → one-liner
  warnings               list[str]
  metadata               ReportMetadata

Recommendation priority ranking
--------------------------------
Priority 1 (critical)  — vagrant nodes with confidence ≥ 0.75
Priority 2 (high)      — stale responsibilities with confidence ≥ 0.70
Priority 3 (high)      — anti-patterns rated critical/high
Priority 4 (medium)    — unanchored responsibilities (>50% unanchored)
Priority 4 (medium)    — no planned model present (quick win)
Priority 5 (medium)    — fix-commit hotspots (churn ≥ 3 commits)
Priority 6 (low)       — stale responsibilities with confidence < 0.70
Priority 7 (low)       — dead-file candidates
Priority 8 (info)      — version drift detected

Within each priority band, items are sorted deterministically:
  - by confidence DESC
  - then by node_id / file ASC

Confidence propagation
-----------------------
Each Recommendation inherits the minimum confidence of all its evidence
signals. A recommendation backed only by low-confidence signals is
marked low.

Graceful degradation
---------------------
Any missing or corrupted input is silently skipped with a warning added.
An empty project (nothing in the scan) produces a valid "clean" report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIORITY_LABELS: dict[int, str] = {
    1: "critical",
    2: "high",
    3: "high",
    4: "medium",
    5: "medium",
    6: "low",
    7: "low",
    8: "info",
}

_RISK_LEVELS = ("none", "low", "medium", "high", "critical")


def _max_risk(*levels: str) -> str:
    best = 0
    for lv in levels:
        try:
            idx = _RISK_LEVELS.index(lv)
        except ValueError:
            continue
        best = max(best, idx)
    return _RISK_LEVELS[best]


# ---------------------------------------------------------------------------
# Sub-dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ArchitectureHealth:
    score: float | None          # 0-100 from architecture_scorer, None if unavailable
    label: str                   # e.g. "good", "fair", "poor"
    anti_pattern_count: int
    top_anti_patterns: list[str]
    hotspot_files: list[str]     # fix-commit hotspots (top 5)
    basis: str

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1) if self.score is not None else None,
            "label": self.label,
            "anti_pattern_count": self.anti_pattern_count,
            "top_anti_patterns": self.top_anti_patterns,
            "hotspot_files": self.hotspot_files,
            "basis": self.basis,
        }


@dataclass
class DriftSummary:
    overall_score: float
    risk_level: str
    vagrant_count: int
    stale_count: int
    unanchored_count: int
    top_risk_nodes: list[str]
    basis: str

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 2),
            "risk_level": self.risk_level,
            "vagrant_count": self.vagrant_count,
            "stale_count": self.stale_count,
            "unanchored_count": self.unanchored_count,
            "top_risk_nodes": self.top_risk_nodes,
            "basis": self.basis,
        }


@dataclass
class Recommendation:
    priority: int                # 1 = highest
    category: str                # vagrant/stale/anti-pattern/coverage/churn/dead-file/version
    title: str
    reason: str
    evidence: str
    confidence: float            # 0.0–1.0
    suggested_action: str
    affected: list[str]          # node_ids / file paths
    risk_zone: bool              # True → "do not touch yet"
    quick_win: bool              # True → low effort, high signal

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "category": self.category,
            "title": self.title,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
            "suggested_action": self.suggested_action,
            "affected": self.affected,
            "risk_zone": self.risk_zone,
            "quick_win": self.quick_win,
        }


@dataclass
class ReportMetadata:
    generator: str = "genesis_architect.pro.recovery_report"
    schema_version: str = "1.0"
    scan_keys_present: list[str] = field(default_factory=list)
    scan_keys_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generator": self.generator,
            "schema_version": self.schema_version,
            "scan_keys_present": self.scan_keys_present,
            "scan_keys_missing": self.scan_keys_missing,
        }


@dataclass
class RecoveryReport:
    executive_summary: str
    project_risk_level: str
    architecture_health: ArchitectureHealth
    drift_summary: DriftSummary
    recommendations: list[Recommendation] = field(default_factory=list)
    evidence_basis: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: ReportMetadata = field(default_factory=ReportMetadata)

    # --- derived views (computed lazily from recommendations) ---

    @property
    def quick_wins(self) -> list[Recommendation]:
        return [r for r in self.recommendations if r.quick_win]

    @property
    def risk_zones(self) -> list[Recommendation]:
        return [r for r in self.recommendations if r.risk_zone]

    @property
    def deep_refactor_candidates(self) -> list[Recommendation]:
        return [r for r in self.recommendations
                if not r.quick_win and not r.risk_zone and r.priority <= 3]

    def to_dict(self) -> dict:
        return {
            "executive_summary": self.executive_summary,
            "project_risk_level": self.project_risk_level,
            "architecture_health": self.architecture_health.to_dict(),
            "drift_summary": self.drift_summary.to_dict(),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "quick_wins": [r.to_dict() for r in self.quick_wins],
            "deep_refactor_candidates": [r.to_dict() for r in self.deep_refactor_candidates],
            "risk_zones": [r.to_dict() for r in self.risk_zones],
            "recommended_fix_order": [r.title for r in self.recommendations],
            "evidence_basis": self.evidence_basis,
            "warnings": self.warnings,
            "metadata": self.metadata.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        return _render_markdown(self)

    def to_html(self) -> str:
        return _render_html(self)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_markdown(report: RecoveryReport) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Genesis Recovery Report")
    add("")
    add(f"**Project Risk Level:** `{report.project_risk_level.upper()}`")
    add("")

    add("## Executive Summary")
    add("")
    add(report.executive_summary)
    add("")

    # Architecture health
    ah = report.architecture_health
    add("## Architecture Health")
    add("")
    score_str = f"{ah.score:.0f}/100" if ah.score is not None else "unavailable"
    add(f"- **Score:** {score_str} ({ah.label})")
    add(f"- **Anti-patterns detected:** {ah.anti_pattern_count}")
    if ah.top_anti_patterns:
        add(f"- **Top anti-patterns:** {', '.join(ah.top_anti_patterns)}")
    if ah.hotspot_files:
        add(f"- **Churn hotspots:** {', '.join(ah.hotspot_files[:3])}")
    add(f"- **Basis:** {ah.basis}")
    add("")

    # Drift summary
    ds = report.drift_summary
    add("## Drift Summary")
    add("")
    add(f"- **Drift score:** {ds.overall_score:.1f} / 100 ({ds.risk_level})")
    add(f"- **Vagrant nodes:** {ds.vagrant_count}")
    add(f"- **Stale responsibilities:** {ds.stale_count}")
    add(f"- **Unanchored responsibilities:** {ds.unanchored_count}")
    if ds.top_risk_nodes:
        add(f"- **Top risk nodes:** {', '.join(ds.top_risk_nodes)}")
    add(f"- **Basis:** {ds.basis}")
    add("")

    # Recommendations
    if report.recommendations:
        add("## Recommendations (by priority)")
        add("")
        for i, rec in enumerate(report.recommendations, 1):
            badge = ""
            if rec.quick_win:
                badge += " ⚡ Quick Win"
            if rec.risk_zone:
                badge += " 🚧 Risk Zone"
            add(f"### {i}. [{_PRIORITY_LABELS.get(rec.priority, 'info').upper()}] {rec.title}{badge}")
            add("")
            add(f"**Category:** {rec.category}  ")
            add(f"**Confidence:** {rec.confidence:.0%}  ")
            add(f"**Reason:** {rec.reason}  ")
            add(f"**Evidence:** {rec.evidence}  ")
            add(f"**Suggested action:** {rec.suggested_action}  ")
            if rec.affected:
                add(f"**Affected:** `{'`, `'.join(rec.affected[:5])}`")
            add("")
    else:
        add("## Recommendations")
        add("")
        add("No recommendations — project appears clean.")
        add("")

    # Quick wins
    if report.quick_wins:
        add("## Quick Wins")
        add("")
        for rec in report.quick_wins:
            add(f"- **{rec.title}** — {rec.suggested_action}")
        add("")

    # Risk zones
    if report.risk_zones:
        add("## Do-Not-Touch-Yet Risk Zones")
        add("")
        for rec in report.risk_zones:
            add(f"- **{rec.title}** — {rec.reason}")
        add("")

    # Deep refactor candidates
    if report.deep_refactor_candidates:
        add("## Deep Refactor Candidates")
        add("")
        for rec in report.deep_refactor_candidates:
            add(f"- **{rec.title}** ({rec.category}) — {rec.reason}")
        add("")

    # Warnings
    if report.warnings:
        add("## Warnings")
        add("")
        for w in report.warnings:
            add(f"- {w}")
        add("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _arch_label(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= 75:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# Recommendation builders
# ---------------------------------------------------------------------------

def _vagrant_recommendations(drift_flags: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for cand in drift_flags.get("vagrant_candidates", []):
        node_id = cand.get("node_id", "?")
        name    = cand.get("name", node_id)
        kind    = cand.get("kind", "component")
        conf    = float(cand.get("confidence", 0.5))
        reason  = cand.get("reason", "node present in committed model but absent from planned model")

        priority = 1 if conf >= 0.75 else 2
        # High-confidence vagrant in a known path → high risk zone (complex/unknown)
        # Low-confidence → could be a new intentional addition → quick win to categorise
        risk_zone  = conf >= 0.75
        quick_win  = conf < 0.50

        recs.append(Recommendation(
            priority=priority,
            category="vagrant",
            title=f"Vagrant node: {name} ({kind})",
            reason=f"{reason} — the planned architecture does not acknowledge this node.",
            evidence=f"committed model contains node '{node_id}'; planned model does not. "
                     f"Detection confidence: {conf:.0%}.",
            confidence=conf,
            suggested_action=(
                "Add this node to the planned model (genesis model add) "
                "or mark it as intentionally external/legacy."
            ),
            affected=[node_id],
            risk_zone=risk_zone,
            quick_win=quick_win,
        ))
    return recs


def _stale_recommendations(drift_flags: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for cand in drift_flags.get("stale_candidates", []):
        node_id = cand.get("node_id", "?")
        resp_id = cand.get("responsibility_id", "?")
        stmt    = cand.get("statement", "unknown responsibility")
        conf    = float(cand.get("confidence", 0.5))
        reason  = cand.get("reason", "responsibility not backed by any code symbol")

        priority  = 2 if conf >= 0.70 else 6
        risk_zone = conf >= 0.80
        quick_win = conf < 0.50

        recs.append(Recommendation(
            priority=priority,
            category="stale",
            title=f"Stale responsibility on {node_id}: \"{_truncate(stmt, 60)}\"",
            reason=f"{reason} — planned intent has no matching source anchor.",
            evidence=f"responsibility '{resp_id}' on node '{node_id}' "
                     f"absent from committed model and source_map. "
                     f"Detection confidence: {conf:.0%}.",
            confidence=conf,
            suggested_action=(
                "Review whether this responsibility is still needed. "
                "If so, implement it; if not, remove it from the planned model."
            ),
            affected=[node_id, resp_id],
            risk_zone=risk_zone,
            quick_win=quick_win,
        ))
    return recs


def _antipattern_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]:
    """Build recommendations from anti_patterns key if present in scan."""
    recs: list[Recommendation] = []
    patterns = scan.get("anti_patterns", [])
    if not isinstance(patterns, list):
        return recs
    for ap in patterns:
        kind     = ap.get("kind", "unknown")
        file_    = ap.get("file", "?")
        conf     = float(ap.get("confidence", 0.6))
        severity = ap.get("severity", "medium")
        basis    = ap.get("basis", "static analysis")

        priority = 3
        risk_zone = severity in ("critical", "high") and conf >= 0.70
        quick_win = severity == "low"

        recs.append(Recommendation(
            priority=priority,
            category="anti-pattern",
            title=f"Anti-pattern [{kind}] in {file_}",
            reason=f"Static analysis detected a {kind} pattern ({severity} severity).",
            evidence=f"{basis}. Confidence: {conf:.0%}.",
            confidence=conf,
            suggested_action=_antipattern_action(kind),
            affected=[file_],
            risk_zone=risk_zone,
            quick_win=quick_win,
        ))
    return recs


def _antipattern_action(kind: str) -> str:
    actions = {
        "god-class":          "Split into smaller, focused modules.",
        "hub-file":           "Reduce fan-in by introducing intermediary abstractions.",
        "circular-dep":       "Break the cycle by extracting a shared dependency.",
        "dead-code":          "Delete or archive the file after confirming it is unused.",
        "feature-envy":       "Move the functionality to the module it depends on most.",
        "leaky-abstraction":  "Enforce layer boundaries; hide implementation details.",
        "shotgun-surgery":    "Consolidate scattered change points into one place.",
    }
    return actions.get(kind, "Review and refactor to eliminate the pattern.")


def _coverage_recommendations(source_anchors: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    total   = int(source_anchors.get("total_responsibilities", 0))
    unanchr = int(source_anchors.get("unanchored_count", 0))
    if total == 0 or unanchr == 0:
        return recs

    ratio = unanchr / total
    conf  = 0.65  # structural observation, moderate confidence
    priority = 4
    quick_win = ratio < 0.25  # small gap → easy to close

    recs.append(Recommendation(
        priority=priority,
        category="coverage",
        title=f"Unanchored responsibilities: {unanchr}/{total} ({ratio:.0%})",
        reason=(
            "A significant fraction of planned responsibilities have no source anchor. "
            "This means planned intent may not be implemented — or not yet indexed."
        ),
        evidence=(
            f"{unanchr} of {total} responsibilities lack a source_map entry. "
            f"Coverage: {1 - ratio:.0%}."
        ),
        confidence=conf,
        suggested_action=(
            "Run `genesis anchor` to re-index, then review remaining gaps. "
            "Implement or remove unanchored responsibilities."
        ),
        affected=[],
        risk_zone=ratio > 0.75,
        quick_win=quick_win,
    ))
    return recs


def _churn_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    hotspots: dict = scan.get("fix_commit_hotspots", {})
    if not isinstance(hotspots, dict):
        return recs

    for file_, count in sorted(hotspots.items(), key=lambda x: -x[1]):
        if count < 3:
            break
        conf = min(0.85, 0.50 + count * 0.05)
        recs.append(Recommendation(
            priority=5,
            category="churn",
            title=f"High churn file: {file_} ({count} fix commits)",
            reason=f"This file has been touched by {count} fix-related commits — a fragility signal.",
            evidence=f"git log --grep=fix shows {count} fix commits touching {file_!r}.",
            confidence=conf,
            suggested_action=(
                "Investigate root cause of repeated fixes. "
                "Consider adding tests, refactoring, or splitting the file."
            ),
            affected=[file_],
            risk_zone=count >= 8,
            quick_win=False,
        ))
    return recs


def _dead_file_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    dead: list = scan.get("dead_file_candidates", [])
    if not isinstance(dead, list):
        return recs
    for f in dead[:10]:
        recs.append(Recommendation(
            priority=7,
            category="dead-file",
            title=f"Possibly unused file: {f}",
            reason="No import/require statement referencing this file was found.",
            evidence=f"Heuristic scan found no references to '{f}' in other source files.",
            confidence=0.45,  # heuristic, false positives possible
            suggested_action=(
                "Verify manually. If truly unused, archive or delete. "
                "Beware: dynamic imports and reflection can fool the heuristic."
            ),
            affected=[f],
            risk_zone=False,
            quick_win=True,
        ))
    return recs


def _version_drift_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if not scan.get("version_drift", False):
        return recs
    sources: dict = scan.get("version_sources", {})
    versions = ", ".join(f"{k}={v}" for k, v in sorted(sources.items()))
    recs.append(Recommendation(
        priority=8,
        category="version-drift",
        title="Version mismatch across manifest files",
        reason="Different version strings found across project manifest files.",
        evidence=f"Found: {versions}.",
        confidence=0.90,
        suggested_action="Align versions across all manifests and add a release script to keep them in sync.",
        affected=list(sources.keys()),
        risk_zone=False,
        quick_win=True,
    ))
    return recs


def _missing_plan_recommendations(scan: dict, warnings: list[str]) -> list[Recommendation]:
    """Emit one recommendation when planned.json is absent (model_sync.diverged=False + no planned)."""
    recs: list[Recommendation] = []
    model_sync: dict = scan.get("model_sync") or {}
    if not isinstance(model_sync, dict):
        return recs
    # planned.json is absent iff diverged=False AND synced=True (or synced=False with no file)
    # But the clearest signal: node_count > 0 and model_sync has no explicit planned model flag.
    # We detect it via drift_flags basis string containing "no planned model"
    drift_flags: dict = scan.get("drift_flags") or {}
    if not isinstance(drift_flags, dict):
        return recs
    basis = str(drift_flags.get("basis", ""))
    # drift_detector emits "planned.json absent" when planned_was_missing=True
    has_no_planned = (
        "planned.json absent" in basis.lower()
        or "no planned model" in basis.lower()
        or "planned_was_missing" in basis.lower()
    )
    # _CONF_NO_PLANNED constant in drift_detector is 0.35; use < 0.45 as a wider guard
    conf = float(drift_flags.get("confidence", 1.0))
    if not has_no_planned and conf >= 0.45:
        return recs

    node_count = int(model_sync.get("node_count", 0))
    if node_count == 0 and not has_no_planned:
        return recs  # truly empty project — no recommendation needed

    recs.append(Recommendation(
        priority=4,
        category="no-planned-model",
        title="No planned architecture model found",
        reason=(
            "The project has no planned.json file. Genesis cannot compute drift "
            "or validate planned intent against the committed model."
        ),
        evidence=(
            f"drift_detector basis: \"{_truncate(basis, 120)}\". "
            f"Committed model has {node_count} node(s); planned model is absent."
        ),
        confidence=0.90,
        suggested_action=(
            "Run `genesis plan init` to create a planned model, "
            "then add planned responsibilities for each node."
        ),
        affected=[],
        risk_zone=False,
        quick_win=True,
    ))
    return recs


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


# ---------------------------------------------------------------------------
# Recommendation sorting
# ---------------------------------------------------------------------------

def _sort_recommendations(recs: list[Recommendation]) -> list[Recommendation]:
    """
    Sort by (priority ASC, confidence DESC, title ASC) for determinism.
    """
    return sorted(recs, key=lambda r: (r.priority, -r.confidence, r.title))


# ---------------------------------------------------------------------------
# Executive summary builder
# ---------------------------------------------------------------------------

def _build_executive_summary(
    project_risk: str,
    arch_health: ArchitectureHealth,
    drift_summary: DriftSummary,
    recs: list[Recommendation],
) -> str:
    critical = sum(1 for r in recs if r.priority == 1)
    high     = sum(1 for r in recs if r.priority in (2, 3))
    quick    = sum(1 for r in recs if r.quick_win)

    risk_phrase = {
        "none":     "No significant issues were detected.",
        "low":      "The project is broadly healthy with minor signals worth addressing.",
        "medium":   "Moderate drift and structural issues require attention.",
        "high":     "Significant drift and architectural issues are present.",
        "critical": "The project has critical drift and requires immediate architectural review.",
    }.get(project_risk, "Risk level undetermined.")

    arch_phrase = ""
    if arch_health.score is not None:
        arch_phrase = f" Architecture score is {arch_health.score:.0f}/100 ({arch_health.label})."

    drift_phrase = (
        f" Drift score is {drift_summary.overall_score:.0f}/100"
        f" ({drift_summary.vagrant_count} vagrant nodes,"
        f" {drift_summary.stale_count} stale responsibilities)."
    )

    action_phrase = ""
    if critical > 0:
        action_phrase = f" {critical} critical recommendation{'s' if critical > 1 else ''} require immediate action."
    elif high > 0:
        action_phrase = f" {high} high-priority recommendation{'s' if high > 1 else ''} should be addressed soon."
    if quick > 0:
        action_phrase += f" {quick} quick win{'s' if quick > 1 else ''} available."

    return risk_phrase + arch_phrase + drift_phrase + action_phrase


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(scan_output: dict) -> RecoveryReport:
    """
    Generate a RecoveryReport from the output of recovery_scan.scan().

    Parameters
    ----------
    scan_output : dict
        The dict returned by `scan(project_dir)`. Missing keys are tolerated.

    Returns
    -------
    RecoveryReport
        Always returns a valid report. Never raises.
    """
    warnings_out: list[str] = []
    evidence_basis: dict[str, str] = {}

    # --- Track which keys are present / missing ---
    all_expected = [
        "fix_commit_hotspots", "external_url_count", "version_sources",
        "doc_version", "version_drift", "dead_file_candidates",
        "model_sync", "model_diff", "drift_flags", "drift_score",
        "source_anchors", "anchor_persist_result",
        "architecture_score", "architecture_profile", "anti_patterns",
    ]
    present  = [k for k in all_expected if k in scan_output]
    missing  = [k for k in all_expected if k not in scan_output]
    if missing:
        warnings_out.append(f"Missing scan keys (degraded mode): {', '.join(missing)}")

    # --- Architecture health ---
    arch_score: float | None = None
    try:
        raw_score = scan_output.get("architecture_score")
        if raw_score is not None:
            arch_score = float(raw_score)
    except (TypeError, ValueError):
        warnings_out.append("architecture_score present but not a number; skipping.")

    anti_patterns: list[dict] = []
    try:
        ap_raw = scan_output.get("anti_patterns", [])
        if isinstance(ap_raw, list):
            anti_patterns = ap_raw
    except Exception:  # noqa: BLE001
        warnings_out.append("anti_patterns could not be read; skipping.")

    top_ap_names = sorted({ap.get("kind", "?") for ap in anti_patterns[:10]})
    hotspot_files: list[str] = list(
        (scan_output.get("fix_commit_hotspots") or {}).keys()
    )[:5]

    arch_health = ArchitectureHealth(
        score=arch_score,
        label=_arch_label(arch_score),
        anti_pattern_count=len(anti_patterns),
        top_anti_patterns=top_ap_names,
        hotspot_files=hotspot_files,
        basis=(
            f"architecture_score={'available' if arch_score is not None else 'unavailable'}; "
            f"{len(anti_patterns)} anti-pattern(s) detected; "
            f"{len(hotspot_files)} churn hotspot(s) found."
        ),
    )

    if arch_score is not None:
        evidence_basis["architecture_score"] = f"architecture_scorer returned {arch_score:.1f}/100"
    if anti_patterns:
        evidence_basis["anti_patterns"] = f"{len(anti_patterns)} pattern(s) detected by static analysis"

    # --- Drift summary ---
    _ds_raw = scan_output.get("drift_score", {})
    drift_score_raw: dict = _ds_raw if isinstance(_ds_raw, dict) else {}
    _df_raw = scan_output.get("drift_flags", {})
    drift_flags_raw: dict = _df_raw if isinstance(_df_raw, dict) else {}
    _sa_raw = scan_output.get("source_anchors", {})
    source_anchors_raw: dict = _sa_raw if isinstance(_sa_raw, dict) else {}

    ds_overall    = float(drift_score_raw.get("overall_score", 0.0))
    ds_risk       = str(drift_score_raw.get("risk_level", "none"))
    vagrant_count = len(drift_flags_raw.get("vagrant_candidates", []))
    stale_count   = len(drift_flags_raw.get("stale_candidates", []))
    unanchored    = int(source_anchors_raw.get("unanchored_count", 0))
    top_risk_nodes: list[str] = drift_score_raw.get("top_risk_nodes", []) or []

    drift_summary = DriftSummary(
        overall_score=ds_overall,
        risk_level=ds_risk,
        vagrant_count=vagrant_count,
        stale_count=stale_count,
        unanchored_count=unanchored,
        top_risk_nodes=top_risk_nodes,
        basis=str(drift_score_raw.get("basis", "drift scoring unavailable")),
    )

    evidence_basis["drift_score"]  = f"drift_scorer returned {ds_overall:.1f}/100 ({ds_risk})"
    evidence_basis["drift_flags"]  = f"{vagrant_count} vagrant, {stale_count} stale candidates"
    evidence_basis["source_anchors"] = f"{unanchored} unanchored responsibilities"

    # --- Build recommendations ---
    all_recs: list[Recommendation] = []

    try:
        all_recs.extend(_vagrant_recommendations(drift_flags_raw, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"vagrant recommendations skipped: {exc}")

    try:
        all_recs.extend(_stale_recommendations(drift_flags_raw, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"stale recommendations skipped: {exc}")

    try:
        all_recs.extend(_antipattern_recommendations(scan_output, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"anti-pattern recommendations skipped: {exc}")

    try:
        all_recs.extend(_coverage_recommendations(source_anchors_raw, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"coverage recommendations skipped: {exc}")

    try:
        all_recs.extend(_churn_recommendations(scan_output, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"churn recommendations skipped: {exc}")

    try:
        all_recs.extend(_dead_file_recommendations(scan_output, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"dead-file recommendations skipped: {exc}")

    try:
        all_recs.extend(_version_drift_recommendations(scan_output, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"version-drift recommendations skipped: {exc}")

    try:
        all_recs.extend(_missing_plan_recommendations(scan_output, warnings_out))
    except Exception as exc:  # noqa: BLE001
        warnings_out.append(f"missing-plan recommendations skipped: {exc}")

    recs_sorted = _sort_recommendations(all_recs)

    # --- Project risk level ---
    project_risk = _max_risk(
        ds_risk,
        "high"    if len(all_recs) > 0 and all_recs[0].priority == 1 else "none",
        "medium"  if arch_score is not None and arch_score < 50 else "none",
        "low"     if len(anti_patterns) > 0 else "none",
    )

    # --- Executive summary ---
    exec_summary = _build_executive_summary(
        project_risk, arch_health, drift_summary, recs_sorted
    )

    # --- Propagate scan warnings ---
    for src in (drift_score_raw.get("warnings") or [], drift_flags_raw.get("warnings") or []):
        for w in src:
            if w and w not in warnings_out:
                warnings_out.append(w)

    return RecoveryReport(
        executive_summary=exec_summary,
        project_risk_level=project_risk,
        architecture_health=arch_health,
        drift_summary=drift_summary,
        recommendations=recs_sorted,
        evidence_basis=evidence_basis,
        warnings=warnings_out,
        metadata=ReportMetadata(
            scan_keys_present=present,
            scan_keys_missing=missing,
        ),
    )


# ---------------------------------------------------------------------------
# Disk-backed entry point
# ---------------------------------------------------------------------------

def generate_report_for_project(project_dir: "Path") -> RecoveryReport:  # noqa: F821
    """
    Run recovery_scan.scan() on *project_dir* and return a RecoveryReport.

    Never raises. All errors surface as warnings inside the returned report.
    """
    from pathlib import Path as _Path
    from genesis_architect.pro.recovery_scan import scan

    project_dir = _Path(project_dir)
    try:
        scan_output = scan(project_dir)
    except Exception as exc:  # noqa: BLE001
        scan_output = {}
        report = generate_report(scan_output)
        report.warnings.insert(0, f"recovery_scan.scan() failed: {exc}")
        return report

    return generate_report(scan_output)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _h(text: str) -> str:
    """HTML-escape user/project-controlled text. Covers all HTML injection vectors."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _risk_color(level: str) -> str:
    return {
        "none":     "#22c55e",
        "low":      "#84cc16",
        "medium":   "#f59e0b",
        "high":     "#ef4444",
        "critical": "#7c3aed",
    }.get(level, "#6b7280")


def _priority_badge(priority: int) -> str:
    label = _PRIORITY_LABELS.get(priority, "info").upper()
    colors = {
        "CRITICAL": ("#fef2f2", "#b91c1c"),
        "HIGH":     ("#fff7ed", "#c2410c"),
        "MEDIUM":   ("#fffbeb", "#b45309"),
        "LOW":      ("#f0fdf4", "#166534"),
        "INFO":     ("#f0f9ff", "#0369a1"),
    }
    bg, fg = colors.get(label, ("#f9fafb", "#374151"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;'
        f'font-size:0.72rem;font-weight:700;letter-spacing:.05em">{_h(label)}</span>'
    )


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;line-height:1.6;font-size:15px}
.wrap{max-width:960px;margin:0 auto;padding:32px 24px}
h1{font-size:1.75rem;font-weight:800;margin-bottom:4px}
h2{font-size:1.15rem;font-weight:700;margin:28px 0 12px;padding-bottom:6px;
  border-bottom:2px solid #e2e8f0;color:#0f172a}
h3{font-size:.95rem;font-weight:600;margin:16px 0 6px;color:#1e293b}
p{margin-bottom:.75rem;color:#334155}
ul{padding-left:1.25rem;margin-bottom:.75rem}
li{margin-bottom:.25rem;color:#334155}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.header{background:#0f172a;color:#fff;padding:28px 24px;border-radius:10px;
  margin-bottom:24px}
.header h1{color:#fff}
.header p{color:#94a3b8;margin:0}
.risk-badge{display:inline-flex;align-items:center;gap:6px;
  padding:4px 14px;border-radius:20px;font-weight:700;font-size:.85rem;
  margin-top:10px;color:#fff}
.kv{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px}
.kv-item{background:#f1f5f9;border-radius:6px;padding:8px 14px;min-width:120px}
.kv-item .label{font-size:.7rem;font-weight:600;color:#64748b;text-transform:uppercase;
  letter-spacing:.05em}
.kv-item .value{font-size:1.1rem;font-weight:700;color:#0f172a}
.rec{border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px;margin-bottom:10px;
  background:#fff;border-left:4px solid #cbd5e1}
.rec.critical{border-left-color:#7c3aed}
.rec.high{border-left-color:#ef4444}
.rec.medium{border-left-color:#f59e0b}
.rec.low{border-left-color:#84cc16}
.rec.info{border-left-color:#0ea5e9}
.rec-title{font-weight:600;font-size:.95rem;margin-bottom:6px;color:#0f172a;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.rec-meta{font-size:.82rem;color:#64748b;margin-bottom:6px}
.rec-action{background:#f0f9ff;border-radius:6px;padding:8px 12px;
  font-size:.85rem;color:#0369a1;margin-top:8px}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;
  font-weight:600;margin-left:4px}
.tag-quick{background:#dcfce7;color:#166534}
.tag-risk{background:#fef2f2;color:#b91c1c}
.conf-bar-wrap{height:6px;background:#e2e8f0;border-radius:3px;
  width:80px;display:inline-block;vertical-align:middle;margin-left:6px}
.conf-bar{height:6px;border-radius:3px;background:#3b82f6}
.section-empty{color:#94a3b8;font-style:italic;font-size:.9rem;padding:8px 0}
.warn-item{background:#fffbeb;border:1px solid #fde68a;border-radius:6px;
  padding:8px 12px;margin-bottom:6px;font-size:.85rem;color:#92400e}
.eb-item{display:flex;gap:12px;padding:6px 0;border-bottom:1px solid #f1f5f9;
  font-size:.85rem}
.eb-key{font-weight:600;color:#0f172a;min-width:160px;flex-shrink:0}
.eb-val{color:#475569}
.payload{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:16px;
  font-family:'Courier New',monospace;font-size:.75rem;overflow-x:auto;
  white-space:pre;max-height:400px;line-height:1.4;margin-top:8px}
.meta-grid{display:flex;flex-wrap:wrap;gap:8px;font-size:.82rem}
.meta-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
  padding:6px 10px;color:#475569}
.meta-item b{color:#0f172a}
details summary{cursor:pointer;font-weight:600;font-size:.9rem;color:#0369a1;
  padding:8px 0;user-select:none}
details summary:hover{color:#0284c7}
"""


def _rec_cards(recs: list[Recommendation]) -> str:
    if not recs:
        return '<p class="section-empty">None identified.</p>'
    parts: list[str] = []
    for rec in recs:
        level = _PRIORITY_LABELS.get(rec.priority, "info")
        tags = ""
        if rec.quick_win:
            tags += '<span class="tag tag-quick">&#9889; Quick Win</span>'
        if rec.risk_zone:
            tags += '<span class="tag tag-risk">&#128679; Risk Zone</span>'
        conf_pct = int(rec.confidence * 100)
        conf_bar = (
            f'<span class="conf-bar-wrap"><span class="conf-bar" '
            f'style="width:{conf_pct}%"></span></span>'
        )
        affected_html = ""
        if rec.affected:
            items = "".join(f"<code>{_h(a)}</code> " for a in rec.affected[:5])
            affected_html = f'<div style="margin-top:6px;font-size:.82rem;color:#64748b">Affected: {items}</div>'
        parts.append(
            f'<div class="rec {_h(level)}">'
            f'<div class="rec-title">{_priority_badge(rec.priority)} {_h(rec.title)}{tags}</div>'
            f'<div class="rec-meta">'
            f'Confidence: {conf_pct}%{conf_bar} &nbsp;|&nbsp; Category: {_h(rec.category)}'
            f'</div>'
            f'<p style="font-size:.88rem;margin-bottom:4px"><b>Reason:</b> {_h(rec.reason)}</p>'
            f'<p style="font-size:.88rem;margin-bottom:4px"><b>Evidence:</b> {_h(rec.evidence)}</p>'
            f'<div class="rec-action">&#128161; {_h(rec.suggested_action)}</div>'
            f'{affected_html}'
            f'</div>'
        )
    return "\n".join(parts)


def _render_html(report: RecoveryReport) -> str:
    """
    Render a RecoveryReport as a self-contained HTML document.

    - All user/project-controlled strings are HTML-escaped via _h().
    - A machine-readable JSON payload is embedded in a <script> tag.
    - No external dependencies. No network requests. No cookies.
    - Output is deterministic for identical inputs.
    """
    risk_color = _risk_color(report.project_risk_level)

    # ---- Header ----
    header = (
        f'<div class="header">'
        f'<h1>Genesis Recovery Report</h1>'
        f'<p>{_h(report.metadata.generator)} &mdash; schema v{_h(report.metadata.schema_version)}</p>'
        f'<div class="risk-badge" style="background:{risk_color}">'
        f'Project Risk: {_h(report.project_risk_level.upper())}'
        f'</div>'
        f'</div>'
    )

    # ---- Executive summary ----
    exec_section = (
        f'<div class="card"><h2>Executive Summary</h2>'
        f'<p>{_h(report.executive_summary)}</p>'
        f'</div>'
    )

    # ---- Architecture health ----
    ah = report.architecture_health
    score_str = f"{ah.score:.0f} / 100" if ah.score is not None else "unavailable"
    ap_html = (
        f'<li>{_h(k)}</li>' for k in ah.top_anti_patterns
    ) if ah.top_anti_patterns else ()
    hs_html = (
        f'<li><code>{_h(f)}</code></li>' for f in ah.hotspot_files
    ) if ah.hotspot_files else ()

    arch_section = (
        f'<div class="card"><h2>Architecture Health</h2>'
        f'<div class="kv">'
        f'<div class="kv-item"><div class="label">Score</div>'
        f'<div class="value">{_h(score_str)}</div></div>'
        f'<div class="kv-item"><div class="label">Rating</div>'
        f'<div class="value">{_h(ah.label)}</div></div>'
        f'<div class="kv-item"><div class="label">Anti-patterns</div>'
        f'<div class="value">{ah.anti_pattern_count}</div></div>'
        f'</div>'
        + (f'<h3>Top Anti-patterns</h3><ul>{"".join(ap_html)}</ul>' if ah.top_anti_patterns else "")
        + (f'<h3>Churn Hotspots</h3><ul>{"".join(hs_html)}</ul>' if ah.hotspot_files else "")
        + f'<p style="font-size:.8rem;color:#94a3b8;margin-top:8px">{_h(ah.basis)}</p>'
        f'</div>'
    )

    # ---- Drift summary ----
    ds = report.drift_summary
    top_risk_html = "".join(f'<li><code>{_h(n)}</code></li>' for n in ds.top_risk_nodes)
    drift_section = (
        f'<div class="card"><h2>Drift Summary</h2>'
        f'<div class="kv">'
        f'<div class="kv-item"><div class="label">Drift Score</div>'
        f'<div class="value" style="color:{_risk_color(ds.risk_level)}">'
        f'{ds.overall_score:.1f}</div></div>'
        f'<div class="kv-item"><div class="label">Risk</div>'
        f'<div class="value">{_h(ds.risk_level)}</div></div>'
        f'<div class="kv-item"><div class="label">Vagrant Nodes</div>'
        f'<div class="value">{ds.vagrant_count}</div></div>'
        f'<div class="kv-item"><div class="label">Stale Resps</div>'
        f'<div class="value">{ds.stale_count}</div></div>'
        f'<div class="kv-item"><div class="label">Unanchored</div>'
        f'<div class="value">{ds.unanchored_count}</div></div>'
        f'</div>'
        + (f'<h3>Top Risk Nodes</h3><ul>{top_risk_html}</ul>' if ds.top_risk_nodes else "")
        + f'<p style="font-size:.8rem;color:#94a3b8;margin-top:8px">{_h(ds.basis)}</p>'
        f'</div>'
    )

    # ---- Recommendations ----
    rec_section = (
        '<div class="card"><h2>Recommendations</h2>'
        + _rec_cards(report.recommendations)
        + '</div>'
    )

    # ---- Quick wins ----
    qw_section = (
        '<div class="card"><h2>&#9889; Quick Wins</h2>'
        + _rec_cards(report.quick_wins)
        + '</div>'
    )

    # ---- Deep refactor candidates ----
    dr_section = (
        '<div class="card"><h2>Deep Refactor Candidates</h2>'
        + _rec_cards(report.deep_refactor_candidates)
        + '</div>'
    )

    # ---- Risk zones ----
    rz_section = (
        '<div class="card"><h2>&#128679; Do-Not-Touch Risk Zones</h2>'
        + _rec_cards(report.risk_zones)
        + '</div>'
    )

    # ---- Evidence basis ----
    eb_rows = "".join(
        f'<div class="eb-item"><div class="eb-key">{_h(k)}</div>'
        f'<div class="eb-val">{_h(v)}</div></div>'
        for k, v in sorted(report.evidence_basis.items())
    )
    eb_section = (
        '<div class="card"><h2>Evidence Basis</h2>'
        + (eb_rows if eb_rows else '<p class="section-empty">No evidence recorded.</p>')
        + '</div>'
    )

    # ---- Warnings ----
    warn_html = "".join(
        f'<div class="warn-item">&#9888; {_h(w)}</div>'
        for w in report.warnings
    )
    warn_section = (
        '<div class="card"><h2>Warnings</h2>'
        + (warn_html if warn_html else '<p class="section-empty">No warnings.</p>')
        + '</div>'
    )

    # ---- Metadata ----
    present_html = "".join(
        f'<span class="meta-item"><b>&#10003;</b> {_h(k)}</span>'
        for k in report.metadata.scan_keys_present
    )
    missing_html = "".join(
        f'<span class="meta-item" style="color:#b91c1c"><b>&#10007;</b> {_h(k)}</span>'
        for k in report.metadata.scan_keys_missing
    )
    meta_section = (
        f'<div class="card"><h2>Metadata</h2>'
        f'<p style="font-size:.85rem"><b>Generator:</b> {_h(report.metadata.generator)} &nbsp;|&nbsp; '
        f'<b>Schema:</b> {_h(report.metadata.schema_version)}</p>'
        + (f'<h3>Scan keys present</h3><div class="meta-grid">{present_html}</div>' if present_html else "")
        + (f'<h3>Scan keys missing</h3><div class="meta-grid">{missing_html}</div>' if missing_html else "")
        + '</div>'
    )

    # ---- Embedded JSON payload ----
    json_payload = json.dumps(report.to_dict(), indent=2)
    payload_section = (
        f'<div class="card">'
        f'<details>'
        f'<summary>Machine-readable JSON payload</summary>'
        f'<pre class="payload" id="json-payload">{_h(json_payload)}</pre>'
        f'</details>'
        f'</div>'
    )

    # ---- Assemble document ----
    body = "\n".join([
        header,
        exec_section,
        arch_section,
        drift_section,
        rec_section,
        qw_section,
        dr_section,
        rz_section,
        eb_section,
        warn_section,
        meta_section,
        payload_section,
    ])

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>Genesis Recovery Report &mdash; {_h(report.project_risk_level.upper())} risk</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="wrap">\n'
        f"{body}\n"
        "</div>\n"
        "</body>\n"
        "</html>"
    )
