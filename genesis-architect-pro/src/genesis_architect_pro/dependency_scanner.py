"""
Dependency Scanner for Genesis Architect (Pro).

Feeds the Knowledge Graph's cve -> package -> module chain
(knowledge_graph.add_security()) and its do-not-touch risk nodes
(knowledge_graph.add_risks()) with real project data:

  - find_python_dependencies() maps each module to the third-party packages
    it actually imports (reusing the import graph's own extraction/resolution
    so "third-party" means exactly what it means there — anything that isn't
    stdlib and doesn't resolve to a project file).
  - scan_dependency_cves() checks those packages against OSV.dev and returns
    findings in the exact shape add_security() expects.
  - scan_do_not_touch_risks() turns fragility_classifier's VOLATILE modules
    ("do not modify without tests + review") into risk nodes, in the shape
    add_risks() expects.

Python only for now — an honest scope limit (see find_python_dependencies),
not a fabricated result for other languages. Every network call goes through
package_registry.query_osv(), which already degrades to "unavailable" on any
failure rather than raising.
"""

from __future__ import annotations

from pathlib import Path

from genesis_architect_pro.import_graph import (
    _collect_files,
    _extract_python_imports,
    _resolve_module_key,
    detect_language,
    load_or_build,
)
from genesis_architect_pro.stdlib_filter import is_stdlib_import

# Well-known top-level import names whose PyPI distribution name differs —
# OSV.dev indexes by PyPI name, so these need mapping or lookups silently
# miss real vulnerabilities.
_IMPORT_TO_PYPI_NAME = {
    "yaml": "pyyaml", "PIL": "pillow", "cv2": "opencv-python", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "jwt": "pyjwt", "sklearn": "scikit-learn",
    "google": "google-api-python-client",
}


def find_python_dependencies(project_path: str | Path) -> dict[str, set[str]]:
    """Map each Python module (project-relative path) to the third-party
    package names it imports. Returns {} for non-Python projects."""
    root = Path(project_path)
    if detect_language(root) != "python":
        return {}

    graph = load_or_build(root, language="python")
    all_modules = set(graph.get("modules", {})) if isinstance(graph, dict) else set()

    result: dict[str, set[str]] = {}
    for py_file in _collect_files(root, [".py"]):
        try:
            rel = str(py_file.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        packages: set[str] = set()
        for raw in _extract_python_imports(py_file, root):
            top = raw.split(".")[0]
            if not top or is_stdlib_import(top):
                continue
            if _resolve_module_key(raw, py_file, root, "python", all_modules) is not None:
                continue  # resolves to a project file — internal, not third-party
            packages.add(_IMPORT_TO_PYPI_NAME.get(top, top))
        if packages:
            result[rel] = packages
    return result


def scan_dependency_cves(project_path: str | Path, *, max_packages: int = 15) -> list[dict]:
    """Find CVEs for the project's third-party Python dependencies, shaped
    for knowledge_graph.add_security(): [{id, package, modules, confidence}].

    Bounded to max_packages distinct packages (one OSV.dev call each) so this
    stays fast on large dependency trees. Never raises — an OSV lookup
    failure degrades to "no CVEs found" for that package.
    """
    from genesis_architect_pro.package_registry import query_osv

    deps = find_python_dependencies(project_path)
    if not deps:
        return []

    package_to_modules: dict[str, list[str]] = {}
    for module, packages in deps.items():
        for pkg in packages:
            package_to_modules.setdefault(pkg, []).append(module)

    cves: list[dict] = []
    for pkg in sorted(package_to_modules)[:max_packages]:
        try:
            signal = query_osv(pkg, "pypi")
        except Exception:
            continue
        for vuln_id in signal.vuln_ids:
            cves.append({
                "id": vuln_id,
                "package": pkg,
                "modules": package_to_modules[pkg],
                "confidence": 0.9,
            })
    return cves


def scan_do_not_touch_risks(project_path: str | Path) -> list[dict]:
    """VOLATILE modules (fragility_classifier's own "do not modify without
    tests + review" tier) as knowledge-graph risk nodes, shaped for
    knowledge_graph.add_risks(): [{id, label, module, confidence}]."""
    from genesis_architect_pro.fragility_classifier import classify_all

    try:
        report = classify_all(project_path)
    except Exception:
        return []

    return [
        {
            "id": f"do-not-touch:{c.module}",
            "label": f"VOLATILE — do not modify without tests + review ({c.module})",
            "module": c.module,
            "confidence": 0.8,
        }
        for c in report.classifications if c.status == "VOLATILE"
    ]
