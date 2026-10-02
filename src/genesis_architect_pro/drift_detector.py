"""
drift_detector.py - Genesis Architect PRO

Read-only drift flag detection.

Produces *candidates* — not final truth. All output is advisory.
Nothing is written; no models are mutated.

Definitions
-----------
vagrant candidate
    A committed node (code-backed observation) that has no counterpart in
    the planned model.  This means the code has grown in a direction that
    the planned architecture does not acknowledge.  Confidence is higher
    when source_map has entries for the node's responsibilities.

stale candidate
    A planned responsibility (or node) that has *no* source_map anchor in
    the committed model for the same responsibility ID.  This means the
    planned intent may no longer be backed by any known code symbol.
    Confidence is lower when source_map is absent entirely.

Both sets are intersected conservatively: false negatives are safer than
false positives at this stage.

Output schema
-------------
{
  "vagrant_candidates": [
      {
        "node_id": str,
        "name": str,
        "kind": str,
        "reason": str,
        "confidence": float   # 0.0–1.0
      }, ...
  ],
  "stale_candidates": [
      {
        "node_id": str,
        "responsibility_id": str,
        "statement": str,
        "reason": str,
        "confidence": float
      }, ...
  ],
  "confidence": float,      # overall confidence in the detection pass
  "basis": str,             # human-readable explanation of confidence level
  "warnings": [str, ...]    # non-fatal issues encountered during detection
}

Confidence tiers
----------------
  >= 0.75  high   — source_map populated, both models loaded cleanly
  >= 0.50  medium — source_map partially populated or one model missing
  <  0.50  low    — source_map absent, or one model corrupted/empty
"""

from __future__ import annotations

import warnings as _warnings_mod
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VagrantCandidate:
    node_id: str
    name: str
    kind: str
    reason: str
    confidence: float


@dataclass
class StaleCandidate:
    node_id: str
    responsibility_id: str
    statement: str
    reason: str
    confidence: float


@dataclass
class DriftFlags:
    vagrant_candidates: list[VagrantCandidate] = field(default_factory=list)
    stale_candidates: list[StaleCandidate] = field(default_factory=list)
    confidence: float = 0.0
    basis: str = "no analysis performed"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "vagrant_candidates": [
                {
                    "node_id": v.node_id,
                    "name": v.name,
                    "kind": v.kind,
                    "reason": v.reason,
                    "confidence": v.confidence,
                }
                for v in self.vagrant_candidates
            ],
            "stale_candidates": [
                {
                    "node_id": s.node_id,
                    "responsibility_id": s.responsibility_id,
                    "statement": s.statement,
                    "reason": s.reason,
                    "confidence": s.confidence,
                }
                for s in self.stale_candidates
            ],
            "confidence": self.confidence,
            "basis": self.basis,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Detection constants
# ---------------------------------------------------------------------------

# Base confidence when both models loaded and source_map is populated
_CONF_HIGH: float = 0.80

# Base when source_map is entirely absent
_CONF_NO_SOURCE_MAP: float = 0.45

# Base when planned model is absent (falls back to committed)
_CONF_NO_PLANNED: float = 0.35

# Per-candidate confidence when source_map backs the detection
_CAND_CONF_BACKED: float = 0.80

# Per-candidate confidence when source_map is absent
_CAND_CONF_UNBACKED: float = 0.45


# ---------------------------------------------------------------------------
# Pure detection function
# ---------------------------------------------------------------------------

