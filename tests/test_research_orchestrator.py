"""Tests for research_orchestrator module - no network, no disk I/O."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_architect_pro.research_orchestrator import (
    ResearchSummary,
    RepoResult,
    build_summary_from_raw,
    check_floor,
    compute_quality,
    compute_coverage,
    is_uncertain,
    merge_streams,
    format_summary,
    FLOOR_MIN_REPOS,
    FLOOR_MIN_DEEP,
    classify_domain,
    normalize_streams,
    save_to_vault,
    load_from_vault,
)
from genesis_architect_pro.research_outline import Outline


# --- helpers ---

def _repos(n: int, deep: int = 0) -> list[dict]:
    return [
        {"name": f"owner/repo{i}", "stars": 100 + i, "url": f"https://github.com/owner/repo{i}",
         "description": f"Repo {i}", "deep_analyzed": i < deep}
        for i in range(n)
    ]


def _issues(n: int) -> list[dict]:
    return [
        {"title": f"Issue {i}", "url": f"https://github.com/owner/repo/issues/{i}",
         "comments": 6, "reactions": 4, "category": "bug", "labels": ["bug"], "body": ""}
        for i in range(n)
    ]


# --- floor gate ---

def test_floor_passes_with_enough_repos():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, f"https://github.com/o/r{i}", "", i < 6)
                     for i in range(13)]
    ok, _ = check_floor(summary)
    assert ok


def test_floor_fails_too_few_repos():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(5)]
    ok, msg = check_floor(summary)
    assert not ok
    assert "Floor not met" in msg


def test_floor_fails_too_few_deep():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", i < 2) for i in range(13)]
    ok, _ = check_floor(summary)
    assert not ok


def test_floor_message_includes_options():
    summary = ResearchSummary(vision="test")
    summary.repos = []
    _, msg = check_floor(summary)
    assert "Broaden" in msg or "override" in msg or "Architect" in msg


# --- quality signal ---

def test_quality_full():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(9)]
    from genesis_architect_pro.pitfall_ranker import RankedPitfall
    summary.pitfall_candidates = [
        RankedPitfall(f"Issue {i}", f"https://x/{i}", "github_issues", "high", "pitfall", "x")
        for i in range(6)
    ]
    assert compute_quality(summary) == "FULL"


def test_quality_thin():
    summary = ResearchSummary(vision="test")
    summary.repos = []
    summary.pitfall_candidates = []
    assert compute_quality(summary) == "THIN"


def test_quality_partial():
    summary = ResearchSummary(vision="test")
    summary.repos = [RepoResult(f"o/r{i}", 100, "", "", True) for i in range(6)]
    summary.pitfall_candidates = []
    assert compute_quality(summary) == "PARTIAL"


# --- merge_streams ---

def test_merge_streams_github_issues():
    issues = _issues(3)
    ranked, _ = merge_streams(issues, [], [], "FastAPI")
    assert len(ranked) > 0
    assert all(p.source == "github_issues" for p in ranked)


def test_merge_streams_exa_results():
    exa = [{"url": "https://reddit.com/r/python/comments/abc",
             "title": "FastAPI lessons learned", "text": "avoid sync in async", "score": 60}]
    ranked, _ = merge_streams([], exa, [], "FastAPI")
    assert any(p.source == "reddit" for p in ranked)


def test_merge_streams_video_signals():
    video_exa = [{"url": "https://youtube.com/watch?v=abc",
                  "title": "FastAPI mistakes postmortem", "text": "we learned the hard way",
                  "author": "DevChannel"}]
    ranked, video_signals = merge_streams([], [], video_exa, "FastAPI")
    assert len(video_signals) > 0


def test_merge_streams_ranked_descending():
    issues = _issues(5)
    ranked, _ = merge_streams(issues, [], [], "test")
    scores = [p.score for p in ranked]
    assert scores == sorted(scores, reverse=True)


def test_merge_streams_caps_at_10():
    issues = _issues(20)
    ranked, _ = merge_streams(issues, [], [], "test")
    assert len(ranked) <= 10


# --- build_summary_from_raw ---

def test_build_summary_sets_vision():
    s = build_summary_from_raw("My FastAPI App", _repos(5), [], [], [])
    assert s.vision == "My FastAPI App"


def test_build_summary_computes_quality():
    s = build_summary_from_raw("test", _repos(2), [], [], [])
    assert s.research_quality in ("FULL", "PARTIAL", "THIN")


def test_build_summary_vault_save(tmp_path):
    s = build_summary_from_raw("test vision", _repos(3), _issues(2), [], [],
                                project_root=tmp_path)
    assert s.vision == "test vision"
    vault_file = tmp_path / ".genesis" / "vault" / "index.json"
    assert vault_file.exists()


def test_build_summary_floor_flag():
    s = build_summary_from_raw("test", _repos(FLOOR_MIN_REPOS + 1, deep=FLOOR_MIN_DEEP + 1),
                                _issues(6), [], [])
    assert s.floor_met is True


# --- format_summary ---

def test_format_summary_includes_quality():
    s = build_summary_from_raw("test", [], [], [], [])
    output = format_summary(s)
    assert "Research quality" in output or "THIN" in output


def test_format_summary_shows_repos():
    s = build_summary_from_raw("test", _repos(3), [], [], [])
    output = format_summary(s)
    assert "repo" in output.lower() or "owner" in output.lower()


def test_format_summary_floor_warning_when_not_met():
    s = build_summary_from_raw("test", _repos(2), [], [], [])
    output = format_summary(s)
    assert "Floor not met" in output or "Options" in output or "Broaden" in output


# --- SKILL.md integration ---




# --- domain-aware floor (a non-code vision has no repo corpus) ---

def test_classify_domain_code_vision():
    assert classify_domain("build a FastAPI service with a Postgres backend") == "code"
    assert classify_domain("a CLI tool for log parsing") == "code"


def test_classify_domain_non_code_vision():
    assert classify_domain(
        "extract a house standard from a design studio archive"
    ) == "non_code"
    assert classify_domain("write onboarding guidelines for new editorial hires") == "non_code"


def test_classify_domain_ties_resolve_to_code():
    """Biased toward code: weakening the repo floor is the costlier mistake."""
    assert classify_domain("something entirely ambiguous") == "code"


def test_non_code_floor_counts_sources_not_repos():
    """A non-repo-shaped problem must not fail on a repo count it can never meet."""
    topics = ["tracking metrics", "baseline grid", "colour proofing", "kerning pairs",
              "paper stock", "logo clearspace", "export presets", "archive naming",
              "print bleed"]
    web = [
        {"url": f"https://community.example{i}.com/thread/{i}",
         "title": f"House rule for {topic}",
         "text": "```css\n.tracking { letter-spacing: 0.02em; }\n```"}
        for i, topic in enumerate(topics)
    ]
    s = build_summary_from_raw(
        "extract a house standard from a studio archive",
        repos=[], github_issues=[], web_results=web, media_results=[],
    )
    assert s.domain == "non_code"
    passed, message = check_floor(s)
    assert passed, message
    assert "repos are not the unit" in message


def test_non_code_floor_still_blocks_thin_research():
    """The gate must survive the domain switch - only its unit changes."""
    s = build_summary_from_raw(
        "extract a house standard from a studio archive",
        repos=[], github_issues=[],
        web_results=[{"url": "https://a-blog.com/p", "title": "One post", "text": "prose"}],
        media_results=[],
    )
    assert check_floor(s)[0] is False
    assert "Floor not met" in check_floor(s)[1]


def test_code_floor_message_offers_the_domain_escape():
    s = build_summary_from_raw("build a CLI tool", _repos(2), [], [], [])
    assert "--domain non-code" in check_floor(s)[1]


# --- stream naming (provider-neutral, back-compatible) ---

def test_legacy_stream_keys_still_load():
    raw = {"exa_results": [{"url": "https://a.com", "title": "t", "text": "x"}],
           "video_exa_results": [{"url": "https://youtube.com/watch?v=1", "title": "talk"}]}
    normalized = normalize_streams(raw)
    assert "exa_results" not in normalized
    assert len(normalized["web_results"]) == 1
    assert len(normalized["media_results"]) == 1


def test_legacy_and_canonical_keys_merge_rather_than_overwrite():
    raw = {"web_results": [{"url": "https://a.com", "title": "a"}],
           "exa_results": [{"url": "https://b.com", "title": "b"}]}
    assert len(normalize_streams(raw)["web_results"]) == 2


def test_build_summary_accepts_legacy_kwargs():
    s = build_summary_from_raw(
        "test", _repos(1), [],
        exa_results=[{"url": "https://a.com", "title": "t", "text": "x"}],
    )
    assert len(s.pitfall_candidates) == 1


def test_provider_recorded_per_item_not_in_the_field_name():
    s = build_summary_from_raw(
        "test", [], [],
        web_results=[{"url": "https://a.com", "title": "t", "text": "x",
                      "provider": "tavily"}],
    )
    assert s.pitfall_candidates[0].provider == "tavily"


# --- machine-readable output ---

def test_to_dict_is_json_serializable_and_carries_the_verdict():
    import json
    s = build_summary_from_raw("build a CLI tool", _repos(3), [], [], [])
    payload = s.to_dict()
    assert json.loads(json.dumps(payload))["domain"] == "code"
    assert payload["floor_met"] is False
    assert "floor_message" in payload
    assert payload["repos"][0]["slug"] == "owner/repo0"


def test_summary_names_the_command_that_closes_the_video_loop():
    """Stream D hands out /watch commands; the return leg must be named too."""
    s = build_summary_from_raw(
        "a task queue service", repos=[], github_issues=[], web_results=[],
        media_results=[{"url": "https://www.youtube.com/watch?v=1",
                        "title": "Lessons learned running queues",
                        "text": "what we wish we knew"}],
    )
    output = format_summary(s)
    assert "--absorb" in output
    assert "a task queue service" in output


# --- R2: outline-driven coverage ---

class TestComputeCoverage:
    def test_no_outline_returns_none_not_zero(self):
        """Not applicable must never render as 'measured and empty' -
        same discipline as RepoResult.stars: int | None."""
        s = ResearchSummary(vision="test")
        assert compute_coverage(s) is None

    def test_outline_with_no_items_returns_none(self):
        s = ResearchSummary(vision="test", outline=Outline(topic="t", fields=["license"]))
        assert compute_coverage(s) is None

    def test_outline_with_no_fields_returns_none(self):
        s = ResearchSummary(vision="test", outline=Outline(topic="t", items=["fastapi"]))
        assert compute_coverage(s) is None

    def test_fully_covered_grid_is_one(self):
        outline = Outline(topic="t", items=["fastapi", "django"], fields=["license"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={"fastapi": {"license": "MIT"}, "django": {"license": "BSD"}},
        )
        assert compute_coverage(s) == 1.0

    def test_empty_findings_is_zero_not_none(self):
        """An outline WAS used, it just found nothing yet - that is a real
        0.0, distinct from "no outline at all" (None)."""
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = ResearchSummary(vision="test", outline=outline)
        assert compute_coverage(s) == 0.0

    def test_partial_grid_computes_the_fraction(self):
        outline = Outline(topic="t", items=["a", "b"], fields=["license", "cve"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={"a": {"license": "MIT"}},  # 1 of 4 cells filled
        )
        assert compute_coverage(s) == 0.25

    def test_blank_string_value_does_not_count_as_filled(self):
        outline = Outline(topic="t", items=["a"], fields=["license"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={"a": {"license": "   "}},
        )
        assert compute_coverage(s) == 0.0

    def test_uncertain_marker_still_counts_as_filled(self):
        """Coverage measures completeness (did we look?), not confidence -
        that split is what R3's uncertain list is for, not this metric."""
        outline = Outline(topic="t", items=["a"], fields=["license"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={"a": {"license": "[uncertain]"}},
        )
        assert compute_coverage(s) == 1.0

    def test_stray_item_not_in_outline_does_not_inflate_coverage(self):
        outline = Outline(topic="t", items=["a"], fields=["license"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={
                "a": {"license": "MIT"},
                "not_in_outline": {"license": "GPL"},
            },
        )
        assert compute_coverage(s) == 1.0

    def test_stray_field_not_in_outline_does_not_inflate_coverage(self):
        outline = Outline(topic="t", items=["a"], fields=["license"])
        s = ResearchSummary(
            vision="test", outline=outline,
            item_findings={"a": {"license": "MIT", "not_a_declared_field": "x"}},
        )
        assert compute_coverage(s) == 1.0


class TestBuildSummaryAcceptsOutline:
    def test_outline_is_stored_on_the_summary(self):
        outline = Outline(topic="library shortlist", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw("test", [], [], outline=outline)
        assert s.outline is outline

    def test_coverage_is_computed_at_build_time(self):
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"fastapi": {"license": "MIT"}},
        )
        assert s.coverage == 1.0

    def test_no_outline_leaves_coverage_none(self):
        s = build_summary_from_raw("test", _repos(3), [])
        assert s.outline is None
        assert s.coverage is None

    def test_item_findings_default_to_empty_dict(self):
        s = build_summary_from_raw("test", [], [])
        assert s.item_findings == {}

    def test_to_dict_carries_outline_and_coverage(self):
        outline = Outline(topic="t", items=["a"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"a": {"license": "MIT"}},
        )
        payload = s.to_dict()
        assert payload["coverage"] == 1.0
        assert payload["outline"]["topic"] == "t"
        assert payload["item_findings"] == {"a": {"license": "MIT"}}

    def test_to_dict_outline_is_none_when_absent(self):
        s = build_summary_from_raw("test", [], [])
        payload = s.to_dict()
        assert payload["outline"] is None


class TestOutlineVaultRoundTrip:
    def test_outline_and_findings_survive_vault_round_trip(self, tmp_path):
        outline = Outline(
            topic="observability vendors", items=["datadog"], fields=["pricing"],
            created_at="2026-08-18T00:00:00+00:00",
        )
        original = build_summary_from_raw(
            "vault outline test", [], [], outline=outline,
            item_findings={"datadog": {"pricing": "usage-based"}},
            project_root=tmp_path,
        )
        loaded = load_from_vault("vault outline test", tmp_path)

        assert original.outline is not None  # the build call above set it
        assert loaded is not None
        assert loaded.outline is not None
        assert loaded.outline.topic == outline.topic
        assert loaded.outline.items == outline.items
        assert loaded.outline.fields == outline.fields
        assert loaded.item_findings == {"datadog": {"pricing": "usage-based"}}
        assert loaded.coverage == 1.0

    def test_no_outline_round_trips_as_none(self, tmp_path):
        build_summary_from_raw("no outline here", _repos(2), [], project_root=tmp_path)
        loaded = load_from_vault("no outline here", tmp_path)

        assert loaded is not None
        assert loaded.outline is None
        assert loaded.coverage is None

    def test_manually_saved_summary_round_trips_outline(self, tmp_path):
        """save_to_vault used directly, not just via build_summary_from_raw."""
        outline = Outline(topic="t", items=["a"], fields=["f"])
        summary = ResearchSummary(
            vision="direct save test", outline=outline,
            item_findings={"a": {"f": "value"}}, coverage=1.0,
        )
        save_to_vault(summary, tmp_path)
        loaded = load_from_vault("direct save test", tmp_path)

        assert loaded is not None
        assert loaded.outline is not None
        assert loaded.outline.topic == "t"
        assert loaded.coverage == 1.0


# --- R3: uncertain values are skipped in the rendered report, not printed ---

class TestIsUncertain:
    def test_default_is_not_uncertain(self):
        s = ResearchSummary(
            vision="test", item_findings={"a": {"license": "MIT"}},
        )
        assert is_uncertain(s, "a", "license") is False

    def test_literal_marker_value_is_uncertain(self):
        s = ResearchSummary(
            vision="test", item_findings={"a": {"license": "[uncertain]"}},
        )
        assert is_uncertain(s, "a", "license") is True

    def test_uncertain_list_entry_marks_it_even_with_a_real_value(self):
        """The two mechanisms are independent: a caller who kept the marker
        separate from the value must still get skipped."""
        s = ResearchSummary(
            vision="test",
            item_findings={"a": {"license": "MIT"}},
            uncertain=["a:license"],
        )
        assert is_uncertain(s, "a", "license") is True

    def test_missing_value_is_not_uncertain_just_absent(self):
        """Absent and uncertain are different states - absent means never
        looked up, uncertain means looked up and not trusted."""
        s = ResearchSummary(vision="test")
        assert is_uncertain(s, "a", "license") is False

    def test_uncertain_entry_for_a_different_item_does_not_leak(self):
        s = ResearchSummary(
            vision="test",
            item_findings={"a": {"license": "MIT"}, "b": {"license": "MIT"}},
            uncertain=["b:license"],
        )
        assert is_uncertain(s, "a", "license") is False
        assert is_uncertain(s, "b", "license") is True


class TestFormatSummaryResearchGrid:
    def test_no_outline_omits_the_grid_section_entirely(self):
        s = build_summary_from_raw("test", [], [])
        assert "Research Grid" not in format_summary(s)

    def test_filled_field_is_rendered(self):
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"fastapi": {"license": "MIT"}},
        )
        output = format_summary(s)
        assert "Research Grid" in output
        assert "fastapi" in output
        assert "license: MIT" in output

    def test_marker_value_is_skipped_not_printed(self):
        """The literal string "[uncertain]" must never reach the reader -
        that would misrepresent a guess as a confirmed finding."""
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"fastapi": {"license": "[uncertain]"}},
        )
        output = format_summary(s)
        assert "[uncertain]" not in output

    def test_uncertain_list_entry_is_also_skipped(self):
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"fastapi": {"license": "MIT"}},
        )
        s.uncertain = ["fastapi:license"]
        output = format_summary(s)
        assert "license: MIT" not in output

    def test_item_with_only_uncertain_fields_does_not_appear_at_all(self):
        """An item whose every field got skipped shouldn't leave a bare,
        empty header behind."""
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={"fastapi": {"license": "[uncertain]"}},
        )
        output = format_summary(s)
        assert "fastapi" not in output

    def test_mixed_certain_and_uncertain_fields_only_shows_certain(self):
        outline = Outline(
            topic="t", items=["fastapi"], fields=["license", "maintenance"]
        )
        s = build_summary_from_raw(
            "test", [], [], outline=outline,
            item_findings={
                "fastapi": {"license": "MIT", "maintenance": "[uncertain]"}
            },
        )
        output = format_summary(s)
        assert "license: MIT" in output
        assert "maintenance" not in output

    def test_empty_grid_section_omitted_when_nothing_filled_yet(self):
        outline = Outline(topic="t", items=["fastapi"], fields=["license"])
        s = build_summary_from_raw("test", [], [], outline=outline)
        assert "Research Grid" not in format_summary(s)


