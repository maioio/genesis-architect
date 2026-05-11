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
                f.write(_starter_content(resolved, safe_name))
            created.append(resolved)

    return created


# SKILL.md Phase 6 Step 3 requires "every file must contain working code, not
# empty stubs". The mapping below provides a minimal but real starting point
# per file; the skill is expected to elaborate on it during the build phase.
def _starter_content(file_path: str, project: str) -> str:
    name = os.path.basename(file_path)

    if name == "__init__.py":
        return f'"""Package: {project}."""\n'
    if name == "main.py":
        return (
            f'"""{project}: entry point."""\n\n'
            "from .core import run\n\n\n"
            'if __name__ == "__main__":\n'
            "    run()\n"
        )
    if name == "core.py":
        return (
            f'"""{project}: core logic."""\n\n\n'
            "def run() -> str:\n"
            f'    return "{project} ready"\n'
        )
    if name == "utils.py":
        return f'"""{project}: shared utilities."""\n'
    if name == "config.py":
        return (
            '"""Environment-driven configuration. Fail fast on missing required vars."""\n\n'
            "import os\n\n\n"
            "def required(key: str) -> str:\n"
            "    value = os.environ.get(key)\n"
            "    if not value:\n"
            '        raise RuntimeError(f"Missing required env var: {key}")\n'
            "    return value\n"
        )
    if name == "test_core.py":
        return (
            f"from {project}.core import run\n\n\n"
            "def test_run_returns_ready_message():\n"
            f'    assert run() == "{project} ready"\n'
        )
    if name == "pyproject.toml":
        return (
            "[project]\n"
            f'name = "{project}"\n'
            'version = "0.1.0"\n'
            'requires-python = ">=3.9"\n\n'
            "[project.scripts]\n"
            f'{project} = "{project}.main:run"\n\n'
            "[build-system]\n"
            'requires = ["setuptools>=61"]\n'
            'build-backend = "setuptools.build_meta"\n'
        )

    if name == "package.json":
        return (
            "{\n"
            f'  "name": "{project}",\n'
            '  "version": "0.1.0",\n'
            '  "type": "module",\n'
            '  "scripts": {\n'
            '    "test": "node --test"\n'
            "  }\n"
            "}\n"
        )
    if name == "tsconfig.json":
        return (
            "{\n"
            '  "compilerOptions": {\n'
            '    "target": "ES2022",\n'
            '    "module": "ESNext",\n'
            '    "moduleResolution": "bundler",\n'
            '    "strict": true,\n'
            '    "outDir": "dist"\n'
            "  },\n"
            '  "include": ["src"]\n'
            "}\n"
        )
    if name == "index.ts":
        return 'import { run } from "./core";\n\nrun();\n'
    if name == "core.ts":
        return f'export function run(): string {{\n  return "{project} ready";\n}}\n'
    if name == "utils.ts":
        return "export {};\n"
    if name == "core.test.ts":
        return (
            'import { run } from "../src/core";\n\n'
            "test('run returns ready message', () => {\n"
            f"  expect(run()).toBe('{project} ready');\n"
            "});\n"
        )

    if name == "go.mod":
        return f"module {project}\n\ngo 1.21\n"
    if name == "main.go":
        return (
            "package main\n\n"
            'import "fmt"\n\n'
            "func main() {\n"
            f'\tfmt.Println("{project} ready")\n'
            "}\n"
        )
    if name == "core.go":
        return "package core\n\nfunc Run() string {\n\treturn \"ready\"\n}\n"
    if name == "core_test.go":
        return (
            "package core\n\n"
            'import "testing"\n\n'
            "func TestRun(t *testing.T) {\n"
            "\tif Run() != \"ready\" {\n"
            "\t\tt.Fatal(\"unexpected output\")\n"
            "\t}\n"
            "}\n"
        )

    if name == "Cargo.toml":
        return (
            "[package]\n"
            f'name = "{project}"\n'
            'version = "0.1.0"\n'
            'edition = "2021"\n'
        )
    if name == "main.rs":
        return f'fn main() {{\n    println!("{project} ready");\n}}\n'
    if name == "core.rs":
        return "pub fn run() -> &'static str {\n    \"ready\"\n}\n"

    if name == ".env.example":
        return (
            "# Copy to .env and fill in. Required vars cause fail-fast at startup.\n"
            "SECRET_KEY=change-me-generate-with-openssl-rand-hex-32\n"
        )
    if name == ".gitkeep":
        return ""
    return f"# {project}: {file_path}\n"


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
