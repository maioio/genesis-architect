"""Tests for skill_fetcher.py — whitelist-only, fetch-and-read, never execute.

Network is injected everywhere (`cloner=`), so nothing here touches the wire.
The bulk of this suite asserts refusals: what the fetcher will NOT do matters
more than what it will.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from genesis_architect_pro.ephemeral_purge import MANIFEST_NAME, purge, read_manifest
from genesis_architect_pro.skill_fetcher import (
    DEFAULT_TTL_HOURS,
    MAX_TTL_HOURS,
    REGISTRY,
    FetchRefused,
    _parse_frontmatter,
    discard,
    execute,
    fetch,
    format_result,
    format_sources,
    is_trusted_url,
    list_sources,
    read_skills,
    sandbox_for,
    sandbox_root,
    validate_source,
)


# ---------------------------------------------------------------------------
# Fake cloner — stands in for the network
# ---------------------------------------------------------------------------


def _fake_pack(skills: dict[str, str] | None = None, *, fail: str = ""):
    """Build a cloner that materialises a fake skill pack on disk."""
    payload = skills if skills is not None else {
        "adr-writer": "Writes architecture decision records.",
        "tradeoff-analysis-writer": "Documents tradeoffs between options.",
    }

    def cloner(url: str, dest):
        if fail:
            return False, fail
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README.md").write_text("# pack\n", encoding="utf-8")
        for name, description in payload.items():
            skill_dir = dest / "skills" / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
                encoding="utf-8")
        return True, ""

    return cloner


# ---------------------------------------------------------------------------
# Whitelist enforcement — refuses before any network access
# ---------------------------------------------------------------------------


class TestWhitelist:
    def test_registry_is_not_empty(self):
        assert REGISTRY

    def test_known_source_validates(self):
        source = validate_source("software-architecture-skills")
        assert source.owner == "45ck"
        assert source.host == "github.com"

    def test_unknown_source_refused(self):
        with pytest.raises(FetchRefused, match="not in the trusted registry"):
            validate_source("some-random-pack")

    def test_raw_url_refused(self):
        with pytest.raises(FetchRefused):
            validate_source("https://evil.example.com/payload.git")

    def test_path_traversal_refused(self):
        for bad in ("../../etc", "..", "a/../../b", "/etc/passwd", "..\\..\\win"):
            with pytest.raises(FetchRefused):
                validate_source(bad)

    def test_empty_and_non_string_refused(self):
        for bad in ("", None, 123, []):
            with pytest.raises(FetchRefused):
                validate_source(bad)  # type: ignore[arg-type]

    def test_uppercase_and_spaces_refused(self):
        for bad in ("Software-Architecture", "has space", "semi;colon", "pipe|x"):
            with pytest.raises(FetchRefused):
                validate_source(bad)

    def test_overlong_id_refused(self):
        with pytest.raises(FetchRefused):
            validate_source("a" * 200)

    def test_fetch_refuses_untrusted_without_calling_cloner(self, tmp_path):
        called = []

        def spy(url, dest):
            called.append(url)
            return True, ""

        with pytest.raises(FetchRefused):
            fetch("not-in-registry", tmp_path, cloner=spy)
        assert called == [], "the network must not be touched for an untrusted id"

    def test_is_trusted_url_only_matches_registry(self):
        assert is_trusted_url("https://github.com/45ck/software-architecture-skills.git")
        assert not is_trusted_url("https://github.com/attacker/software-architecture-skills.git")
        assert not is_trusted_url("https://evil.example.com/x.git")

    def test_every_registry_entry_uses_github_https(self):
        for source in list_sources():
            assert source.host == "github.com"
            assert source.url.startswith("https://github.com/")
            assert source.url.endswith(".git")


# ---------------------------------------------------------------------------
# Never execute
# ---------------------------------------------------------------------------


class TestNeverExecutes:
    def test_execute_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="never executes"):
            execute()

    def test_fetched_scripts_are_not_run(self, tmp_path):
        marker = tmp_path / "SHOULD_NOT_EXIST.txt"

        def cloner(url, dest):
            dest.mkdir(parents=True, exist_ok=True)
            # A repo that would love to be executed.
            (dest / "install.sh").write_text(
                f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
            (dest / "setup.py").write_text(
                f"import pathlib; pathlib.Path(r'{marker}').touch()\n", encoding="utf-8")
            return True, ""

        result = fetch("deep-research-skills", tmp_path, cloner=cloner)
        assert result.ok
        assert not marker.exists(), "fetched code must never be executed"

    def test_read_skills_returns_text_only(self, tmp_path):
        dest = tmp_path / "pack"
        _fake_pack()( "url", dest)
        skills = read_skills(dest)
        assert all(isinstance(s.name, str) and isinstance(s.description, str)
                   for s in skills)


# ---------------------------------------------------------------------------
# Sandbox + ephemeral marking
# ---------------------------------------------------------------------------


class TestSandbox:
    def test_sandbox_is_under_genesis(self, tmp_path):
        path = sandbox_for(tmp_path, "deep-research-skills")
        assert path.parent == sandbox_root(tmp_path)
        assert ".genesis" in str(path)

    def test_sandbox_for_validates_id(self, tmp_path):
        with pytest.raises(FetchRefused):
            sandbox_for(tmp_path, "../escape")

    def test_fetch_creates_sandbox(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        assert result.ok
        assert (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").is_dir()

    def test_fetch_writes_ephemeral_manifest(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        manifest = read_manifest(tmp_path / ".genesis" / "sandbox" / "deep-research-skills")
        assert manifest is not None
        assert manifest["ttl_hours"] == DEFAULT_TTL_HOURS
        assert "deep-research-skills" in result.manifest_path or MANIFEST_NAME in result.manifest_path

    def test_manifest_records_purpose(self, tmp_path):
        fetch("software-architecture-skills", tmp_path, cloner=_fake_pack())
        manifest = read_manifest(
            tmp_path / ".genesis" / "sandbox" / "software-architecture-skills")
        assert "45ck/software-architecture-skills" in manifest["purpose"]

    def test_ttl_capped_at_maximum(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path, ttl_hours=999, cloner=_fake_pack())
        assert result.ttl_hours == MAX_TTL_HOURS
        manifest = read_manifest(tmp_path / ".genesis" / "sandbox" / "deep-research-skills")
        assert manifest["ttl_hours"] == MAX_TTL_HOURS

    def test_shorter_ttl_is_honored(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path, ttl_hours=0.5, cloner=_fake_pack())
        assert result.ttl_hours == 0.5

    def test_zero_ttl_refused(self, tmp_path):
        with pytest.raises(FetchRefused):
            fetch("deep-research-skills", tmp_path, ttl_hours=0, cloner=_fake_pack())

    def test_failed_clone_leaves_nothing_behind(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path,
                       cloner=_fake_pack(fail="network unreachable"))
        assert result.ok is False
        assert "network unreachable" in result.error
        assert not (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").exists()

    def test_refetch_reuses_and_refreshes_ttl(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        second = fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        assert second.reused_existing is True
        assert second.ok

    def test_force_reclones(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        marker = tmp_path / ".genesis" / "sandbox" / "deep-research-skills" / "STALE"
        marker.write_text("x", encoding="utf-8")
        second = fetch("deep-research-skills", tmp_path, cloner=_fake_pack(), force=True)
        assert second.reused_existing is False
        assert not marker.exists(), "force must replace the old sandbox"


# ---------------------------------------------------------------------------
# Reading skills
# ---------------------------------------------------------------------------


class TestReadSkills:
    def test_reads_frontmatter(self, tmp_path):
        result = fetch("software-architecture-skills", tmp_path, cloner=_fake_pack())
        names = {s.name for s in result.skills}
        assert {"adr-writer", "tradeoff-analysis-writer"} <= names

    def test_descriptions_captured(self, tmp_path):
        result = fetch("software-architecture-skills", tmp_path, cloner=_fake_pack())
        adr = next(s for s in result.skills if s.name == "adr-writer")
        assert "decision records" in adr.description

    def test_pack_without_skills_is_not_an_error(self, tmp_path):
        def bare(url, dest):
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "README.md").write_text("nothing here\n", encoding="utf-8")
            return True, ""

        result = fetch("deep-research-skills", tmp_path, cloner=bare)
        assert result.ok is True
        assert result.skills == []

    def test_missing_dir_reads_empty(self, tmp_path):
        assert read_skills(tmp_path / "nope") == []

    def test_oversized_skill_file_skipped(self, tmp_path):
        def huge(url, dest):
            skill_dir = dest / "skills" / "big"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("x" * (300 * 1024), encoding="utf-8")
            return True, ""

        result = fetch("deep-research-skills", tmp_path, cloner=huge)
        assert result.skills == [], "a file past the size cap must be skipped"

    def test_name_falls_back_to_directory(self, tmp_path):
        def no_frontmatter(url, dest):
            skill_dir = dest / "skills" / "unnamed-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("# just a heading\n", encoding="utf-8")
            return True, ""

        result = fetch("deep-research-skills", tmp_path, cloner=no_frontmatter)
        assert result.skills[0].name == "unnamed-skill"


class TestFrontmatterParsing:
    def test_basic(self):
        assert _parse_frontmatter("---\nname: x\ndescription: y\n---\n")["name"] == "x"

    def test_no_frontmatter(self):
        assert _parse_frontmatter("# heading\n") == {}

    def test_quotes_stripped(self):
        parsed = _parse_frontmatter('---\ndescription: "quoted value"\n---\n')
        assert parsed["description"] == "quoted value"

    def test_stops_at_closing_fence(self):
        parsed = _parse_frontmatter("---\nname: x\n---\nbody: not-frontmatter\n")
        assert "body" not in parsed

    def test_ignores_list_items_and_comments(self):
        parsed = _parse_frontmatter("---\nname: x\n- item: y\n# c: d\n---\n")
        assert parsed == {"name": "x"}

    def test_empty_string(self):
        assert _parse_frontmatter("") == {}


# ---------------------------------------------------------------------------
# Auto-Purge integration
# ---------------------------------------------------------------------------


class TestPurgeIntegration:
    def test_fresh_sandbox_is_protected_by_purge(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        purge(tmp_path, apply=True)
        assert (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").is_dir()

    def test_expired_sandbox_is_collected_by_purge(self, tmp_path):
        fetch("deep-research-skills", tmp_path, ttl_hours=0.001, cloner=_fake_pack())
        sandbox = tmp_path / ".genesis" / "sandbox" / "deep-research-skills"
        assert sandbox.is_dir()
        # Backdate the manifest so its TTL is unambiguously past.
        manifest_path = sandbox / MANIFEST_NAME
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["created_at"] = "2020-01-01T00:00:00+00:00"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        report = purge(tmp_path, apply=True)
        assert not sandbox.exists()
        assert str(sandbox) in report.purged

    def test_purge_sees_sandbox_as_candidate_in_dry_run(self, tmp_path):
        fetch("deep-research-skills", tmp_path, ttl_hours=0.001, cloner=_fake_pack())
        sandbox = tmp_path / ".genesis" / "sandbox" / "deep-research-skills"
        manifest_path = sandbox / MANIFEST_NAME
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["created_at"] = "2020-01-01T00:00:00+00:00"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        report = purge(tmp_path)
        assert any("deep-research-skills" in str(c.path) for c in report.candidates)
        assert sandbox.is_dir(), "dry run must not delete"


class TestReadOnlyFiles:
    """Regression: git writes pack files read-only, and plain rmtree then fails
    on Windows with "Access is denied". A live fetch of a real repo exposed
    this; a fake clone with no .git/ directory never does."""

    @staticmethod
    def _readonly_pack(url, dest):
        objects = dest / ".git" / "objects" / "pack"
        objects.mkdir(parents=True, exist_ok=True)
        pack = objects / "pack-deadbeef.idx"
        pack.write_bytes(b"binary-ish")
        os.chmod(pack, stat.S_IREAD)  # exactly what git does
        skill_dir = dest / "skills" / "x"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: x\ndescription: d\n---\n", encoding="utf-8")
        return True, ""

    def test_purge_removes_sandbox_with_readonly_files(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=self._readonly_pack)
        sandbox = tmp_path / ".genesis" / "sandbox" / "deep-research-skills"
        manifest_path = sandbox / MANIFEST_NAME
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["created_at"] = "2020-01-01T00:00:00+00:00"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        report = purge(tmp_path, apply=True)
        assert not sandbox.exists(), f"read-only files blocked removal: {report.errors}"
        assert report.errors == []

    def test_discard_removes_sandbox_with_readonly_files(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=self._readonly_pack)
        assert discard("deep-research-skills", tmp_path) is True
        assert not (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").exists()

    def test_force_refetch_over_readonly_sandbox(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=self._readonly_pack)
        result = fetch("deep-research-skills", tmp_path,
                       cloner=self._readonly_pack, force=True)
        assert result.ok is True
        assert result.reused_existing is False


class TestDiscard:
    def test_discard_removes_sandbox(self, tmp_path):
        fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        assert discard("deep-research-skills", tmp_path) is True
        assert not (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").exists()

    def test_discard_absent_is_false(self, tmp_path):
        assert discard("deep-research-skills", tmp_path) is False

    def test_discard_validates_id(self, tmp_path):
        with pytest.raises(FetchRefused):
            discard("../escape", tmp_path)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReporting:
    def test_format_sources_lists_registry(self):
        text = format_sources()
        for source_id in REGISTRY:
            assert source_id in text
        assert "Arbitrary URLs are never fetched" in text

    def test_format_result_states_no_execution(self, tmp_path):
        result = fetch("software-architecture-skills", tmp_path, cloner=_fake_pack())
        text = format_result(result)
        assert "Nothing was executed" in text
        assert "Auto-Purge" in text

    def test_format_result_failure(self, tmp_path):
        result = fetch("deep-research-skills", tmp_path, cloner=_fake_pack(fail="boom"))
        assert "Failed: boom" in format_result(result)

    def test_result_to_dict_round_trips(self, tmp_path):
        result = fetch("software-architecture-skills", tmp_path, cloner=_fake_pack())
        payload = result.to_dict()
        assert payload["ok"] is True
        assert len(payload["skills"]) == result.skill_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_bare_fetch_lists_sources(self, capsys):
        from genesis_architect_pro.gde_cli import main
        assert main(["fetch"]) == 0
        assert "software-architecture-skills" in capsys.readouterr().out

    def test_list_flag(self, capsys):
        from genesis_architect_pro.gde_cli import main
        assert main(["fetch", "--list"]) == 0
        assert "Trusted skill sources" in capsys.readouterr().out

    def test_untrusted_source_exits_2(self, tmp_path, capsys):
        from genesis_architect_pro.gde_cli import main
        rc = main(["fetch", "definitely-not-real", "--dir", str(tmp_path)])
        assert rc == 2
        assert "trusted registry" in capsys.readouterr().err

    def test_bad_dir_exits_1(self, tmp_path):
        from genesis_architect_pro.gde_cli import main
        assert main(["fetch", "deep-research-skills", "--dir", str(tmp_path / "nope")]) == 1

    def test_discard_via_cli(self, tmp_path):
        from genesis_architect_pro.gde_cli import main
        fetch("deep-research-skills", tmp_path, cloner=_fake_pack())
        rc = main(["fetch", "deep-research-skills", "--dir", str(tmp_path), "--discard"])
        assert rc == 0
        assert not (tmp_path / ".genesis" / "sandbox" / "deep-research-skills").exists()

    def test_in_package_namespace(self):
        import genesis_architect_pro as pkg
        for name in ("fetch", "discard", "list_sources", "validate_source", "FetchRefused"):
            assert hasattr(pkg, name)
