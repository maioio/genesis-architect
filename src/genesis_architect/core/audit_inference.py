"""Genesis audit - infer project purpose from existing files, zero friction."""

import json
import re
from pathlib import Path


def infer_project_context(project_path: str | Path) -> dict:
    """
    Silently read README.md, package.json, pyproject.toml, or go.mod
    to extract project name + description.

    Returns {"name": ..., "description": ...} or empty strings if not found.
    """
    root = Path(project_path)
    name = ""
    description = ""

    # pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if m:
            name = m.group(1)
        m = re.search(r'^description\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if m:
            description = m.group(1)

    # package.json
    if not name:
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                name = data.get("name", "")
                description = data.get("description", "")
            except (json.JSONDecodeError, OSError):
                pass

    # go.mod
    if not name:
        gomod = root / "go.mod"
        if gomod.exists():
            text = gomod.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
            if m:
                name = m.group(1).split("/")[-1]

    # README.md - grab first non-empty line as description fallback
    if not description:
        readme = root / "README.md"
        if readme.exists():
            skip_heading = True
            for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    skip_heading = False
                    continue
                if skip_heading:
                    continue
                clean = stripped.lstrip("#").strip()
                if clean and not clean.startswith("!"):
                    description = clean[:200]
                    break

    return {"name": name, "description": description}


def get_vision(project_path: str | Path, ask_fn) -> str:
    """
    Return the project vision string. Infers from files first.
    Only prompts the user if inference fails.
    """
    ctx = infer_project_context(project_path)
    if ctx["description"]:
        return ctx["description"]
    return ask_fn("Describe what this project does: ")
