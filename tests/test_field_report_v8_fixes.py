"""Regressions for the first field report against v8.0.0.

A user ran the released package on a real project and hit four things. Each
one gets a test here so it cannot come back:

1. `genesis init` with a long vision died on a bare `HTTPError: HTTP Error 422`.
   GitHub caps search queries at 256 characters.
2. The "no repos found" guidance said "try a more specific vision", which is
   backwards: over-specific is what causes it.
3. An empty project scored a perfect 100/100 with 0 modules analysed, and the
   Committee fallback reported full confidence on it. A false green.
4. The Committee silently fell back to three engine perspectives when no LLM
   key was present, while advertising a five-advisor debate.
"""

import pytest

from genesis_architect.core import github
from genesis_architect.core.architecture_scorer import score_project as core_score
from genesis_architect.pro.architecture_scorer import _score_confidence


class TestGitHubQueryLength:
    def test_long_vision_is_trimmed_below_the_api_limit(self):
        vision = "python multi-agent orchestration framework " * 20
        fitted = github._fit_query(vision, github.GITHUB_MAX_QUERY_CHARS - 60)
        assert len(fitted) <= github.GITHUB_MAX_QUERY_CHARS - 60

    def test_trim_cuts_on_a_word_boundary(self):
        """No partial word at the end: a truncated token changes the search."""
        words = "alpha beta gamma delta epsilon".split()
        fitted = github._fit_query(" ".join(words), 14)
        assert not fitted.endswith(" ")
        assert all(w in words for w in fitted.split()), fitted

    def test_short_vision_is_untouched(self):
        assert github._fit_query("a python cli", 200) == "a python cli"

    def test_whitespace_is_normalised(self):
        assert github._fit_query("  a   python\n cli ", 200) == "a python cli"

    def test_422_becomes_an_actionable_error_not_a_bare_httperror(self, monkeypatch):
        import urllib.error

        def boom(url, *a, **k):
            raise urllib.error.HTTPError(url, 422, "Unprocessable Entity", {}, None)

        monkeypatch.setattr(github.urllib.request, "urlopen", boom)
        with pytest.raises(github.GitHubQueryError) as exc:
            github._get("https://api.github.com/search/repositories?q=x")
        msg = str(exc.value)
        assert "422" in msg and str(github.GITHUB_MAX_QUERY_CHARS) in msg

    def test_rate_limit_handling_is_unaffected(self, monkeypatch):
        import urllib.error

        def boom(url, *a, **k):
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

        monkeypatch.setattr(github.urllib.request, "urlopen", boom)
        with pytest.raises(github.GitHubRateLimitError):
            github._get("https://api.github.com/search/repositories?q=x")


class TestNoReposGuidance:
    def test_guidance_does_not_tell_users_to_be_more_specific(self):
        """The failure mode is an over-long, over-specific vision."""
        import inspect

        from genesis_architect import scaffold
        src = inspect.getsource(scaffold)
        assert "more specific vision" not in src
        assert "very long or very niche" in src


class TestEmptyProjectIsNotAPerfectScore:
    def test_empty_project_is_unscored_rather_than_100(self, tmp_path):
        result = core_score(tmp_path)
        assert result["module_count"] == 0
        assert result["scored"] is False
        assert result["total"] is None, "an empty project must not report a grade"
        assert result["unscored_reason"]

    def test_real_project_is_still_scored_normally(self, tmp_path):
        src = tmp_path / "src" / "app"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "main.py").write_text("from app import core\n", encoding="utf-8")
        (src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        result = core_score(tmp_path)
        assert result["scored"] is True
        assert isinstance(result["total"], int) and 0 <= result["total"] <= 100

    def test_confidence_is_zero_when_nothing_was_analysed(self):
        conf, basis = _score_confidence(0, 0, 0)
        assert conf == 0.0
        assert "0 modules" in basis

    def test_confidence_is_low_for_a_handful_of_modules(self):
        conf, _ = _score_confidence(2, 0, 0)
        assert conf <= 0.35

    def test_confidence_still_rises_with_real_evidence(self):
        small, _ = _score_confidence(5, 0, 0)
        large, _ = _score_confidence(60, 0, 5)
        assert large > small


class TestCommitteeIsHonestWithoutAnLLM:
    def _ctx(self, tmp_path):
        from genesis_architect.pro.gde_types import (
            EngineResult, EngineStatus, GDEMode, LifecycleStage, SessionContext,
        )
        ctx = SessionContext(
            session_id="s1", project_dir=tmp_path,
            mode=GDEMode.COMMITTEE, stage=LifecycleStage.EXECUTE,
        )
        ctx.engine_results["architecture_scorer"] = EngineResult(
            engine_id="architecture_scorer", status=EngineStatus.SUCCESS,
            output={"total": 61, "score_label": "fair"})
        return ctx

    def test_missing_api_key_is_reported_not_hidden(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from genesis_architect.pro.gde_engine_adapters import gde_run_committee_analysis
        out = gde_run_committee_analysis(self._ctx(tmp_path))
        joined = " ".join(out.get("_warnings", []))
        assert "ANTHROPIC_API_KEY" in joined
        assert "not a Committee debate" in joined

    def test_fallback_never_claims_full_confidence(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from genesis_architect.pro.gde_engine_adapters import gde_run_committee_analysis
        out = gde_run_committee_analysis(self._ctx(tmp_path))
        assert out["_confidence"] <= 0.6, "aggregation must not report certainty"

    def test_fallback_report_is_not_titled_committee_analysis(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from genesis_architect.pro.gde_engine_adapters import gde_run_committee_analysis
        out = gde_run_committee_analysis(self._ctx(tmp_path))
        payload = out["_pending_writes"][0]["payload"]
        assert "Engine Perspectives" in payload
        assert "not a Committee debate" in payload


class TestNoLicenceTierLeftovers:
    def test_committee_transparency_is_not_gated_on_a_licence_tier(self):
        """Everyone gets the full transcript: there are no tiers any more."""
        import inspect

        from genesis_architect.pro import gde_engine_adapters
        src = inspect.getsource(gde_engine_adapters.gde_run_committee_analysis)
        assert "license_tier" not in src
        assert "TransparencyProfile.FREE" not in src
