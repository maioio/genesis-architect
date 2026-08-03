"""
model_store.py - Genesis Architect PRO

Dual-layer architecture model: planned vs. committed.

  committed (model.json):   verified architecture — code backs every claim
  planned (planned.json):   intent — what we will build; not yet in code

The two layers diverge when the agent or user proposes architecture changes.
mark_implemented() folds planned nodes into committed once code backs them.

All persistence lives in .genesis/ at the project root.

Model format (JSON, indent=2)
------------------------------
{
  "version": "1",
  "nodes":  [ { ...ModelNode fields... } ],
  "links":  [ { ...ModelLink fields... } ],
  "groups": [ { ...ModelGroup fields... } ],
  "source_map": { "<responsibility_id>": [ { "pattern": "...", "line": N,
                                             "end_line": N, "symbol": "..." } ] }
}

Persistence strategy
---------------------
Writes use a write-to-temp-then-rename pattern to avoid leaving a partially
written file if the process is interrupted. The temp file is created in the
same directory as the target (so the rename is atomic on POSIX; on Windows
it is not guaranteed atomic but is still safer than truncating in place).

Schema versioning
-----------------
The "version" field is stored but not currently enforced. If a future reader
encounters an unknown version it will emit a warning via the stdlib `warnings`
module and continue loading. Adding fields with Python defaults keeps the
format forward-compatible; removing fields triggers the warning path.

Divergence check (is_planned_diverged)
---------------------------------------
Structural divergence only — not deep value equality. Compares:
  - set of node IDs
  - set of link IDs
  - set of group IDs
  - set of (node_id, responsibility_id) pairs
  - set of responsibility statement strings per node
This is intentionally cheap (O(V+E)) and does not compare technology /
description / method fields. Future drift detection will do full diffing.

Thread safety
-------------
ModelStore instances are NOT thread-safe. Each call acquires no lock.
For concurrent use, the caller must ensure serialised access.
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path

CURRENT_VERSION: str = "1"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ModelResponsibility:
    """A single responsibility assigned to a node or group."""
    id: str
    statement: str
    vagrant: bool = False          # discovered in code, awaiting user verdict
    stale: bool = False            # committed claim, code no longer backs it
    last_touched_at: str | None = None   # ISO 8601 datetime


@dataclass
class ModelNode:
    """
    A C4-style architecture element.

    kind: one of person | system | container | component | symbol
    """
    id: str
    kind: str
    name: str
    parent_id: str | None = None
    technology: str | None = None
    description: str | None = None
    responsibilities: list[ModelResponsibility] = field(default_factory=list)
    external: bool = False
    vagrant: bool = False          # proposed; not yet in code


@dataclass
class ModelLink:
    """A directed relationship between two nodes."""
    id: str
    src: str
    dst: str
    label: str = ""
    method: str | None = None


@dataclass
class ModelGroup:
    """A named collection of nodes (bounded context, team, layer, …)."""
    id: str
    name: str
    member_ids: list[str] = field(default_factory=list)
    description: str | None = None
    responsibilities: list[ModelResponsibility] = field(default_factory=list)


@dataclass
class ArchModel:
    """
    The full architecture model for one project.

    source_map: maps a responsibility_id to a list of source anchors:
      [ { "pattern": "...", "line": N, "end_line": N, "symbol": "..." } ]
    This is populated by future source-anchor analysis; empty on first use.

    version: used for forward-compatibility checks on load.
    """
    nodes: list[ModelNode] = field(default_factory=list)
    links: list[ModelLink] = field(default_factory=list)
    groups: list[ModelGroup] = field(default_factory=list)
    source_map: dict[str, list[dict]] = field(default_factory=dict)
    version: str = CURRENT_VERSION


# ---------------------------------------------------------------------------
# ModelDiff — result of comparing committed vs planned
# ---------------------------------------------------------------------------

@dataclass
class NodeChange:
    """Fields that differ between committed and planned for the same node ID."""
    node_id: str
    field: str          # "name", "kind", "technology", "description", "external"
    committed_value: object
    planned_value: object


@dataclass
class ResponsibilityChange:
    """A responsibility added or removed on a specific node."""
    node_id: str
    responsibility_id: str
    statement: str
    change: str         # "added" | "removed"


@dataclass
class LinkChange:
    """A link added, removed, or changed between committed and planned."""
    link_id: str
    change: str         # "added" | "removed" | "changed"
    committed: dict | None = None   # snapshot of committed link (if existed)
    planned: dict | None = None     # snapshot of planned link (if present)


@dataclass
class ModelDiff:
    """
    Compact structural diff between committed and planned architecture models.

    All lists are empty when no changes are detected.
    Summary is a human-readable single-line digest.
    """
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    changed_nodes: list[NodeChange] = field(default_factory=list)
    added_links: list[str] = field(default_factory=list)
    removed_links: list[str] = field(default_factory=list)
    changed_links: list[LinkChange] = field(default_factory=list)
    responsibility_changes: list[ResponsibilityChange] = field(default_factory=list)
    summary: str = "no changes"

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_nodes or self.removed_nodes or self.changed_nodes
            or self.added_links or self.removed_links or self.changed_links
            or self.responsibility_changes
        )

    def to_dict(self) -> dict:
        """JSON-safe representation for embedding in scan() output."""
        return {
            "has_changes": self.has_changes,
            "summary": self.summary,
            "added_nodes": self.added_nodes,
            "removed_nodes": self.removed_nodes,
            "changed_nodes": [
                {
                    "node_id": c.node_id,
                    "field": c.field,
                    "committed_value": c.committed_value,
                    "planned_value": c.planned_value,
                }
                for c in self.changed_nodes
            ],
            "added_links": self.added_links,
            "removed_links": self.removed_links,
            "changed_links": [
                {
                    "link_id": lc.link_id,
                    "change": lc.change,
                    "committed": lc.committed,
                    "planned": lc.planned,
                }
                for lc in self.changed_links
            ],
            "responsibility_changes": [
                {
                    "node_id": rc.node_id,
                    "responsibility_id": rc.responsibility_id,
                    "statement": rc.statement,
                    "change": rc.change,
                }
                for rc in self.responsibility_changes
            ],
        }


# Compared node fields (order determines priority in summary)
_NODE_FIELDS: tuple[str, ...] = ("name", "kind", "technology", "description", "external")


def _compute_diff(committed: ArchModel, planned: ArchModel) -> ModelDiff:
    """Pure function: diff committed vs planned, return ModelDiff."""
    diff = ModelDiff()

    # --- Nodes ---
    committed_nodes: dict[str, ModelNode] = {n.id: n for n in committed.nodes}
    planned_nodes: dict[str, ModelNode]   = {n.id: n for n in planned.nodes}

    diff.added_nodes   = sorted(planned_nodes.keys() - committed_nodes.keys())
    diff.removed_nodes = sorted(committed_nodes.keys() - planned_nodes.keys())

    # Changed fields on nodes present in both
    for nid in sorted(committed_nodes.keys() & planned_nodes.keys()):
        c_node = committed_nodes[nid]
        p_node = planned_nodes[nid]
        for f in _NODE_FIELDS:
            cv = getattr(c_node, f)
            pv = getattr(p_node, f)
            if cv != pv:
                diff.changed_nodes.append(NodeChange(
                    node_id=nid, field=f,
                    committed_value=cv, planned_value=pv,
                ))

        # Responsibilities
        c_resp: dict[str, ModelResponsibility] = {r.id: r for r in c_node.responsibilities}
        p_resp: dict[str, ModelResponsibility] = {r.id: r for r in p_node.responsibilities}
        for rid in sorted(p_resp.keys() - c_resp.keys()):
            diff.responsibility_changes.append(ResponsibilityChange(
                node_id=nid, responsibility_id=rid,
                statement=p_resp[rid].statement, change="added",
            ))
        for rid in sorted(c_resp.keys() - p_resp.keys()):
            diff.responsibility_changes.append(ResponsibilityChange(
                node_id=nid, responsibility_id=rid,
                statement=c_resp[rid].statement, change="removed",
            ))

    # Also capture responsibilities on added/removed nodes for completeness
    for nid in diff.added_nodes:
        for r in planned_nodes[nid].responsibilities:
            diff.responsibility_changes.append(ResponsibilityChange(
                node_id=nid, responsibility_id=r.id,
                statement=r.statement, change="added",
            ))
    for nid in diff.removed_nodes:
        for r in committed_nodes[nid].responsibilities:
            diff.responsibility_changes.append(ResponsibilityChange(
                node_id=nid, responsibility_id=r.id,
                statement=r.statement, change="removed",
            ))

    # --- Links ---
    def _link_snapshot(lnk: ModelLink) -> dict:
        return {"src": lnk.src, "dst": lnk.dst, "label": lnk.label}

    committed_links: dict[str, ModelLink] = {lnk.id: lnk for lnk in committed.links}
    planned_links: dict[str, ModelLink]   = {lnk.id: lnk for lnk in planned.links}

    diff.added_links   = sorted(planned_links.keys() - committed_links.keys())
    diff.removed_links = sorted(committed_links.keys() - planned_links.keys())

    for lid in sorted(committed_links.keys() & planned_links.keys()):
        c_lnk = committed_links[lid]
        p_lnk = planned_links[lid]
        if c_lnk.src != p_lnk.src or c_lnk.dst != p_lnk.dst or c_lnk.label != p_lnk.label:
            diff.changed_links.append(LinkChange(
                link_id=lid, change="changed",
                committed=_link_snapshot(c_lnk),
                planned=_link_snapshot(p_lnk),
            ))

    # Also surface added/removed links as LinkChange entries for detail
    for lid in diff.added_links:
        diff.changed_links.append(LinkChange(
            link_id=lid, change="added",
            committed=None, planned=_link_snapshot(planned_links[lid]),
        ))
    for lid in diff.removed_links:
        diff.changed_links.append(LinkChange(
            link_id=lid, change="removed",
            committed=_link_snapshot(committed_links[lid]), planned=None,
        ))
    # Keep changed_links in a deterministic order
    diff.changed_links.sort(key=lambda lc: (lc.change, lc.link_id))

    # --- Summary ---
    parts: list[str] = []
    if diff.added_nodes:
        parts.append(f"+{len(diff.added_nodes)} node{'s' if len(diff.added_nodes) != 1 else ''}")
    if diff.removed_nodes:
        parts.append(f"-{len(diff.removed_nodes)} node{'s' if len(diff.removed_nodes) != 1 else ''}")
    if diff.changed_nodes:
        parts.append(f"~{len(diff.changed_nodes)} field change{'s' if len(diff.changed_nodes) != 1 else ''}")
    if diff.added_links:
        parts.append(f"+{len(diff.added_links)} link{'s' if len(diff.added_links) != 1 else ''}")
    if diff.removed_links:
        parts.append(f"-{len(diff.removed_links)} link{'s' if len(diff.removed_links) != 1 else ''}")
    if diff.changed_links and not (diff.added_links or diff.removed_links):
        changed_only = [lc for lc in diff.changed_links if lc.change == "changed"]
        if changed_only:
            parts.append(f"~{len(changed_only)} link change{'s' if len(changed_only) != 1 else ''}")
    if diff.responsibility_changes:
        added_r  = sum(1 for rc in diff.responsibility_changes if rc.change == "added")
        removed_r = sum(1 for rc in diff.responsibility_changes if rc.change == "removed")
        if added_r:
            parts.append(f"+{added_r} resp")
        if removed_r:
            parts.append(f"-{removed_r} resp")
    diff.summary = ", ".join(parts) if parts else "no changes"

    return diff


# ---------------------------------------------------------------------------
# ModelStore
# ---------------------------------------------------------------------------

class ModelStore:
    """
    Persists and manages the dual-layer (committed + planned) architecture model.

    Parameters
    ----------
    project_path : path-like
        Root directory of the project. The store creates / reads from
        ``<project_path>/.genesis/``.
    """

    COMMITTED_FILENAME = "model.json"
    PLANNED_FILENAME   = "planned.json"

    def __init__(self, project_path: Path | str) -> None:
        self.genesis_dir    = Path(project_path) / ".genesis"
        self.committed_path = self.genesis_dir / self.COMMITTED_FILENAME
        self.planned_path   = self.genesis_dir / self.PLANNED_FILENAME

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_committed(self) -> ArchModel:
        """
        Load the committed model from model.json.

        Returns an empty ArchModel if the file does not exist (first run).
        Returns an empty ArchModel if the file is corrupted (logs a warning).
        """
        return self._load(self.committed_path, label="committed")

    def load_planned(self) -> ArchModel:
        """
        Load the planned model from planned.json.

        Falls back to the committed model if planned.json does not exist
        (meaning there is no divergence yet — planned == committed).
        Returns an empty ArchModel if both are missing.
        """
        if not self.planned_path.exists():
            return self.load_committed()
        return self._load(self.planned_path, label="planned")

    def _load(self, path: Path, *, label: str) -> ArchModel:
        """
        Deserialise an ArchModel from *path*.

        Handles: missing file, empty file, invalid JSON, unknown version,
        missing keys (forward/backward compat).
        """
        if not path.exists():
            return ArchModel()
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            warnings.warn(
                f"ModelStore: could not read {label} model at {path}: {exc}",
                RuntimeWarning, stacklevel=3,
            )
            return ArchModel()
        if not raw:
            return ArchModel()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            warnings.warn(
                f"ModelStore: {label} model at {path} is not valid JSON "
                f"(returning empty model): {exc}",
                RuntimeWarning, stacklevel=3,
            )
            return ArchModel()
        if not isinstance(data, dict):
            warnings.warn(
                f"ModelStore: {label} model at {path} has unexpected root type "
                f"{type(data).__name__!r} (expected dict); returning empty model.",
                RuntimeWarning, stacklevel=3,
            )
            return ArchModel()
        return self._from_dict(data)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_committed(self, model: ArchModel) -> None:
        """Persist *model* to model.json (write-then-rename)."""
        self._save(model, self.committed_path)

    def save_planned(self, model: ArchModel) -> None:
        """Persist *model* to planned.json (write-then-rename)."""
        self._save(model, self.planned_path)

    def _save(self, model: ArchModel, path: Path) -> None:
        """
        Serialise *model* to *path* using a write-to-temp-then-rename strategy.

        The temp file lives in the same directory as *path* so the rename
        stays on the same filesystem (required for atomicity on POSIX).
        """
        self.genesis_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._to_dict(model), indent=2, ensure_ascii=False)
        # Write to a sibling temp file then rename
        fd, tmp_name = tempfile.mkstemp(
            dir=self.genesis_dir, prefix=path.stem + "_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            # On Windows, the target must not exist before rename
            try:
                os.replace(tmp_name, path)
            except OSError:
                # Fallback: remove target then rename (less atomic but safe)
                path.unlink(missing_ok=True)
                os.rename(tmp_name, path)
        except Exception:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # mark_implemented
    # ------------------------------------------------------------------

    def mark_implemented(self, node_ids: list[str]) -> None:
        """
        Fold planned nodes into committed and remove them from planned.

        For each node_id in node_ids:
          1. Look up the node in the planned model.
          2. If node already exists in committed: merge its responsibilities
             (add new ones; keep existing ones unchanged).
          3. If node does not exist in committed: add it wholesale.
          4. Copy source_map entries for all of the node's responsibility IDs.
          5. Remove the node from the planned model.

        Both models are saved atomically after all mutations.

        node_ids not found in planned are silently skipped (idempotent).
        """
        committed = self.load_committed()
        planned   = self.load_planned()

        committed_index: dict[str, ModelNode] = {n.id: n for n in committed.nodes}

        remaining_planned: list[ModelNode] = []
        for node in planned.nodes:
            if node.id not in node_ids:
                remaining_planned.append(node)
                continue

            # Merge into committed
            if node.id in committed_index:
                target = committed_index[node.id]
                existing_resp_ids = {r.id for r in target.responsibilities}
                for resp in node.responsibilities:
                    if resp.id not in existing_resp_ids:
                        target.responsibilities.append(resp)
            else:
                committed.nodes.append(node)
                committed_index[node.id] = node

            # Copy source_map entries for this node's responsibilities
            for resp in node.responsibilities:
                if resp.id in planned.source_map:
                    committed.source_map.setdefault(resp.id, [])
                    # Merge without duplicating identical entries
                    existing = {json.dumps(e, sort_keys=True)
                                for e in committed.source_map[resp.id]}
                    for entry in planned.source_map[resp.id]:
                        key = json.dumps(entry, sort_keys=True)
                        if key not in existing:
                            committed.source_map[resp.id].append(entry)
                            existing.add(key)

        planned.nodes = remaining_planned
        self.save_committed(committed)
        self.save_planned(planned)

    # ------------------------------------------------------------------
    # Divergence check
    # ------------------------------------------------------------------

    def is_planned_diverged(self) -> bool:
        """
        Return True when the planned model is structurally different from
        the committed model.

        Compares:
          - node IDs
          - link IDs
          - group IDs
          - responsibility IDs per node (not values)
          - responsibility statement strings per node
        """
        committed = self.load_committed()
        planned   = self.load_planned()
        return self._structural_signature(committed) != self._structural_signature(planned)

    @staticmethod
    def _structural_signature(model: ArchModel) -> frozenset:
        """
        Cheap structural fingerprint of a model.

        Returns a frozenset of tagged tuples that captures:
          node IDs, link IDs, group IDs, and per-node responsibility (id, statement) pairs.
        This is intentionally NOT a full deep-equality check.
        """
        parts: list[tuple] = []
        for n in model.nodes:
            parts.append(("node", n.id))
            for r in n.responsibilities:
                parts.append(("resp", n.id, r.id, r.statement))
        for lnk in model.links:
            parts.append(("link", lnk.id))
        for g in model.groups:
            parts.append(("group", g.id))
        return frozenset(parts)

    # ------------------------------------------------------------------
    # Model diff
    # ------------------------------------------------------------------

    def model_diff(self) -> "ModelDiff":
        """
        Compute a structural diff between committed and planned models.

        Detects:
          - nodes added in planned (not in committed)
          - nodes removed from planned (in committed but not in planned)
          - nodes whose fields changed between committed and planned
          - links added, removed, or changed (src/dst/label)
          - responsibility additions and removals per node

        Returns a ModelDiff dataclass. Never raises; corrupted models
        emit a warning and return an empty diff.
        """
        try:
            committed = self.load_committed()
            planned   = self.load_planned()
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"ModelStore.model_diff: could not load models: {exc}",
                RuntimeWarning, stacklevel=2,
            )
            return ModelDiff()

        return _compute_diff(committed, planned)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _to_dict(self, model: ArchModel) -> dict:
        """
        Serialise an ArchModel to a JSON-safe dict.

        Uses dataclasses.asdict() for deep conversion, then adds the
        top-level "version" field. Lists are preserved in insertion order
        to ensure deterministic round-trips.
        """
        d = asdict(model)
        # asdict already includes version field from the dataclass.
        # Ensure version is always at the top level for forward-compat.
        d["version"] = model.version or CURRENT_VERSION
        return d

    def _from_dict(self, data: dict) -> ArchModel:
        """
        Deserialise an ArchModel from a raw dict (parsed JSON).

        Unknown keys are silently ignored (forward-compat).
        Missing keys fall back to dataclass defaults (backward-compat).
        Version mismatch emits a warning but does not abort.
        """
        file_version = data.get("version", CURRENT_VERSION)
        if file_version != CURRENT_VERSION:
            warnings.warn(
                f"ModelStore: model version {file_version!r} does not match "
                f"current version {CURRENT_VERSION!r}. Loading anyway.",
                UserWarning, stacklevel=4,
            )

        nodes  = [self._node_from_dict(n) for n in data.get("nodes", [])]
        links  = [self._link_from_dict(lnk) for lnk in data.get("links", [])]
        groups = [self._group_from_dict(g) for g in data.get("groups", [])]
        source_map = data.get("source_map", {})
        if not isinstance(source_map, dict):
            source_map = {}

        return ArchModel(
            nodes=nodes,
            links=links,
            groups=groups,
            source_map=source_map,
            version=file_version,
        )

    @staticmethod
    def _resp_from_dict(d: dict) -> ModelResponsibility:
        return ModelResponsibility(
            id=d.get("id", ""),
            statement=d.get("statement", ""),
            vagrant=bool(d.get("vagrant", False)),
            stale=bool(d.get("stale", False)),
            last_touched_at=d.get("last_touched_at"),
        )

    @staticmethod
    def _node_from_dict(d: dict) -> ModelNode:
        return ModelNode(
            id=d.get("id", ""),
            kind=d.get("kind", "component"),
            name=d.get("name", ""),
            parent_id=d.get("parent_id"),
            technology=d.get("technology"),
            description=d.get("description"),
            responsibilities=[
                ModelStore._resp_from_dict(r)
                for r in d.get("responsibilities", [])
            ],
            external=bool(d.get("external", False)),
            vagrant=bool(d.get("vagrant", False)),
        )

    @staticmethod
    def _link_from_dict(d: dict) -> ModelLink:
        return ModelLink(
            id=d.get("id", ""),
            src=d.get("src", ""),
            dst=d.get("dst", ""),
            label=d.get("label", ""),
            method=d.get("method"),
        )

    @staticmethod
    def _group_from_dict(d: dict) -> ModelGroup:
        return ModelGroup(
            id=d.get("id", ""),
            name=d.get("name", ""),
            member_ids=list(d.get("member_ids", [])),
            description=d.get("description"),
            responsibilities=[
                ModelStore._resp_from_dict(r)
                for r in d.get("responsibilities", [])
            ],
        )
