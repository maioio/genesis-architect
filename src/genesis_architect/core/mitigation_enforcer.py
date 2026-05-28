#!/usr/bin/env python3
"""
mitigation_enforcer.py - Genesis Architect v2.6.0

Hard enforcement of mitigation_file_path rules from PITFALLS.md.

Enforcement hierarchy (applied in order, stops at first definitive result):
  1. FILE EXISTENCE   - the mitigation file must exist on disk.
  2. AST PARSE        - the file must be valid Python (if .py). An empty or
                        stub-only file fails this check.
  3. SYMBOL CHECK     - if mitigation_symbol is specified in PITFALLS.md, the
                        named function/class must exist in the file's AST.
  4. IMPORT CHECK     - if mitigation_import is specified, the named module
                        must be importable from the file (detected via AST
                        import nodes, no actual import executed).
  5. NON-EMPTY CHECK  - file must contain at least one non-comment, non-blank
                        line of real code (guards against empty stub files).

Unlike pitfall_coverage_check.py (keyword grepping, advisory),
this script fails mechanically. Exit 1 = hard block.

Usage:
    python scripts/mitigation_enforcer.py PITFALLS.md --src-root .
    python scripts/mitigation_enforcer.py PITFALLS.md --src-root . --json
    python scripts/mitigation_enforcer.py PITFALLS.md --src-root . --strict

PITFALLS.md optional fields per pitfall block:
    mitigation_file_path: src/myapp/utils/security.py   (required)
    mitigation_symbol: safe_filename                     (optional: function/class name)
    mitigation_import: pathlib                           (optional: import that must exist)

Exit codes:
    0 - all enforcement checks pass
    1 - one or more checks failed (enforcement failure)
    2 - bad arguments or unreadable files
"""

import ast
import json
import re
import sys
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_pitfalls_from_md(pitfalls_path: Path) -> list[dict]:
    """
    Parse pitfalls directly from PITFALLS.md.

    Recognises these fields per pitfall block:
        mitigation_file_path: src/...   (required for enforcement)
        mitigation_symbol: func_or_class (optional: AST symbol check)
        mitigation_import: module_name   (optional: AST import check)

    Returns list of dicts.
    """
    text = pitfalls_path.read_text(encoding="utf-8")
    pitfalls: list[dict] = []

    sections = re.split(r"(?m)^## (Pitfall \d+[^\n]*)\n", text)
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        num_m = re.search(r"Pitfall\s+(\d+)", header, re.IGNORECASE)
        pid = f"pitfall_{num_m.group(1)}" if num_m else f"pitfall_{(i+1)//2}"
        name = re.sub(r"^Pitfall\s+\d+[:\s]*", "", header, flags=re.IGNORECASE).strip()

        path_m = re.search(r"mitigation_file_path\s*:\s*([^\n]+)", body)
        symbol_m = re.search(r"mitigation_symbol\s*:\s*([^\n]+)", body)
        import_m = re.search(r"mitigation_import\s*:\s*([^\n]+)", body)
        url_m = re.search(r"https://github\.com/[^\s,)\]>\"']+/issues/\d+", body)

        pitfalls.append({
            "id": pid,
            "name": name,
            "mitigation_file_path": path_m.group(1).strip() if path_m else "",
            "mitigation_symbol": symbol_m.group(1).strip() if symbol_m else "",
            "mitigation_import": import_m.group(1).strip() if import_m else "",
            "issue_url": url_m.group(0) if url_m else "",
        })

    return pitfalls


def _load_from_evidence(evidence_json: Path) -> list[dict]:
    """Load pitfall list from .genesis/evidence.json if present."""
    if not evidence_json.exists():
        return []
    try:
        data = json.loads(evidence_json.read_text(encoding="utf-8"))
        return data.get("pitfalls", [])
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# AST-level checks (Python files only)
# ---------------------------------------------------------------------------

def _ast_parse(source: str) -> ast.Module | None:
    """Return parsed AST or None if the source is invalid Python."""
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _is_substantive(source: str) -> bool:
    """
    Return True if the file contains at least one non-trivial statement.
    Guards against stub files that are all comments and pass/... stubs.
    """
    tree = _ast_parse(source)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (
            ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.Assign, ast.AugAssign, ast.AnnAssign,
            ast.Return, ast.Raise, ast.Assert,
            ast.Import, ast.ImportFrom,
        )):
            # A function/class body of only Pass or Ellipsis is not substantive
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if all(isinstance(s, (ast.Pass, ast.Expr)) and
                       (isinstance(s, ast.Pass) or
                        isinstance(getattr(s, 'value', None), ast.Constant))
                       for s in body):
                    continue
            return True
    return False


