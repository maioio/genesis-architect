"""
source_anchor.py - Genesis Architect PRO

Conservative, read-only, deterministic source-level responsibility anchoring.

This module scans source files and attempts to match each architecture
responsibility's statement text to concrete code evidence — producing
source_map-style anchor entries that downstream layers (drift_detector,
model_diff) can use to raise or lower confidence.

No LLMs. No semantic understanding. No writes to disk. Output is returned
in memory only. Callers decide whether to persist.

Matching pipeline (applied in order, highest confidence first)
--------------------------------------------------------------
1. Exact symbol match (confidence 0.95)
   The responsibility statement contains a token that exactly matches a
   top-level symbol name (function, class, method) in the file.
   e.g. statement "authenticate users" matches `def authenticate(...)`.

2. Multi-keyword match (confidence 0.70)
   Two or more significant words from the responsibility statement appear
   on the same line or within a 5-line window.
   Stopwords and short tokens (< 4 chars) are excluded.

3. Single keyword match (confidence 0.45)
   Exactly one significant word from the statement appears in the file,
   at a line that looks like a definition or annotation.
   Only definition lines are considered (def, class, fn, func, function,
   export, const, type, interface, impl, pub).

A file is skipped (warning emitted) if it cannot be read. A responsibility
with zero matches is returned with an empty anchor list — this is the
expected false-negative case preferred over false positives.

Output schema (each AnchorEntry)
---------------------------------
{
  "pattern":    str,   # the matched text fragment
  "line":       int,   # 1-based line number of the best match
  "end_line":   int,   # last line of the matched block (best effort)
  "symbol":     str,   # top-level symbol name or ""
  "confidence": float, # 0.0–1.0
  "basis":      str    # human-readable explanation of how the match was found
}

AnchorResult (per-responsibility)
---------------------------------
{
  "responsibility_id": str,
  "statement":         str,
  "node_id":           str,
  "anchors":           list[AnchorEntry],   # empty → no match
  "warnings":          list[str]
}

AnchorReport (full pass)
------------------------
{
  "anchors_by_responsibility": dict[responsibility_id, AnchorResult],
  "anchored_count":            int,  # responsibilities with ≥1 anchor
  "unanchored_count":          int,
  "total_responsibilities":    int,
  "warnings":                  list[str]
}
"""

from __future__ import annotations

import re
import warnings as _warnings_mod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from genesis_architect_pro.model_store import ModelResponsibility


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stopwords excluded from keyword matching
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "onto",
    "when", "then", "will", "should", "must", "can", "able", "used",
    "uses", "via", "per", "all", "any", "each", "its", "their",
    "have", "has", "been", "being", "was", "were", "are", "not",
    "also", "both", "only", "more", "such", "over", "out", "about",
    "using", "provide", "provides", "handle", "handles",
})

# Minimum token length for keyword matching
_MIN_TOKEN_LEN: int = 4

# Lines to look ahead/behind for multi-keyword window
_KEYWORD_WINDOW: int = 5

# Definition-line prefixes (across Python, JS/TS, Go, Rust)
_DEF_LINE_RE: re.Pattern = re.compile(
    r"^\s*(def |class |async def |fn |func |function |export |const |"
    r"type |interface |impl |pub fn |pub struct |pub trait |pub enum |"
    r"module |export default |export function |export class )",
    re.IGNORECASE,
)

# Pattern to extract top-level symbol names from definition lines
_SYMBOL_RE: re.Pattern = re.compile(
    r"^\s*(?:async\s+)?(?:pub\s+)?(?:def|class|fn|func|function|"
    r"interface|impl|type|struct|trait|enum|module|const)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# Confidence tiers
_CONF_EXACT_SYMBOL: float = 0.95
_CONF_MULTI_KEYWORD: float = 0.70
_CONF_SINGLE_KEYWORD: float = 0.45


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AnchorEntry:
    pattern: str
    line: int                    # 1-based
    end_line: int                # 1-based; equals line when unknown
    symbol: str                  # "" when not determined
    confidence: float
    basis: str

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "line": self.line,
            "end_line": self.end_line,
            "symbol": self.symbol,
            "confidence": self.confidence,
            "basis": self.basis,
        }


