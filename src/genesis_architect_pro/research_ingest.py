"""Research Ingest — the bridge from findings gathered elsewhere into the GDE.

Genesis does not fetch. `field_intelligence.run_field_workflow` returns a query
plan with `findings=[]` and leaves the searching to the caller — an agent
driving Exa, Tavily, Firecrawl or GitHub search. Until now nothing carried what
that caller found back in: the RESEARCH engines ran on an empty list, so the
evidence pack, the confidence score and the gates were all computed from
nothing.

This module is that hand-back. `genesis ingest FILE` validates a findings file
and stores it under `.genesis/research/findings.json`; the field_intelligence
adapter reads it back on the next RESEARCH session.

Two rules shape the storage format:

  * A finding's `verified` flag is never stored and never taken from the file.
    What is stored is the *evidence* — `confirmed_by` / `contradicted_by`
    registry source ids — and verification is re-derived from it, against the
    registry as it stands, every time the findings are read. A stored summary
    that can disagree with its evidence eventually does, silently. A caller that
    writes `"verified": true` gets a warning and no effect: a finding becomes
    verified only when an official/source/security registry source confirms it
    (see field_intelligence.verify_finding).

  * Genesis records what the caller reports; it does not re-fetch it. Source
    ids and URLs are the caller's provenance claims. The registry decides which
    ids count as engineering truth, but not whether the caller really read
    them.

Input format (a bare list of finding objects is accepted too):

    {
      "tool": "qdrant",                                   # optional label
      "findings": [
        {"claim": "...", "source_id": "github", "url": "https://...",
         "sentiment": "negative",
         "confirmed_by": ["official_docs"], "contradicted_by": []}
      ],
      "item_findings": {"qdrant": {"license": "Apache-2.0"}},   # optional
      "uncertain": ["pgvector:hybrid_search"]                   # optional
    }

`item_findings` fills the outline's items x fields grid (research_outline), so
coverage can be measured against the stated target. `uncertain` marks cells the
caller does not trust, exactly as research_orchestrator.is_uncertain reads it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from genesis_architect_pro.field_intelligence import FieldFinding, verify_finding
from genesis_architect_pro.source_registry import load_registry

FINDINGS_FILENAME = "findings.json"
MAX_INPUT_BYTES = 2_000_000
MAX_FINDINGS = 200
MAX_CLAIM_CHARS = 2000
_SENTIMENTS = ("positive", "negative", "neutral")
_STORE_VERSION = 1


def findings_path(project_dir: Path) -> Path:
    return Path(project_dir) / ".genesis" / "research" / FINDINGS_FILENAME


@dataclass
class IngestResult:
    """What one `ingest_file` call did. `ok` is False only when nothing was
    stored because the input itself was unusable; individually rejected
    findings do not fail the call, they are listed in `rejected`."""

    ok: bool
    dry_run: bool = False
    stored_path: str = ""
    accepted: int = 0
    total_stored: int = 0
    verified: int = 0
    contradicted: int = 0
    unverified: int = 0
    grid_cells: int = 0
    rejected: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "stored_path": self.stored_path,
            "accepted": self.accepted,
            "total_stored": self.total_stored,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "unverified": self.unverified,
            "grid_cells": self.grid_cells,
            "rejected": list(self.rejected),
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass
class IngestedResearch:
    """Ingested findings as the engines consume them. `error` is set when a
    findings file exists but cannot be read — the caller must surface it and
    treat the research as having no evidence, never as having clean evidence."""

    findings: list = field(default_factory=list)          # list[FieldFinding]
    item_findings: dict = field(default_factory=dict)     # item -> field -> value
    uncertain: list = field(default_factory=list)
    present: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _str_list(value: object, label: str, warnings: list[str], where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        warnings.append(f"{where}: '{label}' must be a list of source ids — ignored")
        return []
    return [v.strip() for v in value if v.strip()]


def _clean_finding(raw: object, index: int, reg, warnings: list[str]) -> tuple[dict | None, str]:
    """Validate one finding. Returns (record, "") or (None, reason)."""
    where = f"findings[{index}]"
    if not isinstance(raw, dict):
        return None, f"{where}: not an object"
    claim = raw.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return None, f"{where}: 'claim' is required and must be a non-empty string"
    claim = claim.strip()
    if len(claim) > MAX_CLAIM_CHARS:
        return None, f"{where}: claim longer than {MAX_CLAIM_CHARS} characters"

    if "verified" in raw:
        warnings.append(
            f"{where}: 'verified' in the file is ignored — a finding is verified only "
            "when an official/source/security registry source is listed in 'confirmed_by'"
        )

    source_id = raw.get("source_id", "reddit_answers")
    if not isinstance(source_id, str) or not source_id.strip():
        warnings.append(f"{where}: 'source_id' is not a string — using 'reddit_answers'")
        source_id = "reddit_answers"
    source_id = source_id.strip()
    if reg.get(source_id) is None:
        warnings.append(
            f"{where}: source_id '{source_id}' is not in the source registry — "
            "kept, but it carries no tier and counts for nothing"
        )

    url = raw.get("url", "")
    if not isinstance(url, str):
        warnings.append(f"{where}: 'url' is not a string — dropped")
        url = ""

    sentiment = raw.get("sentiment", "neutral")
    if sentiment not in _SENTIMENTS:
        warnings.append(f"{where}: sentiment {sentiment!r} not one of {_SENTIMENTS} — using 'neutral'")
        sentiment = "neutral"

    confirmed = _str_list(raw.get("confirmed_by"), "confirmed_by", warnings, where)
    contradicted = _str_list(raw.get("contradicted_by"), "contradicted_by", warnings, where)
    for label, ids in (("confirmed_by", confirmed), ("contradicted_by", contradicted)):
        for sid in ids:
            if reg.get(sid) is None:
                warnings.append(f"{where}: {label} '{sid}' is not in the source registry — cannot count")

    return {
        "claim": claim,
        "source_id": source_id,
        "url": url.strip(),
        "sentiment": sentiment,
        "confirmed_by": confirmed,
        "contradicted_by": contradicted,
    }, ""


def _clean_grid(raw: object, warnings: list[str]) -> dict[str, dict[str, str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        warnings.append("'item_findings' must be an object of item -> {field: value} — ignored")
        return {}
    grid: dict[str, dict[str, str]] = {}
    for item, cells in raw.items():
        if not isinstance(cells, dict):
            warnings.append(f"item_findings[{item!r}] is not an object — skipped")
            continue
        for fld, value in cells.items():
            if isinstance(value, str) and value.strip():
                grid.setdefault(str(item), {})[str(fld)] = value.strip()
            else:
                warnings.append(f"item_findings[{item!r}][{fld!r}] is not a non-empty string — cell skipped")
    return grid


def _finding_key(rec: dict) -> tuple[str, str, str]:
    return (rec["claim"].lower(), rec["source_id"], rec["url"])


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _read_store(path: Path) -> tuple[dict | None, str]:
    """Returns (store, error). A missing file is (None, "")."""
    if not path.is_file():
        return None, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"cannot read {path.name}: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None, f"{path.name} is not a valid ingest store"
    return data, ""


def _write_store(path: Path, store: dict) -> None:
    """Atomic write: a reader must never see a half-written store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".findings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _to_field_findings(records: list[dict], project_dir: Path) -> list[FieldFinding]:
    """Derive FieldFindings from stored evidence. Verification is computed
    here, at read time, from confirmed_by/contradicted_by — never stored."""
    out: list[FieldFinding] = []
    for rec in records:
        finding = FieldFinding(
            claim=rec["claim"], source_id=rec["source_id"],
            url=rec.get("url", ""), sentiment=rec.get("sentiment", "neutral"),
        )
        verify_finding(
            finding,
            confirming_sources=rec.get("confirmed_by"),
            contradicting_sources=rec.get("contradicted_by"),
            project_root=project_dir,
        )
        out.append(finding)
    return out


