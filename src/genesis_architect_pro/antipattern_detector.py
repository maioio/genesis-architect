#!/usr/bin/env python3
"""
antipattern_detector.py - Genesis Architect PRO (advanced extension)

The 4 base detectors (god-class, hub-file, circular-dep, dead-code) live in the
FREE core (genesis_architect.core.antipattern_detector). Pro EXTENDS them - it
does not duplicate them - by adding 3 advanced detectors and confidence
annotations:
  - feature-envy      (module belongs in another package)
  - leaky-abstraction (layer violation)
  - shotgun-surgery   (fragile utility imported by many)

Pro's detect_all delegates to the free core, injecting the advanced detectors
through the `extra_detectors` hook. Base detectors, data model, and reporting
are re-exported from free core - zero duplication.
"""


# Re-export base implementation from free core (data model, base detectors, API).
from genesis_architect.core import antipattern_detector as _base
from genesis_architect.core.antipattern_detector import (  # noqa: F401
    AntiPattern,
    AntiPatternReport,
    GOD_CLASS_FAN_OUT,
    HUB_FILE_FAN_IN,
    LAYER_VIOLATIONS,
    _detect_god_classes,
    _detect_hub_files,
    _detect_circular_deps,
    _detect_dead_code,
    print_report,
)

# Pro thresholds for the advanced detectors.
FEATURE_ENVY_RATIO = 0.65     # >65% imports from one module = feature envy
SHOTGUN_FAN_IN = 8            # utility imported by >8 modules = shotgun risk
MIN_IMPORTS_FOR_ENVY = 4      # minimum imports before feature envy check


# ---------------------------------------------------------------------------
# PRO: confidence annotation
# ---------------------------------------------------------------------------

def _antipattern_confidence(detector_type: str, metrics: dict) -> tuple[float, str]:
    """
    Return (confidence, basis) for a detected anti-pattern.

    confidence: 0.0–1.0. 1.0 = mathematically certain from graph data alone.
    basis: short sentence explaining what the score is based on.
    """
    if detector_type == "god-class":
        fan_out = metrics.get("fan_out", 0)
        threshold = metrics.get("threshold", GOD_CLASS_FAN_OUT)
        excess = fan_out - threshold
        # More excess above threshold = higher confidence
        conf = min(1.0, 0.6 + (excess / max(threshold, 1)) * 0.4)
        return round(conf, 2), f"fan_out={fan_out}, threshold={threshold}, excess={excess}"

    if detector_type == "hub-file":
        fan_in = metrics.get("fan_in", 0)
        threshold = metrics.get("threshold", HUB_FILE_FAN_IN)
        excess = fan_in - threshold
        conf = min(1.0, 0.6 + (excess / max(threshold, 1)) * 0.4)
        return round(conf, 2), f"fan_in={fan_in}, threshold={threshold}, excess={excess}"

    if detector_type == "circular-dep":
        length = metrics.get("cycle_length", 2)
        # Direct A→B→A cycle is unambiguous; longer cycles slightly less so
        conf = 1.0 if length == 2 else 0.92
        return conf, f"cycle_length={length}, deterministic graph cycle"

    if detector_type == "dead-code":
        lines = metrics.get("lines", 0)
        # Zero fan_in is factual; uncertainty comes from dynamic imports
        conf = 0.65 if lines > 100 else 0.80
        basis = f"fan_in=0, lines={lines}"
        if lines > 100:
            basis += "; larger files more likely dynamically imported"
        return conf, basis

    if detector_type == "feature-envy":
        ratio = metrics.get("ratio", 0.0)
        total = metrics.get("total_imports", 0)
        conf = min(1.0, 0.55 + ratio * 0.4 + min(total, 10) / 10 * 0.05)
        return round(conf, 2), f"import_ratio={ratio:.2f}, total_imports={total}"

    if detector_type == "leaky-abstraction":
        src = metrics.get("src_layer", "?")
        dst = metrics.get("dst_layer", "?")
        # Layer violations are definitional once layers are known
        return 0.90, f"layer_violation={src}→{dst}, based on directory heuristic"

    if detector_type == "shotgun-surgery":
        fan_in = metrics.get("fan_in", 0)
        lines = metrics.get("lines", 0)
        conf = min(1.0, 0.65 + min(fan_in - SHOTGUN_FAN_IN, 10) / 10 * 0.20)
        return round(conf, 2), f"fan_in={fan_in}, lines={lines}"

    return 0.75, "static graph analysis"


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# PRO: advanced detectors
# ---------------------------------------------------------------------------

