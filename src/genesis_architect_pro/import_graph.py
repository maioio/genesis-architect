#!/usr/bin/env python3
"""
import_graph.py - Shared multi-language import graph builder.

Builds a module-to-module adjacency structure from source files.
Used by: drift_detector, architecture_scorer, antipattern_detector,
         fragility_classifier, c4_generator.

Supported languages: Python, JavaScript/TypeScript, Go, Rust.

Output schema (also written to .genesis/import_graph.json):
{
  "language": "python",
  "modules": {
    "src/app.py": {
      "imports": ["src/utils.py", "src/models.py"],
      "imported_by": ["src/main.py"],
      "fan_out": 2,
      "fan_in": 1,
      "lines": 184,
      "is_entry_point": false,
      "layer": "application"
    }
  },
  "cycles": [["src/a.py", "src/b.py", "src/a.py"]],
  "dark_modules": ["src/legacy.py"],
  "entry_points": ["src/main.py"]
}
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IGNORED_DIRS = frozenset({
    "node_modules", "venv", ".venv", "dist", "build",
    ".genesis", "__pycache__", ".pytest_cache", ".ruff_cache",
    "htmlcov", ".mypy_cache", "target", "vendor", ".git",
})

ENTRY_POINT_NAMES = frozenset({
    "main.py", "__main__.py", "cli.py", "app.py", "server.py",
    "index.js", "index.ts", "main.js", "main.ts",
    "main.go", "cmd/main.go",
    "main.rs", "src/main.rs",
})

# Layer detection: directory names mapped to layer label
LAYER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(views?|ui|frontend|presentation|pages|screens|templates|components)\b", re.I), "presentation"),
    (re.compile(r"\b(domain|core|business|logic|entities|models|use.?cases)\b", re.I), "domain"),
    (re.compile(r"\b(service|application|app|handlers|controllers|usecases)\b", re.I), "application"),
    (re.compile(r"\b(infra|infrastructure|adapters|repository|db|database|data|storage|external|integrations)\b", re.I), "infrastructure"),
    (re.compile(r"\b(utils|helpers|common|shared|lib)\b", re.I), "shared"),
    (re.compile(r"\b(tests?|spec|__tests__)\b", re.I), "test"),
]

# Layer violation pairs: (importer_layer, imported_layer) that indicate a violation.
# e.g. infrastructure should not import from presentation.
LAYER_VIOLATIONS: frozenset[tuple[str, str]] = frozenset({
    ("infrastructure", "presentation"),
    ("infrastructure", "application"),
    ("infrastructure", "domain"),
    ("domain", "infrastructure"),
    ("domain", "application"),
    ("domain", "presentation"),
    ("application", "presentation"),
    ("shared", "domain"),
    ("shared", "application"),
    ("shared", "infrastructure"),
    ("shared", "presentation"),
})


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(project_path: Path) -> str:
    """Infer primary language from manifest files."""
    if (project_path / "pyproject.toml").exists() or (project_path / "setup.py").exists() or \
       (project_path / "requirements.txt").exists():
        return "python"
    if (project_path / "package.json").exists():
        return "typescript" if any(project_path.rglob("*.ts")) else "javascript"
    if (project_path / "go.mod").exists():
        return "go"
    if (project_path / "Cargo.toml").exists():
        return "rust"
    # Fallback: count files
    counts = {
        "python": len(list(project_path.rglob("*.py"))),
        "typescript": len(list(project_path.rglob("*.ts"))),
        "javascript": len(list(project_path.rglob("*.js"))),
        "go": len(list(project_path.rglob("*.go"))),
        "rust": len(list(project_path.rglob("*.rs"))),
    }
    return max(counts, key=counts.get) if any(counts.values()) else "python"


# ---------------------------------------------------------------------------
# File collectors
# ---------------------------------------------------------------------------

def _collect_files(project_path: Path, extensions: list[str]) -> list[Path]:
    files = []
    for ext in extensions:
        for p in project_path.rglob(f"*{ext}"):
            if not any(part in IGNORED_DIRS for part in p.parts):
                files.append(p)
    return files


# ---------------------------------------------------------------------------
# Language-specific import extractors
# Returns: list of (source_module_rel, imported_module_raw) tuples
# ---------------------------------------------------------------------------

def _extract_python_imports(py_file: Path, project_path: Path) -> list[str]:
    """Return list of top-level module names imported by this file."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


def _extract_js_ts_imports(src_file: Path, project_path: Path) -> list[str]:
    """Extract import paths from JS/TS files using regex."""
    try:
        source = src_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    imports: list[str] = []
    # import ... from '...'
    for m in re.finditer(r"""(?:import|export)\s+(?:.*?\s+from\s+)?['"]([^'"]+)['"]""", source):
        imports.append(m.group(1))
    # require('...')
    for m in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", source):
        imports.append(m.group(1))
    return imports


