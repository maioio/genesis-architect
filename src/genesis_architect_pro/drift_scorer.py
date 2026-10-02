"""
drift_scorer.py - Genesis Architect PRO

Read-only, deterministic drift scoring on top of DriftFlags and AnchorReport.

No writes. No mutations. No side effects.

Scoring model
-------------
The drift score is a penalty accumulator in the range [0.0, 100.0].
0   = no drift detected.
100 = maximum drift (every signal firing at max weight).

Penalty sources (each capped individually before summing):
  V  — vagrant penalty
       +vagrantPenaltyPerNode × confidence_of_candidate
       Default vagrantPenaltyPerNode = 12.0
       Cap: 40.0

  S  — stale penalty
       +stalePenaltyPerResp × confidence_of_candidate
       Default stalePenaltyPerResp = 8.0
       Cap: 35.0

  C  — coverage penalty (unanchored responsibilities)
       unanchored_ratio × coveragePenaltyMax
       Default coveragePenaltyMax = 20.0
       Only applied when total_responsibilities > 0.

  T  — temporal risk penalty (optional, from WLS forecast)
       Only applied when a DecayForecast is provided AND slope is negative
       AND is_significant.
       penalty = temporalPenaltyMax × clamp(1 - predicted_score/100, 0, 1)
       Default temporalPenaltyMax = 15.0

Raw score = clamp(V + S + C + T, 0, 100)

Per-node score
--------------
Each node receives an individual score based on:
  - Whether it appears in vagrant_candidates (weight: vagrantPenaltyPerNode × conf)
  - How many of its stale responsibilities it contributes (weight: stalePenaltyPerResp × conf)
  - Its source_map coverage for its own responsibilities

Risk levels
-----------
  score == 0         → "none"
  0 < score <= 20    → "low"
  20 < score <= 50   → "medium"
  50 < score <= 75   → "high"
  score > 75         → "critical"

Confidence in the score itself
-------------------------------
Mirrors the detection confidence:
  >= 0.75  high   — DriftFlags.confidence >= 0.75 and AnchorReport provided
  >= 0.50  medium — either DriftFlags.confidence < 0.75 or no AnchorReport
  <  0.50  low    — planned model missing or both signals absent

Determinism guarantee
---------------------
Results are sorted alphabetically by node_id wherever ordering matters.
All arithmetic uses Python float (IEEE 754). Given identical inputs, output
is bitwise-identical across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from genesis_architect_pro.decay_regressor import DecayForecast


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class DriftScorerConfig:
    vagrant_penalty_per_node: float = 12.0
    vagrant_penalty_cap: float = 40.0
    stale_penalty_per_resp: float = 8.0
    stale_penalty_cap: float = 35.0
    coverage_penalty_max: float = 20.0
    temporal_penalty_max: float = 15.0


_DEFAULT_CONFIG = DriftScorerConfig()

# Risk level thresholds (upper-bound, inclusive)
_RISK_LEVELS: list[tuple[float, str]] = [
    (0.0,  "none"),
    (20.0, "low"),
    (50.0, "medium"),
    (75.0, "high"),
]
_RISK_CRITICAL = "critical"


def _risk_level(score: float) -> str:
    for threshold, label in _RISK_LEVELS:
        if score <= threshold:
            return label
    return _RISK_CRITICAL


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NodeDriftScore:
    """Drift score for a single architecture node."""
    node_id: str
    name: str
    kind: str
    score: float                      # 0.0–100.0
    risk_level: str                   # none/low/medium/high/critical
    vagrant: bool                     # is this node a vagrant candidate?
    stale_responsibility_count: int   # number of stale responsibilities on this node
    source_map_coverage: float        # fraction of responsibilities with source_map entries (0–1)
    basis: str

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "kind": self.kind,
            "score": round(self.score, 2),
            "risk_level": self.risk_level,
            "vagrant": self.vagrant,
            "stale_responsibility_count": self.stale_responsibility_count,
            "source_map_coverage": round(self.source_map_coverage, 3),
            "basis": self.basis,
        }


@dataclass
class DriftScore:
    """Full drift score result for a project."""
    overall_score: float              # 0.0–100.0
    risk_level: str                   # none/low/medium/high/critical
    confidence: float                 # 0.0–1.0 (confidence in the score itself)
    basis: str                        # human-readable explanation
    per_node_scores: list[NodeDriftScore] = field(default_factory=list)
    top_risk_nodes: list[str] = field(default_factory=list)   # node_ids, highest score first
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 2),
            "risk_level": self.risk_level,
            "confidence": round(self.confidence, 3),
            "basis": self.basis,
            "per_node_scores": [n.to_dict() for n in self.per_node_scores],
            "top_risk_nodes": self.top_risk_nodes,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Pure scoring function
# ---------------------------------------------------------------------------

def score_drift(
    flags: "DriftFlags",          # noqa: F821
    anchor_report: "AnchorReport | None" = None,  # noqa: F821
    forecast: "DecayForecast | None" = None,       # noqa: F821
    *,
    config: DriftScorerConfig = _DEFAULT_CONFIG,
) -> DriftScore:
    """
    Compute a DriftScore from drift flags, an optional anchor report, and an
    optional WLS decay forecast.

    Parameters
    ----------
    flags : DriftFlags
        Output of detect_drift() or compute_drift_flags().
    anchor_report : AnchorReport | None
        Output of anchor_responsibilities() or anchor_from_store().
        When None, coverage_penalty is applied at full weight and confidence
        is lowered.
    forecast : DecayForecast | None
        Output of DecayRegressor.forecast(). When None, temporal penalty is 0.
    config : DriftScorerConfig
        Tunable weights. Defaults are conservative.

    Returns
    -------
    DriftScore
        All fields populated. Never raises.
    """
    warnings_out: list[str] = list(flags.warnings)

    # ---- Confidence in the score ----
    detection_conf = flags.confidence
    has_anchors = anchor_report is not None
    if detection_conf >= 0.75 and has_anchors:
        score_confidence = 0.80
        conf_basis = "high — both models loaded and source anchors available"
    elif detection_conf >= 0.50 or has_anchors:
        score_confidence = 0.55
        conf_basis = "medium — partial signal (one of: source anchors, planned model)"
    else:
        score_confidence = 0.30
        conf_basis = "low — planned model absent or source anchors unavailable"

    # ---- Build per-node lookup structures ----
    # Nodes referenced anywhere: committed nodes (from vagrant candidates + stale candidates)
    all_node_ids: set[str] = set()
    for v in flags.vagrant_candidates:
        all_node_ids.add(v.node_id)
    for s in flags.stale_candidates:
        all_node_ids.add(s.node_id)

    # Index vagrant candidates by node_id
    vagrant_index: dict[str, "VagrantCandidate"] = {  # noqa: F821
        v.node_id: v for v in flags.vagrant_candidates
    }
    # Index stale candidates: node_id → list[StaleCandidate]
    stale_index: dict[str, list] = {}
    for s in flags.stale_candidates:
        stale_index.setdefault(s.node_id, []).append(s)

    # Anchor coverage index: resp_id → bool (anchored)
    anchored_resp_ids: set[str] = set()
    all_resp_ids_in_report: set[str] = set()
    if anchor_report is not None:
        for rid, res in anchor_report.anchors_by_responsibility.items():
            all_resp_ids_in_report.add(rid)
            if res.is_anchored:
                anchored_resp_ids.add(rid)

    # ---- Per-node scoring ----
    per_node: list[NodeDriftScore] = []

    for node_id in sorted(all_node_ids):
        vagrant_cand = vagrant_index.get(node_id)
        stale_resps = stale_index.get(node_id, [])

        # Vagrant signal
        vagrant_penalty = 0.0
        is_vagrant = vagrant_cand is not None
        if is_vagrant:
            vagrant_penalty = config.vagrant_penalty_per_node * vagrant_cand.confidence

        # Stale signal
        stale_penalty = sum(
            config.stale_penalty_per_resp * s.confidence for s in stale_resps
        )
        stale_count = len(stale_resps)

        # Per-node source_map coverage
        # Stale responsibilities on this node that have no anchor
        node_resp_ids = {s.responsibility_id for s in stale_resps}
        # Also include anchored ones we know about from the report
        if anchor_report is not None:
            for rid, res in anchor_report.anchors_by_responsibility.items():
                if res.node_id == node_id:
                    node_resp_ids.add(rid)

        if node_resp_ids:
            node_anchored = sum(1 for rid in node_resp_ids if rid in anchored_resp_ids)
            node_coverage = node_anchored / len(node_resp_ids)
        else:
            node_coverage = 1.0  # no responsibilities → no gap

        node_raw = _clamp(vagrant_penalty + stale_penalty)
        node_risk = _risk_level(node_raw)

        # Build basis string
        parts: list[str] = []
        if is_vagrant:
            parts.append(f"vagrant (conf={vagrant_cand.confidence:.2f})")
        if stale_count:
            parts.append(f"{stale_count} stale resp")
        if node_coverage < 1.0:
            parts.append(f"coverage={node_coverage:.0%}")
        node_basis = "; ".join(parts) if parts else "no drift signals"

        # Determine a representative name/kind from whichever candidate exists
        if vagrant_cand:
            name = vagrant_cand.name
            kind = vagrant_cand.kind
        elif stale_resps:
            name = node_id
            kind = "unknown"
        else:
            name = node_id
            kind = "unknown"

        per_node.append(NodeDriftScore(
            node_id=node_id,
            name=name,
            kind=kind,
            score=node_raw,
            risk_level=node_risk,
            vagrant=is_vagrant,
            stale_responsibility_count=stale_count,
            source_map_coverage=node_coverage,
            basis=node_basis,
        ))

    # Sort per_node by score DESC (deterministic secondary: node_id ASC)
    per_node.sort(key=lambda n: (-n.score, n.node_id))

    # ---- Global penalties ----

    # V — vagrant
    vagrant_raw = sum(
        config.vagrant_penalty_per_node * v.confidence
        for v in flags.vagrant_candidates
    )
    vagrant_pen = _clamp(vagrant_raw, 0, config.vagrant_penalty_cap)

    # S — stale
    stale_raw = sum(
        config.stale_penalty_per_resp * s.confidence
        for s in flags.stale_candidates
    )
    stale_pen = _clamp(stale_raw, 0, config.stale_penalty_cap)

    # C — coverage
    if anchor_report is not None and anchor_report.total_responsibilities > 0:
        unanchored_ratio = anchor_report.unanchored_count / anchor_report.total_responsibilities
        coverage_pen = unanchored_ratio * config.coverage_penalty_max
    elif anchor_report is not None and anchor_report.total_responsibilities == 0:
        coverage_pen = 0.0
    else:
        # No anchor report → treat as fully unanchored (penalise, lower confidence)
        coverage_pen = config.coverage_penalty_max
        warnings_out.append(
            "drift_scorer: no AnchorReport provided; coverage penalty applied at maximum"
        )

    # T — temporal
    temporal_pen = 0.0
    if forecast is not None:
        if forecast.regression.slope < 0 and forecast.regression.is_significant:
            risk_fraction = _clamp(1.0 - forecast.predicted_score / 100.0, 0.0, 1.0)
            temporal_pen = config.temporal_penalty_max * risk_fraction

    overall_raw = _clamp(vagrant_pen + stale_pen + coverage_pen + temporal_pen)
    overall_risk = _risk_level(overall_raw)

    # ---- Top risk nodes ----
    top_risk = [n.node_id for n in per_node if n.score > 0][:5]  # top 5, already sorted

    # ---- Overall basis ----
    penalty_parts: list[str] = []
    if vagrant_pen > 0:
        penalty_parts.append(f"vagrant={vagrant_pen:.1f}")
    if stale_pen > 0:
        penalty_parts.append(f"stale={stale_pen:.1f}")
    if coverage_pen > 0:
        penalty_parts.append(f"coverage={coverage_pen:.1f}")
    if temporal_pen > 0:
        penalty_parts.append(f"temporal={temporal_pen:.1f}")

    if penalty_parts:
        overall_basis = (
            f"score={overall_raw:.1f} ({', '.join(penalty_parts)}); "
            f"confidence: {conf_basis}"
        )
    else:
        overall_basis = f"no drift detected; confidence: {conf_basis}"

    return DriftScore(
        overall_score=overall_raw,
        risk_level=overall_risk,
        confidence=score_confidence,
        basis=overall_basis,
        per_node_scores=per_node,
        top_risk_nodes=top_risk,
        warnings=warnings_out,
    )


# ---------------------------------------------------------------------------
# Disk-backed entry point
# ---------------------------------------------------------------------------

def compute_drift_score(
    project_dir: "Path",  # noqa: F821
    *,
    forecast: "DecayForecast | None" = None,
    config: DriftScorerConfig = _DEFAULT_CONFIG,
) -> DriftScore:
    """
    Load committed + planned models and anchor report from *project_dir*,
    then compute and return a DriftScore.

    Never raises. All errors are surfaced as warnings inside the returned
    DriftScore.
    """
    import warnings as _warnings_mod
    from pathlib import Path as _Path
    from genesis_architect_pro.drift_detector import compute_drift_flags
    from genesis_architect_pro.source_anchor import anchor_from_store

    project_dir = _Path(project_dir)
    score_warnings: list[str] = []

    try:
        flags = compute_drift_flags(project_dir)
    except Exception as exc:  # noqa: BLE001
        msg = f"drift_scorer: could not compute drift flags: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        from genesis_architect_pro.drift_detector import DriftFlags
        flags = DriftFlags(confidence=0.0, basis="error", warnings=[msg])
        score_warnings.append(msg)

    try:
        anchor_report = anchor_from_store(project_dir)
    except Exception as exc:  # noqa: BLE001
        msg = f"drift_scorer: could not load anchor report: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        anchor_report = None
        score_warnings.append(msg)

    result = score_drift(flags, anchor_report, forecast, config=config)
    result.warnings = score_warnings + result.warnings
    return result
