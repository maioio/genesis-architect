"""Recovery scan - git history and codebase fragility signals for genesis recover."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)  # noqa: S603
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


def scan(project_dir: Path) -> dict:
    """Run all fragility scans and return combined JSON."""
    hotspots = fix_commit_hotspots(project_dir)
    urls = external_url_count(project_dir)
    versions = version_drift(project_dir)
    dv = doc_version(project_dir)
    dead = dead_file_candidates(project_dir)

    version_drift_detected = len(set(versions.values())) > 1 if versions else False

    return {
        "fix_commit_hotspots": hotspots,
        "external_url_count": urls,
        "version_sources": versions,
        "doc_version": dv,
        "version_drift": version_drift_detected,
        "dead_file_candidates": dead,
    }


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
