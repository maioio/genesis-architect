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
import sys
import argparse

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

    created = []
    safe_name = name.replace("-", "_").replace(" ", "_").lower()

    for file_path in STRUCTURES[lang][tier]:
        resolved = file_path.replace("{name}", safe_name)
        full_path = os.path.join(base_path, resolved)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        if not os.path.exists(full_path):
            with open(full_path, "w") as f:
                f.write("")
            created.append(resolved)

    return created


def main():
    parser = argparse.ArgumentParser(description="Genesis Architect - Scaffold Generator")
    parser.add_argument("--language", default="python", help="Target language (python, typescript, go, rust)")
    parser.add_argument("--tier", default="minimalist", help="Architecture tier (minimalist, scalable)")
    parser.add_argument("--name", default="my-project", help="Project name")
    parser.add_argument("--output", default=".", help="Output directory")
    args = parser.parse_args()

    print(f"Generating {args.tier} {args.language} scaffold for '{args.name}'...")
    created = create_structure(args.output, args.language, args.tier, args.name)

    print(f"\nCreated {len(created)} files:")
    for path in created:
        print(f"  + {path}")
    print("\nScaffold ready.")


if __name__ == "__main__":
    main()