@dataclass
class AnchorResult:
    responsibility_id: str
    statement: str
    node_id: str
    anchors: list[AnchorEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_anchored(self) -> bool:
        return bool(self.anchors)

    @property
    def best_confidence(self) -> float:
        return max((a.confidence for a in self.anchors), default=0.0)

    def to_dict(self) -> dict:
        return {
            "responsibility_id": self.responsibility_id,
            "statement": self.statement,
            "node_id": self.node_id,
            "anchors": [a.to_dict() for a in self.anchors],
            "warnings": self.warnings,
        }


@dataclass
class AnchorReport:
    anchors_by_responsibility: dict[str, AnchorResult] = field(default_factory=dict)
    anchored_count: int = 0
    unanchored_count: int = 0
    total_responsibilities: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "anchors_by_responsibility": {
                rid: r.to_dict()
                for rid, r in self.anchors_by_responsibility.items()
            },
            "anchored_count": self.anchored_count,
            "unanchored_count": self.unanchored_count,
            "total_responsibilities": self.total_responsibilities,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenise(statement: str) -> list[str]:
    """
    Extract significant lowercase tokens from a responsibility statement.

    Strips punctuation, excludes stopwords, excludes tokens shorter than
    _MIN_TOKEN_LEN characters.
    """
    raw = re.sub(r"[^A-Za-z0-9_ ]", " ", statement).lower().split()
    return [
        t for t in raw
        if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS
    ]


def _extract_symbols(lines: list[str]) -> dict[str, int]:
    """
    Return {symbol_name_lower: 1-based_line_number} for all top-level
    definition symbols in the file.
    """
    symbols: dict[str, int] = {}
    for i, line in enumerate(lines, start=1):
        m = _SYMBOL_RE.match(line)
        if m:
            symbols[m.group(1).lower()] = i
    return symbols


def _end_line_of_block(lines: list[str], start: int) -> int:
    """
    Best-effort: scan forward from start (1-based) to find the end of
    the block started there.  Stops at the next top-level definition or
    EOF.  Returns the last non-empty line of the block.
    """
    end = start
    for i in range(start, len(lines)):    # i is 0-based index, line = i+1
        if i == start - 1:
            continue                       # skip the definition line itself
        line = lines[i]
        if _DEF_LINE_RE.match(line) and line.strip():
            break
        if line.strip():
            end = i + 1                   # 1-based
    return max(start, end)


def _anchor_file(
    statement: str,
    tokens: list[str],
    file_path: Path,
    project_dir: Path,
) -> tuple[list[AnchorEntry], list[str]]:
    """
    Attempt to anchor *statement* in *file_path*.

    Returns (anchors, warnings).  Anchors are sorted by confidence DESC.
    Never raises; file read errors are returned as warnings.
    """
    anchors: list[AnchorEntry] = []
    file_warnings: list[str] = []

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        file_warnings.append(f"source_anchor: could not read {file_path}: {exc}")
        return anchors, file_warnings

    lines = text.splitlines()
    rel_path = str(file_path.relative_to(project_dir)) if file_path.is_relative_to(project_dir) else str(file_path)

    # Pre-compute symbol table for this file
    symbols = _extract_symbols(lines)

    # --- Pass 1: Exact symbol match ---
    for token in tokens:
        if token in symbols:
            lineno = symbols[token]
            end = _end_line_of_block(lines, lineno)
            anchors.append(AnchorEntry(
                pattern=token,
                line=lineno,
                end_line=end,
                symbol=token,
                confidence=_CONF_EXACT_SYMBOL,
                basis=f"exact symbol match: '{token}' in {rel_path}:{lineno}",
            ))

    # Stop here if we already have high-confidence anchors
    if anchors:
        return _deduplicate(anchors), file_warnings

    # --- Pass 2: Multi-keyword window match ---
    if len(tokens) >= 2:
        for i, line in enumerate(lines, start=1):
            line_lower = line.lower()
            # Count tokens present in this line
            hits_on_line = [t for t in tokens if t in line_lower]
            if len(hits_on_line) >= 2:
                anchors.append(AnchorEntry(
                    pattern=" ".join(hits_on_line[:3]),
                    line=i,
                    end_line=i,
                    symbol="",
                    confidence=_CONF_MULTI_KEYWORD,
                    basis=(
                        f"multi-keyword match: {hits_on_line[:3]} "
                        f"in {rel_path}:{i}"
                    ),
                ))
                continue

            # Sliding window: check if the token appears across nearby lines
            if hits_on_line:
                window_start = max(0, i - 1 - _KEYWORD_WINDOW)
                window_end   = min(len(lines), i + _KEYWORD_WINDOW)
                window_text  = " ".join(lines[window_start:window_end]).lower()
                window_hits  = [t for t in tokens if t in window_text]
                if len(window_hits) >= 2:
                    anchors.append(AnchorEntry(
                        pattern=" ".join(window_hits[:3]),
                        line=i,
                        end_line=min(i + _KEYWORD_WINDOW, len(lines)),
                        symbol="",
                        confidence=_CONF_MULTI_KEYWORD,
                        basis=(
                            f"multi-keyword window match: {window_hits[:3]} "
                            f"near {rel_path}:{i}"
                        ),
                    ))

    if anchors:
        return _deduplicate(anchors), file_warnings

    # --- Pass 3: Single keyword on a definition line ---
    for i, line in enumerate(lines, start=1):
        if not _DEF_LINE_RE.match(line):
            continue
        line_lower = line.lower()
        hits = [t for t in tokens if t in line_lower]
        if hits:
            sym_match = _SYMBOL_RE.match(line)
            sym = sym_match.group(1) if sym_match else ""
            anchors.append(AnchorEntry(
                pattern=hits[0],
                line=i,
                end_line=_end_line_of_block(lines, i),
                symbol=sym,
                confidence=_CONF_SINGLE_KEYWORD,
                basis=(
                    f"single keyword on definition line: '{hits[0]}' "
                    f"in {rel_path}:{i}"
                ),
            ))

    return _deduplicate(anchors), file_warnings


def _deduplicate(anchors: list[AnchorEntry]) -> list[AnchorEntry]:
    """
    Remove duplicate line references, keeping the highest-confidence entry
    for each (line, symbol) pair. Sort by confidence DESC, then line ASC.
    """
    seen: dict[tuple[int, str], AnchorEntry] = {}
    for a in anchors:
        key = (a.line, a.symbol)
        if key not in seen or a.confidence > seen[key].confidence:
            seen[key] = a
    return sorted(seen.values(), key=lambda a: (-a.confidence, a.line))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def anchor_responsibilities(
    committed: "ArchModel",  # noqa: F821
    project_dir: Path,
    *,
    file_paths: list[str] | None = None,
) -> AnchorReport:
    """
    Scan source files and attempt to anchor each responsibility in the
    committed model to concrete code evidence.

    Parameters
    ----------
    committed : ArchModel
        The committed architecture model. Responsibilities are taken from
        committed.nodes[*].responsibilities.
    project_dir : Path
        Root directory of the project. Source files are resolved relative
        to this path.
    file_paths : list[str] | None
        If provided, only scan these files (relative paths from project_dir).
        If None, derive the file list from committed.nodes (using node IDs
        as file paths — the convention established by sync_model_from_graph).

    Returns
    -------
    AnchorReport
        All results in memory. Nothing is written to disk.
    """
    report = AnchorReport()
    project_dir = Path(project_dir)

    # Determine which files to scan
    if file_paths is not None:
        scan_files = [project_dir / p for p in file_paths]
    else:
        # Node IDs are module paths (set by sync_model_from_graph)
        scan_files = []
        for node in committed.nodes:
            candidate = project_dir / node.id
            scan_files.append(candidate)

    # Index files that actually exist
    existing_files = [f for f in scan_files if f.exists() and f.is_file()]
    missing = [f for f in scan_files if not f.exists() or not f.is_file()]
    for mf in missing:
        report.warnings.append(
            f"source_anchor: file not found, skipping: {mf}"
        )

    # Collect all responsibilities from committed nodes
    responsibilities: list[tuple[str, "ModelResponsibility"]] = []  # (node_id, resp)
    for node in committed.nodes:
        for resp in node.responsibilities:
            responsibilities.append((node.id, resp))

    report.total_responsibilities = len(responsibilities)

    if not responsibilities:
        report.warnings.append(
            "source_anchor: no responsibilities found in committed model"
        )
        return report

    if not existing_files:
        report.warnings.append(
            "source_anchor: no readable source files found; all responsibilities unanchored"
        )
        report.unanchored_count = report.total_responsibilities
        for node_id, resp in responsibilities:
            report.anchors_by_responsibility[resp.id] = AnchorResult(
                responsibility_id=resp.id,
                statement=resp.statement,
                node_id=node_id,
                anchors=[],
                warnings=[],
            )
        return report

    # Anchor each responsibility across all candidate files
    for node_id, resp in responsibilities:
        tokens = _tokenise(resp.statement)
        result = AnchorResult(
            responsibility_id=resp.id,
            statement=resp.statement,
            node_id=node_id,
        )

        if not tokens:
            result.warnings.append(
                f"source_anchor: responsibility '{resp.id}' has no significant "
                f"tokens after stopword removal"
            )
            report.anchors_by_responsibility[resp.id] = result
            report.unanchored_count += 1
            continue

        all_anchors: list[AnchorEntry] = []
        for fpath in existing_files:
            file_anchors, file_warnings = _anchor_file(
                resp.statement, tokens, fpath, project_dir
            )
            all_anchors.extend(file_anchors)
            result.warnings.extend(file_warnings)

        # Keep only the top-3 highest-confidence anchors to avoid noise
        result.anchors = _deduplicate(all_anchors)[:3]

        report.anchors_by_responsibility[resp.id] = result
        if result.is_anchored:
            report.anchored_count += 1
        else:
            report.unanchored_count += 1

    return report


def anchor_from_store(project_dir: Path) -> AnchorReport:
    """
    Load the committed model from *project_dir* and run anchoring.

    Never raises. Errors are collected as warnings in the returned report.
    """
    from genesis_architect_pro.model_store import ModelStore

    project_dir = Path(project_dir)
    report_warnings: list[str] = []

    try:
        store = ModelStore(project_dir)
        committed = store.load_committed()
    except Exception as exc:  # noqa: BLE001
        msg = f"source_anchor: could not load committed model: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        return AnchorReport(warnings=[msg])

    report = anchor_responsibilities(committed, project_dir)
    report.warnings = report_warnings + report.warnings
    return report


@dataclass
class PersistResult:
    """Result of a ``persist_anchors()`` call."""
    added: int = 0          # new source_map entries written
    skipped: int = 0        # entries already present (deduplicated)
    saved: bool = False     # True if save_committed() was actually called
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "added": self.added,
            "skipped": self.skipped,
            "saved": self.saved,
            "warnings": self.warnings,
        }


