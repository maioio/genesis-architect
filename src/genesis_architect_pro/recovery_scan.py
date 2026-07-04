"""Recovery scan - git history and codebase fragility signals for genesis recover."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        # encoding+errors: git output is UTF-8; without this text=True decodes
        # with the OS locale (cp1252 on Windows) and crashes on non-Latin-1 bytes.
        result = subprocess.run(cmd, capture_output=True, text=True,  # noqa: S603
                                encoding="utf-8", errors="replace",
                                cwd=cwd, timeout=30)
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def fix_commit_hotspots(project_dir: Path, top_n: int = 10) -> dict[str, int]:
    """Return files ranked by number of fix-related commits touching them."""
    out = _run(["git", "log", "--grep=fix", "--stat", "--pretty="], project_dir)  # noqa: S607
    counts: dict[str, int] = {}
    for line in out.splitlines():
        # stat lines look like: " path/to/file.py | 5 +++--"
        if "|" in line:
            path = line.split("|")[0].strip()
            if path:
                counts[path] = counts.get(path, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n])


def external_url_count(project_dir: Path) -> dict[str, int]:
    """Count hardcoded URL strings per file (fragility signal)."""
    url_re = re.compile(r'https?://[^\s\'"]{10,}')
    counts: dict[str, int] = {}
    for f in project_dir.rglob("*"):
        if not f.is_file():
            continue
        if any(part in f.parts for part in (".git", "node_modules", "__pycache__", ".venv", "venv")):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n = len(url_re.findall(text))
        if n > 0:
            counts[str(f.relative_to(project_dir))] = n
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def version_drift(project_dir: Path) -> dict[str, str]:
    """Check for version mismatches between common version sources."""
    sources: dict[str, str] = {}
    for candidate in ["package.json", "pyproject.toml", "manifest.json", "setup.cfg"]:
        p = project_dir / candidate
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'"version"\s*:\s*"([^"]+)"', text) or re.search(r"version\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            sources[candidate] = m.group(1)
    return sources


def doc_version(project_dir: Path) -> str | None:
    """Extract version from README or CHANGELOG."""
    for candidate in ["README.md", "CHANGELOG.md"]:
        p = project_dir / candidate
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"v(\d+\.\d+[\.\d]*)", text)
        if m:
            return m.group(1)
    return None


def dead_file_candidates(project_dir: Path) -> list[str]:
    """Find files not imported by anything in the project (rough heuristic)."""
    all_source: list[Path] = []
    for ext in ("*.js", "*.ts", "*.py", "*.mjs"):
        all_source.extend(
            f for f in project_dir.rglob(ext)
            if not any(part in f.parts for part in (".git", "node_modules", "__pycache__", ".venv", "venv", "dist"))
        )

    all_text = ""
    for f in all_source:
        try:
            all_text += f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    dead: list[str] = []
    for f in all_source:
        stem = f.stem
        # Skip index/main/test files - they're entry points, not dead
        if stem in ("index", "main", "__init__", "setup", "conftest"):
            continue
        if stem.startswith("test_") or stem.endswith("_test") or stem.endswith(".test"):
            continue
        # Check if stem appears anywhere in other files' import/require statements
        pattern = f'["\'/]{stem}["\'/]'
        if not re.search(pattern, all_text.replace(f.read_text(encoding="utf-8", errors="ignore") if f.exists() else "", "", 1)):
            dead.append(str(f.relative_to(project_dir)))

    return dead[:20]  # cap at 20 to avoid noise


def sync_model_from_graph(project_dir: Path, graph: dict) -> dict:
    """
    Populate `.genesis/model.json` from the current import graph.

    Behaviour
    ---------
    - If `model.json` does not exist, create it with one ModelNode per module
      in the graph (kind="component", name=relative path).
    - If `model.json` already has nodes that came from graph sync (vagrant=False,
      kind="component"), leave it untouched — the user may have authored it.
    - Never touch `planned.json`.
    - On any error (corrupt file, I/O failure), emit a warning and return a
      status dict with ``synced=False`` and the warning message; the caller
      continues normally.

    Returns a status dict with keys:
      synced (bool)        — True if model.json was written this call
      node_count (int)     — nodes in the committed model after the call
      diverged (bool)      — True if planned.json exists and differs from committed
      warning (str | None) — non-fatal warning message, or None
    """
    try:
        from genesis_architect_pro.model_store import (
            ModelStore, ModelNode,
        )

        store = ModelStore(project_dir)

        # Load current committed model (empty ArchModel if missing)
        try:
            committed = store.load_committed()
        except Exception as exc:  # noqa: BLE001
            msg = f"ModelStore: could not load committed model: {exc}"
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
            return {"synced": False, "node_count": 0, "diverged": False, "warning": msg}

        synced = False
        modules: dict = graph.get("modules", {})

        # Only auto-populate on first run (no existing nodes)
        if not committed.nodes and modules:
            language = graph.get("language", "unknown")
            for mod_path, mod_data in modules.items():
                node = ModelNode(
                    id=mod_path,
                    kind="component",
                    name=mod_path,
                    technology=language,
                    description=(
                        f"fan_in={mod_data.get('fan_in', 0)}, "
                        f"fan_out={mod_data.get('fan_out', 0)}, "
                        f"lines={mod_data.get('lines', 0)}"
                    ),
                    # vagrant=False: these are committed (code-backed) observations
                    vagrant=False,
                )
                committed.nodes.append(node)

            try:
                store.save_committed(committed)
                synced = True
            except Exception as exc:  # noqa: BLE001
                msg = f"ModelStore: could not save committed model: {exc}"
                warnings.warn(msg, RuntimeWarning, stacklevel=2)
                return {
                    "synced": False,
                    "node_count": len(committed.nodes),
                    "diverged": False,
                    "warning": msg,
                }

        # Check divergence (cheap structural signature comparison)
        try:
            diverged = store.is_planned_diverged()
        except Exception:  # noqa: BLE001
            diverged = False

        return {
            "synced": synced,
            "node_count": len(committed.nodes),
            "diverged": diverged,
            "warning": None,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"ModelStore integration error (recovery continues): {exc}"
        warnings.warn(msg, RuntimeWarning, stacklevel=2)
        return {"synced": False, "node_count": 0, "diverged": False, "warning": str(exc)}


def scan(project_dir: Path) -> dict:
    """Run all Recovery Intelligence engines and return a combined result dict.

    Returned keys
    -------------
    fix_commit_hotspots   dict[str, int]  — files ranked by fix-commit frequency
    external_url_count    dict[str, int]  — files ranked by hardcoded URL count
    version_sources       dict[str, str]  — version string per manifest file
    doc_version           str | None      — version extracted from README/CHANGELOG
    version_drift         bool            — True when manifest versions disagree
    dead_file_candidates  list[str]       — files with no detected import references
    model_sync            dict            — result of syncing committed model from graph
    model_diff            dict            — structural diff between committed and planned
    drift_flags           dict            — vagrant + stale candidates from drift_detector
    source_anchors        dict            — responsibility → code-location mappings
    anchor_persist_result dict            — result of persisting new anchors to model_store
    architecture_score    float | None    — 0-100 score from architecture_scorer
    architecture_profile  str             — adaptive profile used for scoring
    anti_patterns         list[dict]      — detected anti-patterns (kind/file/confidence/severity/basis)
    drift_score           dict            — numeric drift score with per-node breakdown
    recovery_report       dict            — full RecoveryReport.to_dict() output

    All keys are always present. Every engine is wrapped in try/except; failures
    surface as warning strings inside the relevant sub-dict rather than exceptions.
    """
    hotspots = fix_commit_hotspots(project_dir)
    urls = external_url_count(project_dir)
    versions = version_drift(project_dir)
    dv = doc_version(project_dir)
    dead = dead_file_candidates(project_dir)

    version_drift_detected = len(set(versions.values())) > 1 if versions else False

    # Model sync — additive, never raises; failures surface in model_sync["warning"]
    try:
        from genesis_architect_pro.import_graph import load_or_build
        graph = load_or_build(project_dir)
        model_sync = sync_model_from_graph(project_dir, graph)
    except Exception as exc:  # noqa: BLE001
        model_sync = {
            "synced": False, "node_count": 0, "diverged": False,
            "warning": f"model sync skipped: {exc}",
        }

    # Model diff — additive, never raises
    try:
        from genesis_architect_pro.model_store import ModelStore
        _store = ModelStore(project_dir)
        model_diff = _store.model_diff().to_dict()
    except Exception as exc:  # noqa: BLE001
        model_diff = {
            "has_changes": False, "summary": f"diff skipped: {exc}",
            "added_nodes": [], "removed_nodes": [], "changed_nodes": [],
            "added_links": [], "removed_links": [], "changed_links": [],
            "responsibility_changes": [],
        }

    # Drift flags — additive, read-only, never raises
    try:
        from genesis_architect_pro.drift_detector import compute_drift_flags
        drift_flags = compute_drift_flags(project_dir).to_dict()
    except Exception as exc:  # noqa: BLE001
        drift_flags = {
            "vagrant_candidates": [],
            "stale_candidates": [],
            "confidence": 0.0,
            "basis": f"drift detection skipped: {exc}",
            "warnings": [],
        }

    # Architecture score — additive, read-only, never raises
    try:
        from genesis_architect_pro.architecture_scorer import score_project
        _arch = score_project(project_dir)
        architecture_score = _arch.get("total")
        architecture_profile = _arch.get("profile", "default")
    except Exception:  # noqa: BLE001
        architecture_score = None
        architecture_profile = "default"

    # Anti-pattern detection — additive, read-only, never raises
    try:
        from genesis_architect_pro.antipattern_detector import detect_all
        _ap_report = detect_all(project_dir)
        anti_patterns = [
            {
                "kind": ap.type,
                "file": ap.file,
                "confidence": getattr(ap, "confidence", 0.60),
                "severity": ap.severity.lower() if ap.severity else "medium",
                "basis": getattr(ap, "basis", "static analysis"),
            }
            for ap in (getattr(_ap_report, "patterns", []) or [])
        ]
    except Exception:  # noqa: BLE001
        anti_patterns = []

    # Source anchoring — compute object first so it can be optionally persisted below
    _anchor_report = None
    try:
        from genesis_architect_pro.source_anchor import anchor_from_store
        _anchor_report = anchor_from_store(project_dir)
        source_anchors = _anchor_report.to_dict()
    except Exception as exc:  # noqa: BLE001
        source_anchors = {
            "anchors_by_responsibility": {},
            "anchored_count": 0,
            "unanchored_count": 0,
            "total_responsibilities": 0,
            "warnings": [f"source anchoring skipped: {exc}"],
        }

    # Persist source anchors — safe, additive, never raises.
    # Only writes when new anchors are found; idempotent on re-run.
    anchor_persist_result: dict = {"added": 0, "skipped": 0, "saved": False, "warnings": []}
    try:
        if _anchor_report is not None and _anchor_report.total_responsibilities > 0:
            from genesis_architect_pro.model_store import ModelStore as _MS
            from genesis_architect_pro.source_anchor import persist_anchors as _pa
            _persist_result = _pa(_anchor_report, _MS(project_dir))
            anchor_persist_result = _persist_result.to_dict()
    except Exception as exc:  # noqa: BLE001
        anchor_persist_result["warnings"].append(f"anchor persistence skipped: {exc}")

    # Decay forecast — optional temporal signal fed into drift scorer.
    # Requires ≥3 historical score records; absent forecast is not an error.
    _decay_forecast = None
    try:
        from genesis_architect_pro.architecture_scorer import load_score_history
        from genesis_architect_pro.decay_regressor import forecast_from_history
        _history = load_score_history(project_dir)
        if len(_history) >= 3:
            _decay_forecast = forecast_from_history(_history)
    except Exception:  # noqa: BLE001
        pass

    # Drift score — additive, read-only, never raises
    try:
        from genesis_architect_pro.drift_scorer import compute_drift_score
        drift_score = compute_drift_score(project_dir, forecast=_decay_forecast).to_dict()
    except Exception as exc:  # noqa: BLE001
        drift_score = {
            "overall_score": 0.0,
            "risk_level": "none",
            "confidence": 0.0,
            "basis": f"drift scoring skipped: {exc}",
            "per_node_scores": [],
            "top_risk_nodes": [],
            "warnings": [],
        }

    scan_result = {
        "fix_commit_hotspots": hotspots,
        "external_url_count": urls,
        "version_sources": versions,
        "doc_version": dv,
        "version_drift": version_drift_detected,
        "dead_file_candidates": dead,
        "model_sync": model_sync,
        "model_diff": model_diff,
        "drift_flags": drift_flags,
        "source_anchors": source_anchors,
        "anchor_persist_result": anchor_persist_result,
        "architecture_score": architecture_score,
        "architecture_profile": architecture_profile,
        "anti_patterns": anti_patterns,
        "drift_score": drift_score,
    }

    # Recovery report — additive, read-only, never raises
    try:
        from genesis_architect_pro.recovery_report import generate_report
        scan_result["recovery_report"] = generate_report(scan_result).to_dict()
    except Exception as exc:  # noqa: BLE001
        scan_result["recovery_report"] = {
            "executive_summary": f"report generation skipped: {exc}",
            "project_risk_level": "none",
            "warnings": [str(exc)],
        }

    return scan_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis recovery scanner")
    parser.add_argument("project_dir", nargs="?", default=".", help="Path to project root")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: {project_dir} is not a directory", file=sys.stderr)
        return 1

    result = scan(project_dir)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Fix commit hotspots: {result['fix_commit_hotspots']}")
        print(f"Files with external URLs: {len(result['external_url_count'])}")
        print(f"Version sources: {result['version_sources']}")
        print(f"Version drift: {result['version_drift']}")
        print(f"Dead file candidates: {len(result['dead_file_candidates'])}")

    return 0
