"""
project_tree (G-MED-01): an annotated tree of manifest, infrastructure and
environment files, with noise collapsed and categories propagated upward.
"""

import builtins
import io
import json
import sys
from pathlib import Path

import pytest

from genesis_architect_pro import project_tree
from genesis_architect_pro.project_tree import (
    ENVIRONMENT,
    INFRASTRUCTURE,
    MANIFEST,
    build_tree,
    classify,
    main,
)

SECRET_ENV = "environment file, may hold secrets (contents not read)"


def _touch(root: Path, *rel_paths: str, content: str = "") -> None:
    for rel in rel_paths:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    _touch(
        root,
        "pyproject.toml", ".env", ".env.example", "README.md",
        "src/pkg/__init__.py",
        ".github/workflows/ci.yml",
        "services/api/Dockerfile", "services/api/requirements.txt", "services/api/app.py",
        "node_modules/left-pad/package.json",
        "myenv/pyvenv.cfg", "myenv/lib/site-packages/dep/setup.py",
    )
    return root


def _find(node, path):
    if node.path == path:
        return node
    for child in node.children:
        found = _find(child, path)
        if found is not None:
            return found
    return None


def _all_paths(node):
    yield node.path
    for child in node.children:
        yield from _all_paths(child)


class TestClassify:
    @pytest.mark.parametrize("path,expected", [
        ("pyproject.toml", (MANIFEST, "Python project")),
        ("PyProject.TOML", (MANIFEST, "Python project")),
        ("web/package.json", (MANIFEST, "Node package")),
        ("Cargo.lock", (MANIFEST, "Rust lockfile")),
        ("requirements-dev.txt", (MANIFEST, "Python requirements")),
        ("requirements/base.txt", (MANIFEST, "Python requirements")),
        ("src/App.csproj", (MANIFEST, ".NET project")),
        ("Dockerfile", (INFRASTRUCTURE, "container image")),
        ("DOCKERFILE", (INFRASTRUCTURE, "container image")),
        ("docker/Dockerfile.prod", (INFRASTRUCTURE, "container image")),
        ("api.Dockerfile", (INFRASTRUCTURE, "container image")),
        ("services\\api\\Dockerfile", (INFRASTRUCTURE, "container image")),
        ("docker-compose.override.yml", (INFRASTRUCTURE, "container composition")),
        ("compose.yaml", (INFRASTRUCTURE, "container composition")),
        (".github/workflows/release.yaml", (INFRASTRUCTURE, "CI workflow (GitHub Actions)")),
        (".circleci/config.yml", (INFRASTRUCTURE, "CI (CircleCI)")),
        (".devcontainer/devcontainer.json", (INFRASTRUCTURE, "dev container")),
        ("infra/main.tf", (INFRASTRUCTURE, "Terraform")),
        ("Makefile", (INFRASTRUCTURE, "build tasks (make)")),
        (".env", (ENVIRONMENT, SECRET_ENV)),
        (".env.production", (ENVIRONMENT, SECRET_ENV)),
        ("config/prod.env", (ENVIRONMENT, SECRET_ENV)),
        (".env.example", (ENVIRONMENT, "environment template")),
        ("sample.env", (ENVIRONMENT, "environment template")),
        (".envrc", (ENVIRONMENT, "direnv environment, may hold secrets (contents not read)")),
        (".python-version", (ENVIRONMENT, "runtime version pin")),
        (".nvmrc", (ENVIRONMENT, "runtime version pin")),
    ])
    def test_labelled(self, path, expected):
        assert classify(path) == expected

    @pytest.mark.parametrize("path", [
        "", "README.md", "src/app.py", "config.yml", "workflows/ci.yml",
        "docs/requirements.md", ".envoy", "compose.py", "app.yaml",
    ])
    def test_unlabelled(self, path):
        assert classify(path) is None


