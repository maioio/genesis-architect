#!/usr/bin/env python3
"""
scaffold_generator.py - Genesis Architect
Creates project folder structure based on language and architecture tier.
No external dependencies required (stdlib only).

Usage:
  python scripts/scaffold_generator.py --language typescript --tier minimalist --name my-project
  python scripts/scaffold_generator.py --language python --tier scalable --name my-service
"""

import os
import re
import sys
import argparse
from pathlib import Path

STRUCTURES = {
    "typescript": {
        "minimalist": [
            "src/index.ts",
            "src/core.ts",
            "src/utils.ts",
            "tests/core.test.ts",
            ".github/workflows/ci.yml",
            ".env.example",
            "package.json",
            "tsconfig.json",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
        "scalable": [
            "src/index.ts",
            "src/domain/.gitkeep",
            "src/services/.gitkeep",
            "src/infrastructure/.gitkeep",
            "src/config/index.ts",
            "tests/unit/.gitkeep",
            "tests/integration/.gitkeep",
            ".github/workflows/ci.yml",
            ".env.example",
            "package.json",
            "tsconfig.json",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
    },
    "python": {
        "minimalist": [
            "src/{name}/__init__.py",
            "src/{name}/main.py",
            "src/{name}/core.py",
            "src/{name}/utils.py",
            "tests/__init__.py",
            "tests/test_core.py",
            ".github/workflows/ci.yml",
            ".env.example",
            "pyproject.toml",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
        "scalable": [
            "src/{name}/__init__.py",
            "src/{name}/domain/.gitkeep",
            "src/{name}/services/.gitkeep",
            "src/{name}/adapters/.gitkeep",
            "src/{name}/config.py",
            "tests/unit/.gitkeep",
            "tests/integration/.gitkeep",
            ".github/workflows/ci.yml",
            ".env.example",
            "pyproject.toml",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
    },
    "go": {
        "minimalist": [
            "cmd/main.go",
            "internal/core/core.go",
            "internal/utils/utils.go",
            "internal/core/core_test.go",
            ".github/workflows/ci.yml",
            ".env.example",
            "go.mod",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
        "scalable": [
            "cmd/main.go",
            "internal/domain/.gitkeep",
            "internal/service/.gitkeep",
            "internal/repository/.gitkeep",
            "pkg/config/config.go",
            "tests/unit/.gitkeep",
            "tests/integration/.gitkeep",
            ".github/workflows/ci.yml",
            ".env.example",
            "go.mod",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
    },
    "rust": {
        "minimalist": [
            "src/main.rs",
            "src/core.rs",
            "src/utils.rs",
            "tests/integration_test.rs",
            ".github/workflows/ci.yml",
            ".env.example",
            "Cargo.toml",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
        "scalable": [
            "src/main.rs",
            "src/domain/mod.rs",
            "src/services/mod.rs",
            "src/infrastructure/mod.rs",
            "src/config.rs",
            "tests/integration_test.rs",
            ".github/workflows/ci.yml",
            ".env.example",
            "Cargo.toml",
            "RESEARCH.md",
            "PITFALLS.md",
            "ROADMAP.md",
        ],
    },
}


_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4",
                     "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2",
                     "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"}


def _validate_name(name: str) -> str:
    """Normalize and validate project name. Returns safe package name or raises ValueError."""
    if not name or not name.strip():
        raise ValueError("Project name cannot be empty.")
    stripped = name.strip()
    if any(c in stripped for c in ("/", "\\", "\x00")):
        raise ValueError(f"Project name must not contain path separators: {name!r}")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", stripped).lower()
    safe = re.sub(r"_+", "_", safe).strip("_-")
    if not safe:
        raise ValueError(f"Project name {name!r} contains no valid characters.")
    if re.match(r"^\d", safe):
        safe = "p_" + safe
    if safe in _WINDOWS_RESERVED:
        raise ValueError(f"Project name {name!r} is a reserved system name.")
    if len(safe) > 64:
        raise ValueError(f"Project name is too long (max 64 chars after normalization).")
    return safe


def create_structure(base_path: str, language: str, tier: str, name: str) -> list[str]:
    """Create project folder structure. Returns list of created paths."""
    lang = language.lower()
    if lang not in STRUCTURES:
        print(f"Warning: no template for '{language}'. Using python as fallback (keeping requested tier).")
        lang = "python"

    tier = tier.lower()
    if tier not in STRUCTURES[lang]:
        print(f"Warning: tier '{tier}' not found. Using minimalist.")
        tier = "minimalist"

    safe_name = _validate_name(name)
    base = Path(base_path).resolve()

    created = []
    for file_path in STRUCTURES[lang][tier]:
        resolved = file_path.replace("{name}", safe_name)
        full_path = (base / resolved).resolve()
        # Safety: ensure every generated path stays inside base_path
        try:
            full_path.relative_to(base)
        except ValueError:
            raise PermissionError(f"Generated path escapes output directory: {full_path}")
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if not full_path.exists():
                full_path.write_text("", encoding="utf-8")
                created.append(resolved)
        except OSError as e:
            print(f"  Warning: could not create {resolved}: {e}")

    return created


def main():
    parser = argparse.ArgumentParser(description="Genesis Architect - Scaffold Generator")
    parser.add_argument("--language", default="python", help="Target language (python, typescript, go, rust)")
    parser.add_argument("--tier", default="minimalist", help="Architecture tier (minimalist, scalable)")
    parser.add_argument("--name", default="my-project", help="Project name")
    parser.add_argument("--output", default=".", help="Output directory")
    args = parser.parse_args()

    try:
        safe = _validate_name(args.name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"Generating {args.tier} {args.language} scaffold for '{safe}'...")
    created = create_structure(args.output, args.language, args.tier, args.name)

    print(f"\nCreated {len(created)} files:")
    for path in created:
        print(f"  + {path}")
    print("\nScaffold ready.")


if __name__ == "__main__":
    main()