def detect_drift(
    committed: "ArchModel",  # noqa: F821  (type hint only)
    planned: "ArchModel",    # noqa: F821
    *,
    planned_was_missing: bool = False,
    source_map_empty: bool = False,
    detection_warnings: list[str] | None = None,
) -> DriftFlags:
    """
    Pure function: compare committed vs planned and return DriftFlags.

    Parameters
    ----------
    committed : ArchModel
        The code-backed committed architecture model.
    planned : ArchModel
        The intent model. If planned.json was absent the caller should
        pass the committed model here AND set planned_was_missing=True.
    planned_was_missing : bool
        True when planned.json did not exist; suppresses vagrant candidates
        (there is nothing to compare against) and sets low confidence.
    source_map_empty : bool
        True when committed.source_map has no entries; lowers confidence.
    detection_warnings : list[str] | None
        Accumulated non-fatal issues to include in the result.
    """
    warn_list: list[str] = list(detection_warnings or [])

    # --- Overall confidence ---
    if planned_was_missing:
        overall_conf = _CONF_NO_PLANNED
        basis = (
            "low confidence — planned.json absent; no intent model to compare against; "
            "vagrant detection skipped"
        )
    elif source_map_empty:
        overall_conf = _CONF_NO_SOURCE_MAP
        basis = (
            "medium confidence — source_map is empty; drift detection relies on "
            "structural comparison only, not code anchors"
        )
    else:
        overall_conf = _CONF_HIGH
        basis = (
            "high confidence — both models loaded, source_map populated; "
            "detection uses structural comparison and source anchors"
        )

    flags = DriftFlags(confidence=overall_conf, basis=basis, warnings=warn_list)

    # --- Vagrant candidates ---
    # A committed node is a vagrant candidate when it is absent from planned.
    # Skip entirely when there is no planned model to compare.
    if not planned_was_missing:
        planned_node_ids = {n.id for n in planned.nodes}
        for node in committed.nodes:
            if node.id in planned_node_ids:
                continue
            # Determine per-candidate confidence
            has_source_anchor = any(
                r.id in committed.source_map
                for r in node.responsibilities
            ) if not source_map_empty else False

            cand_conf = _CAND_CONF_BACKED if has_source_anchor else _CAND_CONF_UNBACKED

            reason = (
                "node present in committed model but absent from planned; "
                + ("source_map has anchors for its responsibilities"
                   if has_source_anchor
                   else "no source_map anchors — lower confidence")
            )
            flags.vagrant_candidates.append(VagrantCandidate(
                node_id=node.id,
                name=node.name,
                kind=node.kind,
                reason=reason,
                confidence=cand_conf,
            ))

    # Sort for determinism
    flags.vagrant_candidates.sort(key=lambda v: v.node_id)

    # --- Stale candidates ---
    # A planned responsibility is a stale candidate when:
    #   1. The responsibility ID exists in planned but NOT in committed.source_map.
    #   2. There is also no committed node with a matching responsibility ID.
    # Conservative: only flag when BOTH conditions are true.

    committed_resp_ids: set[str] = set()
    for n in committed.nodes:
        for r in n.responsibilities:
            committed_resp_ids.add(r.id)

    source_map_ids: set[str] = set(committed.source_map.keys())

    for node in planned.nodes:
        for resp in node.responsibilities:
            in_committed_resp = resp.id in committed_resp_ids
            in_source_map = resp.id in source_map_ids

            # Skip if either backing signal is present (conservative)
            if in_committed_resp or in_source_map:
                continue

            reason = (
                "planned responsibility not found in committed model responsibilities "
                "and has no source_map anchor"
            )
            if source_map_empty:
                reason += " (source_map absent — confidence reduced)"

            cand_conf = (
                _CAND_CONF_BACKED if not source_map_empty
                else _CAND_CONF_UNBACKED
            )

            flags.stale_candidates.append(StaleCandidate(
                node_id=node.id,
                responsibility_id=resp.id,
                statement=resp.statement,
                reason=reason,
                confidence=cand_conf,
            ))

    # Sort for determinism
    flags.stale_candidates.sort(key=lambda s: (s.node_id, s.responsibility_id))

    return flags


# ---------------------------------------------------------------------------
# ModelStore-integrated entry point
# ---------------------------------------------------------------------------

def compute_drift_flags(project_dir: "Path") -> DriftFlags:  # noqa: F821
    """
    Load committed and planned models from *project_dir* and run drift detection.

    Never raises. All errors are collected as warnings in the returned DriftFlags.
    """
    from pathlib import Path as _Path
    from genesis_architect_pro.model_store import ModelStore

    project_dir = _Path(project_dir)
    detection_warnings: list[str] = []

    try:
        store = ModelStore(project_dir)
    except Exception as exc:  # noqa: BLE001
        msg = f"drift_detector: could not create ModelStore: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        return DriftFlags(confidence=0.0, basis="error — ModelStore unavailable",
                          warnings=[msg])

    # Load committed
    try:
        committed = store.load_committed()
    except Exception as exc:  # noqa: BLE001
        msg = f"drift_detector: could not load committed model: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        detection_warnings.append(msg)
        from genesis_architect_pro.model_store import ArchModel
        committed = ArchModel()

    # Load planned — check if planned.json exists first
    planned_path = project_dir / ".genesis" / "planned.json"
    planned_was_missing = not planned_path.exists()

    try:
        planned = store.load_planned()
    except Exception as exc:  # noqa: BLE001
        msg = f"drift_detector: could not load planned model: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        detection_warnings.append(msg)
        from genesis_architect_pro.model_store import ArchModel
        planned = ArchModel()
        planned_was_missing = True

    source_map_empty = not committed.source_map

    return detect_drift(
        committed,
        planned,
        planned_was_missing=planned_was_missing,
        source_map_empty=source_map_empty,
        detection_warnings=detection_warnings,
    )