class TestBuildTree:
    def test_render(self, proj):
        assert build_tree(proj).render() == "\n".join([
            "proj/  (manifest, infrastructure, environment)",
            f"|-- .env  [environment] {SECRET_ENV}",
            "|-- .env.example  [environment] environment template",
            "|-- pyproject.toml  [manifest] Python project",
            "|-- .github/workflows/  (infrastructure)",
            "|   `-- ci.yml  [infrastructure] CI workflow (GitHub Actions)",
            "`-- services/api/  (manifest, infrastructure)",
            "    |-- Dockerfile  [infrastructure] container image",
            "    `-- requirements.txt  [manifest] Python requirements",
            "collapsed: myenv, node_modules",
        ])

    def test_annotations_propagate_to_every_ancestor(self, proj):
        report = build_tree(proj)
        assert report.tree.annotations == {MANIFEST: 2, INFRASTRUCTURE: 2, ENVIRONMENT: 2}
        assert _find(report.tree, "services/api").annotations == {MANIFEST: 1, INFRASTRUCTURE: 1}

    def test_directories_without_labelled_files_are_pruned(self, proj):
        paths = set(_all_paths(build_tree(proj).tree))
        assert not any(p == "src" or p.startswith("src/") for p in paths)

    def test_unlabelled_files_are_counted_not_shown(self, proj):
        report = build_tree(proj)
        assert report.tree.other_files == 1                           # README.md
        assert _find(report.tree, "services/api").other_files == 1    # app.py
        assert "README.md" not in report.render()
        assert report.files_scanned == 9                              # noise dirs never entered

    def test_noise_and_virtualenvs_are_collapsed_not_entered(self, proj):
        report = build_tree(proj)
        assert sorted(report.collapsed) == ["myenv", "node_modules"]
        labelled = {f.path for f in report.labelled}
        assert "node_modules/left-pad/package.json" not in labelled
        assert "myenv/lib/site-packages/dep/setup.py" not in labelled

    def test_repeated_noise_is_counted(self, tmp_path):
        _touch(tmp_path, "Dockerfile", "a/__pycache__/x.pyc", "b/__pycache__/y.pyc", "pkg.egg-info/PKG-INFO")
        report = build_tree(tmp_path)
        assert report.render().splitlines()[-1] == "collapsed: __pycache__ (x2), pkg.egg-info"

    def test_never_opens_a_file(self, proj, monkeypatch):
        (proj / ".env").write_text("API_KEY=do-not-read\n", encoding="utf-8")

        def forbidden(*args, **kwargs):
            raise AssertionError(f"project_tree opened a file: {args[:1]}")

        monkeypatch.setattr(builtins, "open", forbidden)
        monkeypatch.setattr(io, "open", forbidden)
        report = build_tree(proj)
        assert ".env" in {f.path for f in report.by_category(ENVIRONMENT)}
        assert "do-not-read" not in json.dumps(report.to_dict())

    def test_chain_merge_stops_at_a_directory_with_files(self, tmp_path):
        _touch(tmp_path, "a/b/Dockerfile", "a/b/c/package.json")
        tree = build_tree(tmp_path).tree
        assert [c.name for c in tree.children] == ["a/b"]
        merged = tree.children[0]
        assert merged.path == "a/b"
        assert [(c.name, c.is_dir) for c in merged.children] == [("Dockerfile", False), ("c", True)]

    def test_empty_project_says_so(self, tmp_path):
        _touch(tmp_path, "main.py")
        report = build_tree(tmp_path)
        assert report.labelled == []
        assert report.render().splitlines()[-1] == "no manifest, infrastructure or environment files found"

    def test_max_files_truncates_with_a_warning(self, tmp_path):
        _touch(tmp_path, *(f"f{i}.txt" for i in range(5)))
        report = build_tree(tmp_path, max_files=3)
        assert report.truncated is True
        assert report.files_scanned == 3
        assert any("Stopped after 3 files" in w for w in report.warnings)

    def test_exact_file_count_is_not_truncated(self, tmp_path):
        _touch(tmp_path, "a.txt", "b.txt", "c.txt")
        assert build_tree(tmp_path, max_files=3).truncated is False

    def test_max_depth_skips_deeper_directories_with_a_warning(self, tmp_path):
        _touch(tmp_path, "pyproject.toml", "a/Makefile", "a/b/Dockerfile")
        report = build_tree(tmp_path, max_depth=1)
        assert {f.path for f in report.labelled} == {"pyproject.toml", "a/Makefile"}
        assert report.warnings == ["1 directory below depth 1 not scanned (first: a/b)"]

    def test_walk_errors_become_warnings(self, tmp_path, monkeypatch):
        def fake_walk(top, topdown=True, onerror=None):
            onerror(PermissionError(13, "Permission denied", str(Path(top) / "locked")))
            yield str(top), [], ["pyproject.toml"]

        monkeypatch.setattr(project_tree.os, "walk", fake_walk)
        report = build_tree(tmp_path)
        assert report.warnings == ["Could not list locked: Permission denied"]
        assert [f.path for f in report.labelled] == ["pyproject.toml"]

    def test_relative_root(self, proj, monkeypatch):
        monkeypatch.chdir(proj)
        report = build_tree(".")
        assert report.root_name == "proj"
        assert "services/api/Dockerfile" in {f.path for f in report.labelled}

    def test_invalid_arguments_raise(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            build_tree(tmp_path / "missing")
        with pytest.raises(ValueError):
            build_tree(tmp_path, max_files=0)

    def test_to_dict_is_json_and_environment_neutral(self, proj):
        data = build_tree(proj).to_dict()
        text = json.dumps(data)
        assert str(proj.parent) not in text
        assert data["counts"] == {MANIFEST: 2, INFRASTRUCTURE: 2, ENVIRONMENT: 2}
        assert data["tree"]["name"] == "proj"
        assert [c["name"] for c in data["tree"]["children"]][-2:] == [".github/workflows", "services/api"]


class TestCli:
    def test_json(self, proj, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["project_tree", str(proj), "--json"])
        main()
        data = json.loads(capsys.readouterr().out)
        assert data["counts"][ENVIRONMENT] == 2

    def test_text(self, proj, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["project_tree", str(proj)])
        main()
        assert capsys.readouterr().out.startswith("proj/  (manifest, infrastructure, environment)")

    def test_missing_path_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["project_tree", str(tmp_path / "nope")])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        assert "Not a directory" in capsys.readouterr().err