def _symbol_exists(source: str, symbol: str) -> bool:
    """
    Return True if a top-level function or class named `symbol` exists in the AST.
    Also checks for module-level assignments (e.g. CONSTANT = ...).
    """
    tree = _ast_parse(source)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    return True
    return False


def _import_exists(source: str, module_name: str) -> bool:
    """
    Return True if the file imports `module_name` anywhere (import or from-import).
    Does NOT execute the import - purely AST-level.
    """
    tree = _ast_parse(source)
    if tree is None:
        return False
    top = module_name.split(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_name or alias.name.startswith(top + "."):
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == module_name or
                                node.module.startswith(top + ".")):
                return True
    return False


def _check_python_file(
    path: Path,
    symbol: str = "",
    import_name: str = "",
    strict: bool = False,
) -> list[str]:
    """
    Run AST-level checks on a Python file.

    Returns a list of error strings (empty = all checks passed).
    """
    errors: list[str] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"Cannot read file: {exc}"]

    # 1. Parse check
    if _ast_parse(source) is None:
        errors.append(f"SyntaxError: {path} is not valid Python - mitigation is broken code")
        return errors  # remaining checks meaningless

    # 2. Non-empty / non-stub check (always on)
    if not _is_substantive(source):
        errors.append(
            f"Stub-only: {path} contains no substantive code "
            "(only pass/..., comments, or bare docstrings)"
        )

    # 3. Symbol check (optional, only when specified)
    if symbol and not _symbol_exists(source, symbol):
        errors.append(
            f"Symbol missing: '{symbol}' not found in {path} "
            f"(expected function, class, or assignment named '{symbol}')"
        )

    # 4. Import check (optional, only when specified)
    if import_name and not _import_exists(source, import_name):
        errors.append(
            f"Import missing: '{import_name}' not imported in {path}"
        )

    return errors


# ---------------------------------------------------------------------------
# Core enforcement logic
# ---------------------------------------------------------------------------

def _resolve_mitigation_path(raw_path: str, project_root: Path) -> Path | None:
    """
    Resolve a mitigation_file_path relative to project_root.
    Returns the Path if it exists, None otherwise.

    The path in PITFALLS.md is always written relative to the project root
    (e.g., 'src/myapp/utils/security.py'), never absolute.
    """
    if not raw_path:
        return None
    candidate = (project_root / raw_path).resolve()
    # Security: must stay inside project root
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


class EnforcementResult:
    def __init__(self) -> None:
        self.passed: list[dict] = []
        self.failed: list[dict] = []
        self.unmapped: list[dict] = []

    @property
    def ok(self) -> bool:
        return not self.failed and not self.unmapped

    def summary(self) -> str:
        total = len(self.passed) + len(self.failed) + len(self.unmapped)
        return (
            f"Mitigations: {len(self.passed)}/{total} present | "
            f"missing: {len(self.failed)} | unmapped: {len(self.unmapped)}"
        )


def enforce(
    pitfalls: list[dict],
    project_root: Path,
    strict: bool = False,
) -> EnforcementResult:
    """
    For each pitfall, run the full enforcement hierarchy:

      1. File existence (always required)
      2. AST parse validity (Python .py files only)
      3. Non-stub check: file must contain real code
      4. Symbol check: mitigation_symbol must exist in AST (if specified)
      5. Import check: mitigation_import must be present in AST (if specified)

    Pitfalls with no mitigation_file_path go to 'unmapped' (separate category).
    """
    result = EnforcementResult()

    for p in pitfalls:
        pid = p.get("id", "?")
        name = p.get("name", "?")
        raw_path = p.get("mitigation_file_path", "").strip()
        symbol = p.get("mitigation_symbol", "").strip()
        import_name = p.get("mitigation_import", "").strip()

        if not raw_path:
            result.unmapped.append({
                "id": pid,
                "name": name,
                "reason": "No mitigation_file_path in PITFALLS.md - add one before Phase 6",
            })
            continue

        resolved = _resolve_mitigation_path(raw_path, project_root)
        if resolved is None:
            result.failed.append({
                "id": pid,
                "name": name,
                "mitigation_file_path": raw_path,
                "reason": f"File not found: {raw_path}",
            })
            continue

        # File exists - now run deeper checks for Python files
        ast_errors: list[str] = []
        if resolved.suffix == ".py":
            ast_errors = _check_python_file(
                resolved,
                symbol=symbol,
                import_name=import_name,
                strict=strict,
            )

        if ast_errors:
            result.failed.append({
                "id": pid,
                "name": name,
                "mitigation_file_path": raw_path,
                "reason": "; ".join(ast_errors),
            })
        else:
            entry: dict = {
                "id": pid,
                "name": name,
                "mitigation_file_path": raw_path,
                "resolved": str(resolved),
            }
            if symbol:
                entry["symbol_verified"] = symbol
            if import_name:
                entry["import_verified"] = import_name
            result.passed.append(entry)

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_report(result: EnforcementResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "passed": result.passed,
            "failed": result.failed,
            "unmapped": result.unmapped,
            "ok": result.ok,
            "summary": result.summary(),
        }, indent=2))
        return

    print(result.summary(), file=sys.stderr)
    for p in result.passed:
        print(f"  [OK]      {p['id']}: {p['mitigation_file_path']}", file=sys.stderr)
    for f in result.failed:
        print(f"  [MISSING] {f['id']}: {f['mitigation_file_path']}", file=sys.stderr)
        print(f"            {f['reason']}", file=sys.stderr)
    for u in result.unmapped:
        print(f"  [UNMAPPED]{u['id']}: {u['name']}", file=sys.stderr)
        print(f"            {u['reason']}", file=sys.stderr)


