#!/usr/bin/env python3
"""
scaffold_generator.py - Genesis Architect
Creates project folder structure based on language and architecture tier.
No external dependencies required (stdlib only).

Usage:
  python scripts/scaffold_generator.py --language typescript --tier minimalist --name my-project
  python scripts/scaffold_generator.py --language python --tier scalable --name my-service
"""

import argparse
import re
import sys
from pathlib import Path

# Single source of truth: references/folder-structures.toml
# Loaded once at import time via tomllib (Python 3.11+ stdlib).
_TOML_PATH = Path(__file__).parent.parent.parent.parent / "references" / "folder-structures.toml"


def _load_structures() -> dict:
    """Load STRUCTURES from references/folder-structures.toml using stdlib tomllib."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # popular backport, optional
        except ImportError:
            raise ImportError(
                "tomllib is required (stdlib in Python 3.11+). "
                "On Python 3.10 or earlier, install 'tomli': pip install tomli"
            )
    with open(_TOML_PATH, "rb") as f:
        raw = tomllib.load(f)
    # raw shape: {language: {tier: {files: [...]}}}
    # Normalise to {language: {tier: [files]}}
    result = {}
    for lang, tiers in raw.items():
        result[lang] = {}
        for tier, data in tiers.items():
            result[lang][tier] = data["files"]
    return result


STRUCTURES = _load_structures()

_VAULT_README = """\
# Genesis Vault - Smart Resolution Engine Cache

Solutions found by `genesis resolve` are cached here by topic and language.
Vault hits avoid external API calls entirely.

Usage:
  python scripts/vault.py search "[topic]" [language]   # query the cache
  python scripts/vault.py save                          # save a new entry
  python scripts/vault.py stats                         # inspect cache size

This directory is safe to commit - it contains only text summaries, no secrets.
"""

# Pre-commit config: local hooks only, no external pre-commit plugin repos.
# Runs genesis enforcement on every commit without requiring the LLM session.
_PRE_COMMIT_CONFIG = """\
# Genesis Architect - enforcement hooks
# These hooks enforce architecture decisions on every git commit.
# They require no external services - only Python stdlib.
#
# Install once: pip install pre-commit && pre-commit install
# Run manually: pre-commit run --all-files
# Skip (emergency only): git commit --no-verify

repos:
  - repo: local
    hooks:
      - id: genesis-mitigation-enforcer
        name: Genesis Mitigation Enforcer
        language: python
        entry: python scripts/mitigation_enforcer.py PITFALLS.md --src-root .
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
        # Fails if any mitigation_file_path in PITFALLS.md is missing or stub-only.
        # Fix: create the file with real implementation code.

      - id: genesis-drift-detector
        name: Genesis Architecture Drift Detector
        language: python
        entry: python scripts/drift_detector.py . --level 2
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
        # Fails if imports violate architecture rules in .genesis/evidence.json.
        # Fix: remove the forbidden import, or update evidence.json rules if intentional.
"""

_FIXED_CONTENT: dict[str, str] = {
    ".genesis/vault/README.md": _VAULT_README,
    ".pre-commit-config.yaml": _PRE_COMMIT_CONFIG,
}


def _file_content(resolved_path: str) -> str:
    """Return initial file content. Special-cased for known files, empty otherwise."""
    return _FIXED_CONTENT.get(resolved_path, "")


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
        raise ValueError("Project name is too long (max 64 chars after normalization).")
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
                content = _file_content(resolved)
                full_path.write_text(content, encoding="utf-8")
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
    parser.add_argument("--validate", action="store_true", help="Validate the TOML structure file and exit")
    args = parser.parse_args()

    if args.validate:
        langs = len(STRUCTURES)
        tiers = sum(len(t) for t in STRUCTURES.values())
        print(f"Structure valid: {langs} languages, {tiers} tiers")
        sys.exit(0)

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
