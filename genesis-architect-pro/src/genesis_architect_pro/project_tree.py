#!/usr/bin/env python3
"""
project_tree.py - Genesis Architect PRO

An annotated project tree that shows only the files that say how a project is
built, deployed and configured:

  manifest        - package and dependency manifests, lockfiles
  infrastructure  - container, CI, IaC, deployment and build-task files
  environment     - .env files, templates and runtime version pins

Everything else is collapsed. Generated and vendored directories (.git,
node_modules, __pycache__, dist, any directory holding pyvenv.cfg, ...) are
never entered; they are listed in the report instead of disappearing silently.
A directory appears only if a labelled file sits somewhere below it, and it is
annotated with the categories found beneath it (annotation propagation). A
directory whose only content is one sub-directory is merged into it, so
.github/workflows/ reads as one line.

Classification is by file name and location only. No file is ever opened:
an .env file is labelled as present, and its contents are never read.

Public API
----------
  classify(rel_path) -> (category, detail) | None
  build_tree(root, max_depth=None, max_files=DEFAULT_MAX_FILES) -> TreeReport

Usage:
  python -m genesis_architect_pro.project_tree [PATH]
  python -m genesis_architect_pro.project_tree [PATH] --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST = "manifest"
INFRASTRUCTURE = "infrastructure"
ENVIRONMENT = "environment"
CATEGORIES = (MANIFEST, INFRASTRUCTURE, ENVIRONMENT)

DEFAULT_MAX_FILES = 50_000

# Generated, vendored or tool-state directories. "build" is deliberately absent:
# Go and CI layouts keep Dockerfiles and pipelines under build/.
NOISE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components", "vendor",
    "__pycache__", ".venv", "venv", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".pyre", ".hypothesis",
    "dist", "target", ".gradle", ".terraform",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".cache",
    "coverage", "htmlcov", ".idea", ".vscode", ".genesis",
})
_NOISE_SUFFIXES = (".egg-info",)
_VENV_MARKER = "pyvenv.cfg"

_MANIFEST_NAMES: dict[str, str] = {
    "pyproject.toml": "Python project",
    "setup.py": "Python package (setuptools)",
    "setup.cfg": "Python package (setuptools)",
    "pipfile": "Python dependencies (Pipenv)",
    "constraints.txt": "Python constraints",
    "environment.yml": "Conda environment",
    "environment.yaml": "Conda environment",
    "poetry.lock": "Python lockfile (Poetry)",
    "uv.lock": "Python lockfile (uv)",
    "pipfile.lock": "Python lockfile (Pipenv)",
    "package.json": "Node package",
    "package-lock.json": "Node lockfile (npm)",
    "yarn.lock": "Node lockfile (Yarn)",
    "pnpm-lock.yaml": "Node lockfile (pnpm)",
    "bun.lockb": "Node lockfile (Bun)",
    "deno.json": "Deno project",
    "deno.jsonc": "Deno project",
    "cargo.toml": "Rust crate",
    "cargo.lock": "Rust lockfile",
    "go.mod": "Go module",
    "go.sum": "Go checksums",
    "pom.xml": "Maven project",
    "build.gradle": "Gradle project",
    "build.gradle.kts": "Gradle project",
    "settings.gradle": "Gradle settings",
    "settings.gradle.kts": "Gradle settings",
    "gemfile": "Ruby dependencies (Bundler)",
    "gemfile.lock": "Ruby lockfile",
    "composer.json": "PHP dependencies (Composer)",
    "composer.lock": "PHP lockfile",
    "mix.exs": "Elixir project",
    "pubspec.yaml": "Dart/Flutter package",
    "package.swift": "Swift package",
    "cmakelists.txt": "CMake project",
}
_MANIFEST_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".csproj", ".NET project"),
    (".fsproj", ".NET project"),
    (".vbproj", ".NET project"),
    (".sln", ".NET solution"),
    (".gemspec", "Ruby gem"),
)

_INFRA_NAMES: dict[str, str] = {
    "dockerfile": "container image",
    "containerfile": "container image",
    ".dockerignore": "container build context",
    ".gitlab-ci.yml": "CI (GitLab)",
    "jenkinsfile": "CI (Jenkins)",
    "azure-pipelines.yml": "CI (Azure Pipelines)",
    "bitbucket-pipelines.yml": "CI (Bitbucket)",
    ".travis.yml": "CI (Travis)",
    "chart.yaml": "Helm chart",
    "kustomization.yaml": "Kustomize overlay",
    "skaffold.yaml": "Skaffold config",
    "procfile": "process definition",
    "fly.toml": "deployment (Fly.io)",
    "vercel.json": "deployment (Vercel)",
    "netlify.toml": "deployment (Netlify)",
    "render.yaml": "deployment (Render)",
    "serverless.yml": "deployment (Serverless)",
    "vagrantfile": "VM definition",
    "makefile": "build tasks (make)",
    "gnumakefile": "build tasks (make)",
    "justfile": "build tasks (just)",
    "taskfile.yml": "build tasks (Task)",
    ".pre-commit-config.yaml": "pre-commit hooks",
    ".devcontainer.json": "dev container",
}
_YAML = (".yml", ".yaml")

_RUNTIME_PINS = frozenset({
    ".python-version", ".nvmrc", ".node-version", ".ruby-version",
    ".tool-versions", "runtime.txt",
})
_ENV_TEMPLATE_MARKERS = frozenset({"example", "sample", "template", "tmpl", "dist"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TreeNode:
    """
    One node of the annotated tree.

    name:        display name; a merged directory chain reads "a/b"
    path:        posix path relative to the scanned root ("" for the root)
    category:    files only - manifest | infrastructure | environment
    annotations: directories only - labelled files below, per category
    other_files: directories only - unlabelled files directly inside, not shown
    """
    name: str
    path: str
    is_dir: bool
    category: str | None = None
    detail: str = ""
    children: list[TreeNode] = field(default_factory=list)
    annotations: dict[str, int] = field(default_factory=dict)
    other_files: int = 0

    def to_dict(self) -> dict:
        if not self.is_dir:
            return {"name": self.name, "path": self.path,
                    "category": self.category, "detail": self.detail}
        return {
            "name": self.name,
            "path": self.path,
            "annotations": dict(self.annotations),
            "other_files": self.other_files,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class LabelledFile:
    path: str
    category: str
    detail: str


@dataclass
class TreeReport:
    root_name: str
    tree: TreeNode
    labelled: list[LabelledFile] = field(default_factory=list)
    files_scanned: int = 0
    collapsed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False

    def by_category(self, category: str) -> list[LabelledFile]:
        return [f for f in self.labelled if f.category == category]

    def render(self) -> str:
        lines = render_tree(self.tree)
        if self.collapsed:
            counts = Counter(PurePosixPath(p).name for p in self.collapsed)
            names = ", ".join(
                name if n == 1 else f"{name} (x{n})" for name, n in sorted(counts.items())
            )
            lines.append(f"collapsed: {names}")
        if not self.labelled:
            lines.append("no manifest, infrastructure or environment files found")
        lines.extend(f"WARNING: {w}" for w in self.warnings)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "root": self.root_name,
            "files_scanned": self.files_scanned,
            "truncated": self.truncated,
            "counts": {c: len(self.by_category(c)) for c in CATEGORIES},
            "labelled": [
                {"path": f.path, "category": f.category, "detail": f.detail}
                for f in self.labelled
            ],
            "collapsed": list(self.collapsed),
            "warnings": list(self.warnings),
            "tree": self.tree.to_dict(),
        }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_environment(name: str) -> tuple[str, str] | None:
    if name in _RUNTIME_PINS:
        return ENVIRONMENT, "runtime version pin"
    if name == ".envrc":
        return ENVIRONMENT, "direnv environment, may hold secrets (contents not read)"
    if not (name == ".env" or name.startswith(".env.") or name.endswith(".env")):
        return None
    if _ENV_TEMPLATE_MARKERS.intersection(name.split(".")):
        return ENVIRONMENT, "environment template"
    return ENVIRONMENT, "environment file, may hold secrets (contents not read)"


def _classify_infrastructure(name: str, parents: list[str]) -> tuple[str, str] | None:
    if name in _INFRA_NAMES:
        return INFRASTRUCTURE, _INFRA_NAMES[name]
    if name.startswith("dockerfile.") or name.endswith(".dockerfile"):
        return INFRASTRUCTURE, "container image"
    if name.endswith(_YAML) and (name.startswith("docker-compose") or name.startswith("compose.")):
        return INFRASTRUCTURE, "container composition"
    if name.endswith(_YAML) and parents[-2:] == [".github", "workflows"]:
        return INFRASTRUCTURE, "CI workflow (GitHub Actions)"
    if name == "config.yml" and parents[-1:] == [".circleci"]:
        return INFRASTRUCTURE, "CI (CircleCI)"
    if name == "devcontainer.json" and parents[-1:] == [".devcontainer"]:
        return INFRASTRUCTURE, "dev container"
    if name.endswith(".tf"):
        return INFRASTRUCTURE, "Terraform"
    if name.endswith(".tfvars"):
        return INFRASTRUCTURE, "Terraform variables (contents not read)"
    return None


def _classify_manifest(name: str, parents: list[str]) -> tuple[str, str] | None:
    if name in _MANIFEST_NAMES:
        return MANIFEST, _MANIFEST_NAMES[name]
    for suffix, detail in _MANIFEST_SUFFIXES:
        if name.endswith(suffix):
            return MANIFEST, detail
    if name.endswith((".txt", ".in")) and (
        name.startswith("requirements") or parents[-1:] == ["requirements"]
    ):
        return MANIFEST, "Python requirements"
    return None


def classify(rel_path: str) -> tuple[str, str] | None:
    """
    Return (category, detail) for a file path relative to the project root, or
    None when the file is none of manifest, infrastructure or environment.
    Matching is case-insensitive and uses the name and parent directories only.
    """
    parts = [p.lower() for p in PurePosixPath(rel_path.replace("\\", "/")).parts]
    if not parts:
        return None
    name, parents = parts[-1], parts[:-1]
    return (_classify_environment(name)
            or _classify_infrastructure(name, parents)
            or _classify_manifest(name, parents))


def _is_noise_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in NOISE_DIRS or lowered.endswith(_NOISE_SUFFIXES)


# ---------------------------------------------------------------------------
# Tree building
# ---------------------------------------------------------------------------

def _sort_key(node: TreeNode) -> tuple[bool, str]:
    # Files before directories, so a directory's own manifests lead its block.
    return node.is_dir, node.name.lower()


def _assemble(labelled: list[LabelledFile], other_files: dict[str, int],
              root_name: str) -> TreeNode:
    root = TreeNode(name=root_name, path="", is_dir=True, other_files=other_files.get("", 0))
    index: dict[str, TreeNode] = {"": root}
    for item in labelled:
        parts = item.path.split("/")
        parent = root
        for depth in range(1, len(parts)):
            dir_path = "/".join(parts[:depth])
            node = index.get(dir_path)
            if node is None:
                node = TreeNode(name=parts[depth - 1], path=dir_path, is_dir=True,
                                other_files=other_files.get(dir_path, 0))
                index[dir_path] = node
                parent.children.append(node)
            parent = node
        parent.children.append(TreeNode(name=parts[-1], path=item.path, is_dir=False,
                                        category=item.category, detail=item.detail))
    _propagate(root)
    for child in root.children:
        _merge_chains(child)
    return root


def _propagate(node: TreeNode) -> Counter:
    """Fill every directory's annotations from the labelled files below it."""
    if not node.is_dir:
        return Counter({node.category: 1})
    total: Counter = Counter()
    node.children.sort(key=_sort_key)
    for child in node.children:
        total += _propagate(child)
    node.annotations = {c: total[c] for c in CATEGORIES if total[c]}
    return total