def load_ingested(project_dir: Path) -> IngestedResearch:
    """Read the ingest store back for the engines. Fails closed: an unreadable
    store is reported in `error` and yields no findings."""
    store, error = _read_store(findings_path(project_dir))
    if error:
        return IngestedResearch(present=True, error=error)
    if store is None:
        return IngestedResearch()
    records: list[dict] = []
    for rec in store["findings"]:
        if isinstance(rec, dict) and isinstance(rec.get("claim"), str) and rec["claim"].strip():
            records.append({
                "claim": rec["claim"],
                "source_id": rec.get("source_id") if isinstance(rec.get("source_id"), str) else "reddit_answers",
                "url": rec.get("url") if isinstance(rec.get("url"), str) else "",
                "sentiment": rec.get("sentiment") if rec.get("sentiment") in _SENTIMENTS else "neutral",
                "confirmed_by": [s for s in (rec.get("confirmed_by") or []) if isinstance(s, str)],
                "contradicted_by": [s for s in (rec.get("contradicted_by") or []) if isinstance(s, str)],
            })
    grid = _clean_grid(store.get("item_findings"), [])
    uncertain = [u for u in (store.get("uncertain") or []) if isinstance(u, str)]
    return IngestedResearch(
        findings=_to_field_findings(records, Path(project_dir)),
        item_findings=grid, uncertain=uncertain, present=True,
    )


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_file(source: Path, project_dir: Path, *, replace: bool = False,
                dry_run: bool = False) -> IngestResult:
    """Validate `source` and merge it into the project's ingest store.

    Merge is the default (findings de-duplicated on claim + source + url, grid
    cells overwritten by the newer file, `uncertain` unioned) so several
    research batches can be ingested in turn. `replace=True` starts the store
    over. `dry_run=True` validates and reports without writing anything.
    """
    project_dir = Path(project_dir)
    source = Path(source)
    result = IngestResult(ok=False, dry_run=dry_run)

    if not source.is_file():
        result.error = f"findings file not found: {source}"
        return result
    try:
        size = source.stat().st_size
    except OSError as exc:
        result.error = f"cannot stat findings file: {exc}"
        return result
    if size > MAX_INPUT_BYTES:
        result.error = f"findings file is {size} bytes; the limit is {MAX_INPUT_BYTES}"
        return result
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result.error = f"findings file is not valid JSON: {exc}"
        return result

    if isinstance(data, list):
        data = {"findings": data}
    if not isinstance(data, dict) or not isinstance(data.get("findings", []), list):
        result.error = "expected an object with a 'findings' list, or a bare list of findings"
        return result

    raw_findings = data.get("findings", [])
    if len(raw_findings) > MAX_FINDINGS:
        result.warnings.append(
            f"{len(raw_findings)} findings supplied; only the first {MAX_FINDINGS} are read"
        )
        raw_findings = raw_findings[:MAX_FINDINGS]

    reg = load_registry(project_dir)
    incoming: list[dict] = []
    for idx, raw in enumerate(raw_findings):
        rec, reason = _clean_finding(raw, idx, reg, result.warnings)
        if rec is None:
            result.rejected.append(reason)
        else:
            incoming.append(rec)
    grid = _clean_grid(data.get("item_findings"), result.warnings)
    uncertain = _str_list(data.get("uncertain"), "uncertain", result.warnings, "file")

    if not incoming and not grid:
        result.error = "nothing usable in the file: no valid findings and no item_findings"
        return result

    path = findings_path(project_dir)
    store, store_error = ({}, "") if replace else _read_store(path)
    if store_error:
        # Do not silently overwrite a store that is present but unreadable.
        result.error = f"{store_error}; fix or delete it, or re-run with --replace"
        return result
    store = store or {}

    existing = [r for r in store.get("findings", []) if isinstance(r, dict) and isinstance(r.get("claim"), str)]
    seen = {_finding_key(r) for r in existing}
    merged = list(existing)
    for rec in incoming:
        if _finding_key(rec) in seen:
            continue
        seen.add(_finding_key(rec))
        merged.append(rec)
        result.accepted += 1
    if len(merged) > MAX_FINDINGS:
        result.warnings.append(f"store capped at {MAX_FINDINGS} findings; newest were dropped")
        merged = merged[:MAX_FINDINGS]

    merged_grid: dict[str, dict[str, str]] = _clean_grid(store.get("item_findings"), [])
    for item, cells in grid.items():
        merged_grid.setdefault(item, {}).update(cells)
    merged_uncertain = sorted({*(store.get("uncertain") or []), *uncertain})

    new_store = {
        "version": _STORE_VERSION,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "tool": data.get("tool") if isinstance(data.get("tool"), str) else store.get("tool", ""),
        "findings": merged,
        "item_findings": merged_grid,
        "uncertain": merged_uncertain,
    }

    derived = _to_field_findings(merged, project_dir)
    result.total_stored = len(merged)
    result.verified = sum(1 for f in derived if f.status == "verified")
    result.contradicted = sum(1 for f in derived if f.status == "contradicted")
    result.unverified = sum(1 for f in derived if f.status == "unverified")
    result.grid_cells = sum(len(c) for c in merged_grid.values())

    if not dry_run:
        try:
            _write_store(path, new_store)
        except OSError as exc:
            result.error = f"could not write {path.name}: {exc}"
            return result
        try:
            result.stored_path = str(path.relative_to(project_dir))
        except ValueError:
            result.stored_path = path.name
    result.ok = True
    return result


def format_ingest_result(result: IngestResult) -> str:
    """Plain-text report for the CLI."""
    if not result.ok:
        return f"Ingest failed: {result.error}"
    verb = "Would store" if result.dry_run else "Stored"
    lines = [
        f"{verb} {result.accepted} new finding(s); {result.total_stored} total"
        + (f" in {result.stored_path}" if result.stored_path else ""),
        f"  verified {result.verified} · contradicted {result.contradicted} · "
        f"unverified {result.unverified}",
    ]
    if result.grid_cells:
        lines.append(f"  outline grid cells filled: {result.grid_cells}")
    if result.unverified and not result.verified:
        lines.append(
            "  No finding is verified yet. Verification needs an official/source/security "
            "registry id in 'confirmed_by'."
        )
    for reason in result.rejected:
        lines.append(f"  rejected: {reason}")
    for warning in result.warnings:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)