class TestUncertainPersistence:
    def test_to_dict_carries_uncertain_list(self):
        s = build_summary_from_raw("test", [], [])
        s.uncertain = ["a:license"]
        assert s.to_dict()["uncertain"] == ["a:license"]

    def test_uncertain_defaults_to_empty_list(self):
        s = build_summary_from_raw("test", [], [])
        assert s.uncertain == []

    def test_uncertain_round_trips_through_vault(self, tmp_path):
        summary = ResearchSummary(vision="uncertain vault test", uncertain=["a:license"])
        save_to_vault(summary, tmp_path)
        loaded = load_from_vault("uncertain vault test", tmp_path)

        assert loaded is not None
        assert loaded.uncertain == ["a:license"]

    def test_missing_uncertain_key_in_old_vault_entry_defaults_to_empty(self, tmp_path):
        """A vault entry saved before R3 existed has no 'uncertain' key at
        all - loading it must not raise."""
        import json as _json
        from genesis_architect.core import vault as _vault

        _vault.put(
            key="research:pre-r3 entry",
            solution=_json.dumps({"vision": "pre-r3 entry"}),
            source_url="genesis:research_orchestrator",
            project_root=tmp_path,
        )
        loaded = load_from_vault("pre-r3 entry", tmp_path)
        assert loaded is not None
        assert loaded.uncertain == []