def persist_anchors(
    report: AnchorReport,
    store: "ModelStore",  # noqa: F821
) -> PersistResult:
    """
    Merge anchors from *report* into the committed model's source_map and
    persist the result via a single ``store.save_committed()`` call.

    Behaviour
    ---------
    - Empty report (total_responsibilities == 0, or no anchored results):
      no-op; returns PersistResult with added=0.
    - Only *anchored* responsibilities (is_anchored == True) are merged.
    - For each anchored responsibility, every AnchorEntry is converted to
      a source_map dict and appended to ``committed.source_map[resp_id]``
      only if an identical entry does not already exist.
    - Existing source_map entries are never removed or modified.
    - ``planned.json`` is never read or written.
    - ``save_committed()`` is called **exactly once** after all merges,
      or not at all if nothing changed.

    Deduplication key
    -----------------
    Two source_map entries are considered identical when their serialised
    (pattern, line, end_line, symbol) quadruple matches, regardless of
    confidence or basis. This lets re-runs of anchoring add updated
    confidence values without creating duplicate line references.

    Parameters
    ----------
    report : AnchorReport
        Result of a prior ``anchor_responsibilities()`` or
        ``anchor_from_store()`` call. Not mutated.
    store : ModelStore
        The ModelStore instance pointing at the target project directory.

    Returns
    -------
    PersistResult
        added       — count of new entries written
        skipped     — count of entries already present (deduplicated)
        warnings    — non-fatal issues encountered
        saved       — True if save_committed() was actually called
    """
    from genesis_architect_pro.model_store import ModelStore as _MS  # noqa: F401

    result = PersistResult()

    # No-op cases
    if not report.anchors_by_responsibility:
        return result
    if not any(r.is_anchored for r in report.anchors_by_responsibility.values()):
        return result

    # Load committed model
    try:
        committed = store.load_committed()
    except Exception as exc:  # noqa: BLE001
        msg = f"persist_anchors: could not load committed model: {exc}"
        _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
        result.warnings.append(msg)
        return result

    # Deduplication helper — identity key excludes confidence/basis so
    # re-running anchoring doesn't duplicate the same line reference.
    def _entry_key(d: dict) -> tuple:
        return (d.get("pattern", ""), d.get("line", 0),
                d.get("end_line", 0), d.get("symbol", ""))

    changed = False

    for resp_id, anchor_result in report.anchors_by_responsibility.items():
        if not anchor_result.is_anchored:
            continue

        existing_entries = committed.source_map.get(resp_id, [])
        existing_keys = {_entry_key(e) for e in existing_entries}

        new_entries: list[dict] = []
        for anchor in anchor_result.anchors:
            entry = anchor.to_dict()
            key = _entry_key(entry)
            if key in existing_keys:
                result.skipped += 1
            else:
                new_entries.append(entry)
                existing_keys.add(key)
                result.added += 1

        if new_entries:
            committed.source_map[resp_id] = existing_entries + new_entries
            changed = True

    if changed:
        try:
            store.save_committed(committed)
            result.saved = True
        except Exception as exc:  # noqa: BLE001
            msg = f"persist_anchors: could not save committed model: {exc}"
            _warnings_mod.warn(msg, RuntimeWarning, stacklevel=2)
            result.warnings.append(msg)

    return result