def _merge_chains(node: TreeNode) -> None:
    """Merge a directory into its only child while that child is a directory."""
    if not node.is_dir:
        return
    while len(node.children) == 1 and node.children[0].is_dir:
        only = node.children[0]
        node.name = f"{node.name}/{only.name}"
        node.path = only.path
        node.children = only.children
        node.other_files = only.other_files
    for child in node.children:
        _merge_chains(child)


def build_tree(root: str | Path, max_depth: int | None = None,
               max_files: int = DEFAULT_MAX_FILES) -> TreeReport:
    """
    Walk *root* and build the annotated tree. Read-only: directories are listed,
    no file is opened.

    max_depth: directories deeper than this many levels below root are not
               entered (a warning says how many were skipped).
    max_files: stop after this many files and mark the report truncated.
    """
    base = Path(root)
    if not base.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    if max_files <= 0:
        raise ValueError(f"max_files must be positive, got {max_files}")

    root_name = base.resolve().name or str(base)
    labelled: list[LabelledFile] = []
    other_files: dict[str, int] = {}
    collapsed: list[str] = []
    warnings: list[str] = []
    depth_skipped: list[str] = []
    scanned = 0
    truncated = False

    def on_error(exc: OSError) -> None:
        where = str(exc.filename or "?")
        try:
            where = Path(where).relative_to(base).as_posix()
        except ValueError:
            pass
        warnings.append(f"Could not list {where}: {exc.strerror or exc}")

    for dirpath, dirnames, filenames in os.walk(base, topdown=True, onerror=on_error):
        rel_dir = Path(dirpath).relative_to(base).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        if rel_dir and _VENV_MARKER in filenames:
            collapsed.append(rel_dir)
            dirnames[:] = []
            continue

        depth = len(rel_dir.split("/")) if rel_dir else 0
        keep = []
        for name in sorted(dirnames, key=str.lower):
            child = f"{rel_dir}/{name}" if rel_dir else name
            if _is_noise_dir(name):
                collapsed.append(child)
            elif max_depth is not None and depth >= max_depth:
                depth_skipped.append(child)
            else:
                keep.append(name)
        dirnames[:] = keep

        for name in sorted(filenames, key=str.lower):
            if scanned >= max_files:
                truncated = True
                break
            scanned += 1
            rel_file = f"{rel_dir}/{name}" if rel_dir else name
            label = classify(rel_file)
            if label is None:
                other_files[rel_dir] = other_files.get(rel_dir, 0) + 1
            else:
                labelled.append(LabelledFile(rel_file, *label))
        if truncated:
            break

    if truncated:
        warnings.append(
            f"Stopped after {max_files} files: the tree is partial. "
            "Raise max_files or scan a sub-directory."
        )
    if depth_skipped:
        warnings.append(
            f"{len(depth_skipped)} director{'y' if len(depth_skipped) == 1 else 'ies'} "
            f"below depth {max_depth} not scanned (first: {depth_skipped[0]})"
        )

    return TreeReport(
        root_name=root_name,
        tree=_assemble(labelled, other_files, root_name),
        labelled=labelled,
        files_scanned=scanned,
        collapsed=collapsed,
        warnings=warnings,
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _node_line(node: TreeNode) -> str:
    if node.is_dir:
        tags = ", ".join(node.annotations)
        return f"{node.name}/  ({tags})" if tags else f"{node.name}/"
    return f"{node.name}  [{node.category}] {node.detail}"


def render_tree(node: TreeNode) -> list[str]:
    """Render *node* and its descendants as ASCII tree lines."""
    lines = [_node_line(node)]

    def walk(children: list[TreeNode], prefix: str) -> None:
        for i, child in enumerate(children):
            last = i == len(children) - 1
            lines.append(f"{prefix}{'`-- ' if last else '|-- '}{_node_line(child)}")
            if child.is_dir:
                walk(child.children, prefix + ("    " if last else "|   "))

    walk(node.children, "")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Annotated Project Tree"
    )
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = build_tree(args.path, max_depth=args.max_depth, max_files=args.max_files)
    except (NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())


if __name__ == "__main__":
    main()