def _detect_feature_envy(modules: dict) -> list[AntiPattern]:
    """Module that imports mostly from one other module - it may belong there."""
    patterns = []
    for mod, data in modules.items():
        imports = data.get("imports", [])
        if len(imports) < MIN_IMPORTS_FOR_ENVY:
            continue

        # Count imports per external module
        from collections import Counter
        counts = Counter(imports)
        top_target, top_count = counts.most_common(1)[0]
        ratio = top_count / len(imports)

        if ratio > FEATURE_ENVY_RATIO:
            metrics = {
                "top_target": top_target,
                "top_count": top_count,
                "total_imports": len(imports),
                "ratio": round(ratio, 2),
            }
            conf, basis = _antipattern_confidence("feature-envy", metrics)
            patterns.append(AntiPattern(
                id=f"feature-envy-{mod.replace('/', '-').replace('.', '-')}",
                type="feature-envy",
                severity="MEDIUM",
                file=mod,
                description=(
                    f"'{mod}' imports {int(ratio*100)}% of its dependencies from '{top_target}'. "
                    f"This module may have feature envy and belong closer to '{top_target}'."
                ),
                metrics=metrics,
                affected_modules=[top_target],
                suggested_fix=(
                    f"Consider moving '{mod}' into the same package as '{top_target}', "
                    f"or extracting shared behaviour into a dedicated module."
                ),
                confidence=conf,
                basis=basis,
            ))
    return patterns


def _detect_leaky_abstractions(modules: dict) -> list[AntiPattern]:
    """Low-layer modules importing from high-layer = architectural inversion."""
    patterns = []
    layer_map = {mod: data.get("layer", "unknown") for mod, data in modules.items()}

    for mod, data in modules.items():
        src_layer = layer_map.get(mod, "unknown")
        for imp in data.get("imports", []):
            dst_layer = layer_map.get(imp, "unknown")
            if src_layer != "unknown" and dst_layer != "unknown":
                if (src_layer, dst_layer) in LAYER_VIOLATIONS:
                    ap_id = f"leaky-{mod.replace('/', '-').replace('.', '-')}-to-{imp.replace('/', '-').replace('.', '-')}"
                    lk_metrics = {"src_layer": src_layer, "dst_layer": dst_layer}
                    conf, basis = _antipattern_confidence("leaky-abstraction", lk_metrics)
                    patterns.append(AntiPattern(
                        id=ap_id,
                        type="leaky-abstraction",
                        severity="HIGH",
                        file=mod,
                        description=(
                            f"Layer violation: '{mod}' ({src_layer}) imports from "
                            f"'{imp}' ({dst_layer}). "
                            f"{src_layer.capitalize()} should not depend on {dst_layer}."
                        ),
                        metrics=lk_metrics,
                        affected_modules=[imp],
                        suggested_fix=(
                            f"Move '{imp}' to a layer that '{mod}' ({src_layer}) is allowed to depend on, "
                            f"or introduce an interface/abstraction that {src_layer} depends on instead."
                        ),
                        confidence=conf,
                        basis=basis,
                    ))
    # Deduplicate by module pair (keep first occurrence per src)
    seen_src: set[str] = set()
    deduped = []
    for p in patterns:
        if p.file not in seen_src:
            deduped.append(p)
            seen_src.add(p.file)
    return deduped[:20]  # cap output


def _detect_shotgun_surgery(modules: dict) -> list[AntiPattern]:
    """
    Utility module imported by many other modules - a change cascades everywhere.
    Different from hub-file: this targets small utility modules, not large central ones.
    """
    patterns = []
    for mod, data in modules.items():
        fi = data.get("fan_in", 0)
        fo = data.get("fan_out", 0)
        lines = data.get("lines", 0)

        # Shotgun: high fan_in, low fan_out (utility, not hub), small file
        if fi > SHOTGUN_FAN_IN and fo <= 3 and lines < 200:
            sg_metrics = {"fan_in": fi, "fan_out": fo, "lines": lines}
            conf, basis = _antipattern_confidence("shotgun-surgery", sg_metrics)
            patterns.append(AntiPattern(
                id=f"shotgun-{mod.replace('/', '-').replace('.', '-')}",
                type="shotgun-surgery",
                severity="MEDIUM",
                file=mod,
                description=(
                    f"'{mod}' is a small utility ({lines} lines, fan_out={fo}) "
                    f"imported by {fi} modules. Any change breaks {fi} dependents."
                ),
                metrics=sg_metrics,
                affected_modules=data.get("imported_by", [])[:10],
                suggested_fix=(
                    f"Stabilise the public API of '{mod}' or split it so dependents "
                    f"import only what they need. Consider a facade pattern."
                ),
                confidence=conf,
                basis=basis,
            ))
    return patterns


# ---------------------------------------------------------------------------
# PRO: detect_all - delegate to free core with advanced detectors injected
# ---------------------------------------------------------------------------

# Adapt (modules) -> (modules, cycles) signature for the extra_detectors hook.
def _envy_adapter(modules, cycles):       # noqa: ARG001
    return _detect_feature_envy(modules)


def _leaky_adapter(modules, cycles):      # noqa: ARG001
    return _detect_leaky_abstractions(modules)


def _shotgun_adapter(modules, cycles):    # noqa: ARG001
    return _detect_shotgun_surgery(modules)


_ADVANCED_DETECTORS = [_envy_adapter, _leaky_adapter, _shotgun_adapter]


def detect_all(project_path, language=None, rebuild_graph=False):
    """Pro detection: base 4 detectors (free core) + 3 advanced (Pro)."""
    return _base.detect_all(
        project_path, language=language, rebuild_graph=rebuild_graph,
        extra_detectors=_ADVANCED_DETECTORS,
    )
