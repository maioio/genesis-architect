"""Tests for scaffold_generator.py - closes issue #14."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ---------------------------------------------------------------------------
# _validate_name
# ---------------------------------------------------------------------------

class TestValidateName:
    def test_simple_name_passes(self):
        from scaffold_generator import _validate_name
        assert _validate_name("my-project") == "my-project"

    def test_normalizes_spaces_to_underscores(self):
        from scaffold_generator import _validate_name
        assert _validate_name("my project") == "my_project"

    def test_lowercases(self):
        from scaffold_generator import _validate_name
        assert _validate_name("MyProject") == "myproject"

    def test_strips_leading_trailing_whitespace(self):
        from scaffold_generator import _validate_name
        assert _validate_name("  myproject  ") == "myproject"

    def test_prefixes_digit_start_with_p(self):
        from scaffold_generator import _validate_name
        assert _validate_name("1service").startswith("p_")

    def test_rejects_empty_name(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="empty"):
            _validate_name("")

    def test_rejects_whitespace_only(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="empty"):
            _validate_name("   ")

    def test_rejects_path_separator_slash(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="path separators"):
            _validate_name("foo/bar")

    def test_rejects_path_separator_backslash(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="path separators"):
            _validate_name("foo\\bar")

    def test_rejects_reserved_windows_name(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="reserved"):
            _validate_name("con")

    def test_rejects_name_too_long(self):
        from scaffold_generator import _validate_name
        with pytest.raises(ValueError, match="too long"):
            _validate_name("a" * 65)

    def test_collapses_multiple_underscores(self):
        from scaffold_generator import _validate_name
        result = _validate_name("my___project")
        assert "__" not in result


# ---------------------------------------------------------------------------
# create_structure - file creation
# ---------------------------------------------------------------------------

class TestCreateStructure:
    def test_python_minimalist_creates_expected_files(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "python", "minimalist", "myapp")
        names = [Path(p).name for p in created]
        assert "__init__.py" in names
        assert "pyproject.toml" in names

    def test_python_scalable_creates_expected_files(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "python", "scalable", "myapp")
        assert len(created) > 0
        paths_str = " ".join(created)
        assert "myapp" in paths_str

    def test_typescript_minimalist_creates_index(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "typescript", "minimalist", "myapp")
        names = [Path(p).name for p in created]
        assert "index.ts" in names

    def test_typescript_scalable_creates_files(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "typescript", "scalable", "myapp")
        assert len(created) > 0

    def test_go_minimalist_creates_main(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "go", "minimalist", "myapp")
        assert any("main.go" in p for p in created)

    def test_rust_minimalist_creates_main(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "rust", "minimalist", "myapp")
        assert any("main.rs" in p for p in created)

    def test_files_are_non_empty_after_gitkeep_filter(self, tmp_path):
        from scaffold_generator import create_structure
        create_structure(str(tmp_path), "python", "minimalist", "myapp")
        py_files = [f for f in tmp_path.rglob("*.py") if ".gitkeep" not in str(f)]
        assert len(py_files) > 0

    def test_created_files_actually_exist_on_disk(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "python", "minimalist", "myapp")
        for rel_path in created:
            full = tmp_path / rel_path
            assert full.exists(), f"Expected file missing: {rel_path}"

    def test_name_placeholder_substituted(self, tmp_path):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "python", "minimalist", "coolapp")
        assert any("coolapp" in p for p in created), f"Name not substituted in: {created}"

    def test_unknown_language_falls_back_to_python(self, tmp_path, capsys):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "cobol", "minimalist", "myapp")
        assert len(created) > 0
        assert "Warning" in capsys.readouterr().out

    def test_unknown_tier_falls_back_to_minimalist(self, tmp_path, capsys):
        from scaffold_generator import create_structure
        created = create_structure(str(tmp_path), "python", "superscalable", "myapp")
        assert len(created) > 0
        assert "Warning" in capsys.readouterr().out

    def test_does_not_overwrite_existing_files(self, tmp_path):
        from scaffold_generator import create_structure
        create_structure(str(tmp_path), "python", "minimalist", "myapp")
        # Write sentinel content
        init = next(tmp_path.rglob("__init__.py"), None)
        assert init is not None
        init.write_text("# sentinel", encoding="utf-8")
        # Run again
        create_structure(str(tmp_path), "python", "minimalist", "myapp")
        assert init.read_text() == "# sentinel"

    def test_path_traversal_blocked(self, tmp_path):
        from scaffold_generator import create_structure, _validate_name
        # inject a path that would escape base_path
        import unittest.mock as mock
        evil_files = ["../../../etc/passwd"]
        with mock.patch("scaffold_generator.STRUCTURES", {"python": {"minimalist": evil_files}}):
            with pytest.raises(PermissionError, match="escapes"):
                create_structure(str(tmp_path), "python", "minimalist", "myapp")

    def test_returns_list_of_strings(self, tmp_path):
        from scaffold_generator import create_structure
        result = create_structure(str(tmp_path), "python", "minimalist", "myapp")
        assert isinstance(result, list)
        assert all(isinstance(p, str) for p in result)


# ---------------------------------------------------------------------------
# All 8 language/tier combos (mirrors CI smoke test)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("language,tier,expected_count", [
    ("python",     "minimalist", 1),
    ("python",     "scalable",   1),
    ("typescript", "minimalist", 1),
    ("typescript", "scalable",   1),
    ("go",         "minimalist", 1),
    ("go",         "scalable",   1),
    ("rust",       "minimalist", 1),
    ("rust",       "scalable",   1),
])
def test_all_combos_produce_files(tmp_path, language, tier, expected_count):
    from scaffold_generator import create_structure
    created = create_structure(str(tmp_path / f"{language}-{tier}"), language, tier, "smoke")
    assert len(created) >= expected_count, f"{language}/{tier} produced no files"


# ---------------------------------------------------------------------------
# STRUCTURES (TOML integrity)
# ---------------------------------------------------------------------------

PRODUCTION_DEFAULTS = [
    ".env.example",
    ".pre-commit-config.yaml",
    "sonar-project.properties",
    "docs/adr/001-initial-architecture.md",
    ".github/workflows/ci.yml",
    "RESEARCH.md",
    "PITFALLS.md",
    "ROADMAP.md",
]

SECURITY_FILE_SUFFIXES = (
    "utils/security.py",
    "utils/security.ts",
    "utils/security.go",
    "utils/security.rs",
)


class TestStructuresIntegrity:
    def test_all_expected_languages_present(self):
        from scaffold_generator import STRUCTURES
        for lang in ("python", "typescript", "go", "rust"):
            assert lang in STRUCTURES, f"Missing language: {lang}"

    def test_each_language_has_both_tiers(self):
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            assert "minimalist" in tiers, f"{lang} missing minimalist tier"
            assert "scalable" in tiers, f"{lang} missing scalable tier"

    def test_each_tier_has_at_least_5_files(self):
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            for tier, files in tiers.items():
                assert len(files) >= 5, f"{lang}/{tier} has only {len(files)} files"

    def test_no_absolute_paths_in_toml(self):
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            for tier, files in tiers.items():
                for f in files:
                    assert not f.startswith("/"), f"Absolute path in TOML: {f}"
                    assert not f.startswith("\\"), f"Absolute path in TOML: {f}"

    @pytest.mark.parametrize("required_file", PRODUCTION_DEFAULTS)
    def test_production_defaults_in_all_archetypes(self, required_file):
        """Every archetype/tier must include all mandatory production-defaults files."""
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            for tier, files in tiers.items():
                norm = [f.replace("\\", "/") for f in files]
                assert any(
                    f == required_file or f.endswith("/" + required_file)
                    for f in norm
                ), (
                    f"{lang}/{tier} missing production default: '{required_file}'. "
                    f"Add it to references/folder-structures.toml."
                )

    def test_vault_readme_in_all_archetypes(self):
        """Every archetype/tier must include .genesis/vault/README.md."""
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            for tier, files in tiers.items():
                norm = [f.replace("\\", "/") for f in files]
                assert ".genesis/vault/README.md" in norm, (
                    f"{lang}/{tier} missing .genesis/vault/README.md"
                )

    def test_vault_readme_has_content_after_scaffold(self, tmp_path):
        """scaffold_generator must write non-empty content to .genesis/vault/README.md."""
        from scaffold_generator import create_structure
        create_structure(str(tmp_path), "python", "minimalist", "myapp")
        vault_readme = tmp_path / ".genesis" / "vault" / "README.md"
        assert vault_readme.exists(), ".genesis/vault/README.md was not created"
        assert vault_readme.stat().st_size > 0, ".genesis/vault/README.md is empty"
        content = vault_readme.read_text(encoding="utf-8")
        assert "vault" in content.lower() or "genesis" in content.lower()

    def test_pre_commit_config_has_genesis_hooks(self, tmp_path):
        """scaffold_generator must write genesis enforcement hooks to .pre-commit-config.yaml."""
        from scaffold_generator import create_structure
        create_structure(str(tmp_path), "python", "minimalist", "myapp")
        pre_commit = tmp_path / ".pre-commit-config.yaml"
        assert pre_commit.exists(), ".pre-commit-config.yaml was not created"
        content = pre_commit.read_text(encoding="utf-8")
        assert "genesis-mitigation-enforcer" in content, "Missing mitigation enforcer hook"
        assert "genesis-drift-detector" in content, "Missing drift detector hook"
        assert "mitigation_enforcer.py" in content, "Hook must call mitigation_enforcer.py"
        assert "drift_detector.py" in content, "Hook must call drift_detector.py"

    def test_security_file_in_all_archetypes(self):
        """Every archetype/tier must include a language-appropriate security.py/ts/go/rs."""
        from scaffold_generator import STRUCTURES
        for lang, tiers in STRUCTURES.items():
            for tier, files in tiers.items():
                norm = [f.replace("\\", "/") for f in files]
                has_security = any(
                    any(f.endswith(suffix) for suffix in SECURITY_FILE_SUFFIXES)
                    for f in norm
                )
                assert has_security, (
                    f"{lang}/{tier} missing a utils/security.* file. "
                    f"Add src/{{name}}/utils/security.{{'py'|'ts'|'go'|'rs'}} "
                    f"to references/folder-structures.toml."
                )


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMain:
    def test_validate_flag_exits_0(self):
        from scaffold_generator import main
        import unittest.mock as mock
        with mock.patch("sys.argv", ["scaffold_generator.py", "--validate"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0

    def test_invalid_name_exits_1(self, tmp_path):
        from scaffold_generator import main
        import unittest.mock as mock
        with mock.patch("sys.argv", [
            "scaffold_generator.py",
            "--name", "con",       # reserved Windows name
            "--output", str(tmp_path),
        ]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_valid_args_exit_0(self, tmp_path):
        from scaffold_generator import main
        import unittest.mock as mock
        with mock.patch("sys.argv", [
            "scaffold_generator.py",
            "--language", "python",
            "--tier", "minimalist",
            "--name", "testapp",
            "--output", str(tmp_path),
        ]):
            main()   # should not raise