def _extract_go_imports(go_file: Path, project_path: Path) -> list[str]:
    """Extract Go import paths."""
    try:
        source = go_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    imports: list[str] = []
    # Single import: import "pkg"
    for m in re.finditer(r'^import\s+"([^"]+)"', source, re.MULTILINE):
        imports.append(m.group(1))
    # Import block: import ( "pkg1" "pkg2" )
    block_m = re.search(r'import\s*\((.*?)\)', source, re.DOTALL)
    if block_m:
        for m in re.finditer(r'"([^"]+)"', block_m.group(1)):
            imports.append(m.group(1))
    return imports


def _extract_rust_imports(rs_file: Path, project_path: Path) -> list[str]:
    """Extract Rust use statements."""
    try:
        source = rs_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    imports: list[str] = []
    for m in re.finditer(r'^use\s+([\w:]+)', source, re.MULTILINE):
        imports.append(m.group(1).split("::")[0])
    for m in re.finditer(r'^extern\s+crate\s+(\w+)', source, re.MULTILINE):
        imports.append(m.group(1))
    return imports


# ---------------------------------------------------------------------------
# Module key normalisation
# Maps a raw import path to a project-relative module key (best-effort)
# ---------------------------------------------------------------------------

def _resolve_module_key(raw_import: str, source_file: Path, project_path: Path,
                         language: str, all_modules: set[str]) -> str | None:
    """
    Try to resolve a raw import string to a project-relative file path.
    Returns None if the import appears to be a third-party/stdlib dependency.
    """
    if language == "python":
        # Relative import or known project package
        pkg_dir = project_path / "src"
        if not pkg_dir.exists():
            pkg_dir = project_path

        candidate_py = pkg_dir / (raw_import.replace(".", "/") + ".py")
        candidate_init = pkg_dir / raw_import.replace(".", "/") / "__init__.py"

        for cand in [candidate_py, candidate_init]:
            if cand.exists():
                try:
                    rel = str(cand.relative_to(project_path))
                    return rel.replace("\\", "/")
                except ValueError:
                    pass

        # Check against known module keys by name match
        raw_top = raw_import.split(".")[0]
        for key in all_modules:
            stem = Path(key).stem
            if stem == raw_top or stem == raw_import:
                return key
        return None

    elif language in ("javascript", "typescript"):
        if not raw_import.startswith("."):
            return None  # third-party
        # Resolve relative path
        try:
            resolved = (source_file.parent / raw_import).resolve()
            # Try with extensions
            for ext in [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"]:
                candidate = Path(str(resolved) + ext) if not resolved.suffix else resolved
                if ext.startswith("/"):
                    candidate = resolved / ("index" + ext.split("/")[1])
                if candidate.exists():
                    rel = str(candidate.relative_to(project_path))
                    return rel.replace("\\", "/")
        except (ValueError, OSError):
            pass
        return None

    elif language == "go":
        # Project-internal imports contain the module path prefix
        # Match against all_modules by suffix
        parts = raw_import.rstrip("/").split("/")
        if len(parts) >= 2:
            suffix = "/".join(parts[-2:])
            for key in all_modules:
                if key.replace("\\", "/").endswith(suffix + ".go") or \
                   key.replace("\\", "/").endswith(suffix + "/"):
                    return key
        return None

    elif language == "rust":
        # Map crate-internal modules to file paths
        for key in all_modules:
            stem = Path(key).stem
            if stem == raw_import:
                return key
        return None

    return None


# ---------------------------------------------------------------------------
# Layer detection
# ---------------------------------------------------------------------------

def _detect_layer(module_path: str) -> str:
    path_str = module_path.replace("\\", "/").lower()
    for pattern, layer in LAYER_PATTERNS:
        if pattern.search(path_str):
            return layer
    return "unknown"


# ---------------------------------------------------------------------------
# Cycle detection (DFS)
# ---------------------------------------------------------------------------

def _find_cycles(adj: dict[str, list[str]]) -> list[list[str]]:
    """Find all simple cycles in directed graph using DFS with colour marking."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adj}
    path: list[str] = []
    cycles: list[list[str]] = []
    found_cycle_roots: set[str] = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbour in adj.get(node, []):
            if neighbour not in color:
                continue
            if color[neighbour] == GRAY:
                # Found a cycle: extract from path
                idx = path.index(neighbour)
                cycle = path[idx:] + [neighbour]
                cycle_key = frozenset(cycle[:-1])
                if cycle_key not in found_cycle_roots:
                    found_cycle_roots.add(cycle_key)
                    cycles.append(cycle)
            elif color[neighbour] == WHITE:
                dfs(neighbour)
        path.pop()
        color[node] = BLACK

    for node in list(adj.keys()):
        if color[node] == WHITE:
            dfs(node)

    return cycles


# ---------------------------------------------------------------------------
# Line counter
# ---------------------------------------------------------------------------

def _count_lines(file_path: Path) -> int:
    try:
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Dark module detection
# ---------------------------------------------------------------------------

def _find_dark_modules(modules: dict, entry_points: list[str]) -> list[str]:
    """Modules with fan_in == 0 that are not entry points."""
    dark = []
    entry_set = set(entry_points)
    for mod, data in modules.items():
        if data["fan_in"] == 0 and mod not in entry_set:
            dark.append(mod)
    return dark


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def build_graph(project_path: str | Path, language: str | None = None,
                save: bool = True) -> dict:
    """
    Build the import graph for a project.

    Args:
        project_path: Root directory of the project.
        language: Override language detection.
        save: Write .genesis/import_graph.json.

    Returns:
        Graph dict with keys: language, modules, cycles, dark_modules, entry_points.
    """
    root = Path(project_path).resolve()

    if language is None:
        language = detect_language(root)

    # Collect source files
    ext_map = {
        "python": [".py"],
        "javascript": [".js", ".jsx"],
        "typescript": [".ts", ".tsx"],
        "go": [".go"],
        "rust": [".rs"],
    }
    extensions = ext_map.get(language, [".py"])
    src_files = _collect_files(root, extensions)

    # Index all module keys
    all_modules_set: set[str] = set()
    file_to_key: dict[Path, str] = {}
    for f in src_files:
        try:
            rel = str(f.relative_to(root)).replace("\\", "/")
            all_modules_set.add(rel)
            file_to_key[f] = rel
        except ValueError:
            pass

    # Extract imports per file
    extractor_map = {
        "python": _extract_python_imports,
        "javascript": _extract_js_ts_imports,
        "typescript": _extract_js_ts_imports,
        "go": _extract_go_imports,
        "rust": _extract_rust_imports,
    }
    extractor = extractor_map.get(language, _extract_python_imports)

    raw_edges: dict[str, list[str]] = {}  # src_key -> [dst_key]
    for f in src_files:
        src_key = file_to_key.get(f)
        if not src_key:
            continue
        raw_imports = extractor(f, root)
        resolved: list[str] = []
        for raw in raw_imports:
            dst = _resolve_module_key(raw, f, root, language, all_modules_set)
            if dst and dst != src_key:
                resolved.append(dst)
        raw_edges[src_key] = list(dict.fromkeys(resolved))  # deduplicate, preserve order

    # Build fan-in / fan-out
    fan_in: dict[str, int] = {k: 0 for k in all_modules_set}
    for src, dsts in raw_edges.items():
        for dst in dsts:
            if dst in fan_in:
                fan_in[dst] += 1

    # Entry points
    entry_points: list[str] = []
    for mod in all_modules_set:
        name = Path(mod).name
        if name in ENTRY_POINT_NAMES or name.startswith("__main__"):
            entry_points.append(mod)
        # Also: fan_in == 0 and has main-like name patterns
        if fan_in.get(mod, 0) == 0 and name in ("main.py", "app.py", "cli.py",
                                                   "index.js", "index.ts"):
            if mod not in entry_points:
                entry_points.append(mod)

    # Assemble modules dict
    modules: dict[str, dict] = {}
    for mod in sorted(all_modules_set):
        f_path = root / mod
        modules[mod] = {
            "imports": raw_edges.get(mod, []),
            "imported_by": [
                src for src, dsts in raw_edges.items() if mod in dsts
            ],
            "fan_out": len(raw_edges.get(mod, [])),
            "fan_in": fan_in.get(mod, 0),
            "lines": _count_lines(f_path),
            "is_entry_point": mod in entry_points,
            "layer": _detect_layer(mod),
        }

    # Find cycles
    adj = {mod: data["imports"] for mod, data in modules.items()}
    cycles = _find_cycles(adj)

    # Dark modules: fan_in == 0 and not entry point
    dark_modules = _find_dark_modules(modules, entry_points)

    graph = {
        "language": language,
        "modules": modules,
        "cycles": cycles,
        "dark_modules": dark_modules,
        "entry_points": entry_points,
        "module_count": len(modules),
        "edge_count": sum(len(v["imports"]) for v in modules.values()),
        "cycle_count": len(cycles),
    }

    if save:
        genesis_dir = root / ".genesis"
        genesis_dir.mkdir(parents=True, exist_ok=True)
        (genesis_dir / "import_graph.json").write_text(
            json.dumps(graph, indent=2), encoding="utf-8"
        )

    return graph


def load_or_build(project_path: str | Path, language: str | None = None,
                  force_rebuild: bool = False) -> dict:
    """Load cached graph from .genesis/import_graph.json or rebuild."""
    root = Path(project_path).resolve()
    cache_path = root / ".genesis" / "import_graph.json"

    if not force_rebuild and cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return build_graph(root, language=language, save=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Genesis - Import Graph Builder")
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--language", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    graph = load_or_build(args.project_path, language=args.language,
                          force_rebuild=args.rebuild)

    if args.json:
        print(json.dumps(graph, indent=2))
    else:
        print(f"Language: {graph['language']}")
        print(f"Modules:  {graph['module_count']}")
        print(f"Edges:    {graph['edge_count']}")
        print(f"Cycles:   {graph['cycle_count']}")
        print(f"Dark:     {len(graph['dark_modules'])}")
        if graph["cycles"]:
            print("\nCycles detected:")
            for c in graph["cycles"][:5]:
                print(f"  {' -> '.join(c)}")
        if graph["dark_modules"]:
            print(f"\nDark modules (fan_in=0, not entry point): {len(graph['dark_modules'])}")
            for d in graph["dark_modules"][:5]:
                print(f"  {d}")


if __name__ == "__main__":
    main()