def _print_failure_guidance(result: EnforcementResult) -> None:
    """Print actionable fix instructions on failure."""
    if result.failed:
        print("\nFix required:", file=sys.stderr)
        for f in result.failed:
            print(
                f"  Create '{f['mitigation_file_path']}' with the mitigation code for {f['id']}.",
                file=sys.stderr,
            )
    if result.unmapped:
        print("\nAdd mitigation_file_path to these pitfalls in PITFALLS.md:", file=sys.stderr)
        for u in result.unmapped:
            print(f"  ## {u['name']}", file=sys.stderr)
            print(f"  mitigation_file_path: src/<package>/utils/<module>.py", file=sys.stderr)
    print(
        "\nRe-run after fixing:\n"
        "  python scripts/mitigation_enforcer.py PITFALLS.md --src-root src/",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect - Mitigation Enforcer\n"
                    "Hard-checks that every mitigation_file_path in PITFALLS.md exists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pitfalls_md",
        help="Path to PITFALLS.md",
    )
    parser.add_argument(
        "--src-root",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--from-evidence",
        action="store_true",
        help="Load pitfalls from .genesis/evidence.json instead of parsing PITFALLS.md",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="(Reserved for future stricter checks; currently same as default)",
    )
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help=(
            "Treat unmapped pitfalls (no mitigation_file_path) as warnings, not failures. "
            "Exit 1 only on 'failed' (file missing or stub-only). "
            "Use in CI when some mitigations are config-file-based (e.g. pyproject.toml pins)."
        ),
    )

    args = parser.parse_args()

    pitfalls_path = Path(args.pitfalls_md)
    project_root = Path(args.src_root).resolve()

    if not pitfalls_path.exists():
        print(f"ERROR: {pitfalls_path} not found", file=sys.stderr)
        sys.exit(2)
    if not project_root.is_dir():
        print(f"ERROR: --src-root {project_root} is not a directory", file=sys.stderr)
        sys.exit(2)

    # Load pitfall list
    if args.from_evidence:
        evidence_json = project_root / ".genesis" / "evidence.json"
        pitfalls = _load_from_evidence(evidence_json)
        if not pitfalls:
            print(
                "WARNING: --from-evidence specified but .genesis/evidence.json is missing "
                "or has no pitfalls. Falling back to PITFALLS.md parser.",
                file=sys.stderr,
            )
            pitfalls = _parse_pitfalls_from_md(pitfalls_path)
    else:
        pitfalls = _parse_pitfalls_from_md(pitfalls_path)

    if not pitfalls:
        print("WARNING: No pitfalls parsed from PITFALLS.md", file=sys.stderr)
        sys.exit(0)

    result = enforce(pitfalls, project_root, strict=args.strict)
    _print_report(result, as_json=args.json)

    # Determine failure: always fail on 'failed'; fail on unmapped unless --allow-unmapped
    has_failure = bool(result.failed) or (result.unmapped and not args.allow_unmapped)
    if has_failure:
        _print_failure_guidance(result)
        sys.exit(1)

    if not args.json:
        if result.unmapped and args.allow_unmapped:
            print(
                f"Mitigation enforcement: PASSED ({len(result.unmapped)} unmapped pitfall(s) "
                "allowed via --allow-unmapped - add mitigation_file_path when files exist)",
                file=sys.stderr,
            )
        else:
            print("Mitigation enforcement: PASSED", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
