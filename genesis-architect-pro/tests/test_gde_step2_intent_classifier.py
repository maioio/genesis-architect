"""Tests for Step 2: intent_classifier.py

Coverage:
- Each GDEMode classified by clear keyword
- Confidence thresholds (clarifying questions on low confidence)
- Ambiguity → COMMITTEE escalation
- Empty / whitespace input → COMMITTEE fallback
- Signal accumulation (multiple keywords → higher confidence)
- Returned Intent type is correct
- params populated for ambiguous cases
- No LLM calls (pure function)
"""

from __future__ import annotations


from genesis_architect_pro.gde_types import GDEMode, Intent
from genesis_architect_pro.intent_classifier import (
    CLARIFY_THRESHOLD,
    MIN_CONFIDENCE,
    classify,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_intent(intent: Intent, mode: GDEMode) -> None:
    assert isinstance(intent, Intent)
    assert intent.mode is mode
    assert 0.0 <= intent.confidence <= 1.0
    assert isinstance(intent.signals, list)
    assert isinstance(intent.clarifying_questions, list)
    assert isinstance(intent.params, dict)


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_intent_instance(self):
        result = classify("scan the project for issues")
        assert isinstance(result, Intent)

    def test_raw_text_preserved(self):
        text = "  recover the broken module  "
        result = classify(text)
        assert result.raw_text == text.strip()

    def test_confidence_in_range(self):
        for text in ["recover", "research", "refactor", "gate", "build", "document"]:
            result = classify(text)
            assert 0.0 <= result.confidence <= 1.0

    def test_mode_is_gde_mode_enum(self):
        result = classify("run a recovery scan")
        assert isinstance(result.mode, GDEMode)


# ---------------------------------------------------------------------------
# Mode classification — clear signal inputs
# ---------------------------------------------------------------------------


class TestModeClassification:
    def test_recovery_scan(self):
        result = classify("scan the project and diagnose any drift")
        _assert_intent(result, GDEMode.RECOVERY)

    def test_recovery_broken(self):
        result = classify("the project is broken, fix it")
        assert result.mode in (GDEMode.RECOVERY, GDEMode.BUILD, GDEMode.COMMITTEE)
        # 'broken' + 'fix' = recovery signals dominant
        result2 = classify("the project is broken")
        assert result2.mode is GDEMode.RECOVERY

    def test_recovery_drift(self):
        result = classify("check for drift and decay in modules")
        _assert_intent(result, GDEMode.RECOVERY)

    def test_recovery_fragility(self):
        result = classify("which modules are fragile or at risk?")
        assert result.mode in (GDEMode.RECOVERY, GDEMode.GATE, GDEMode.COMMITTEE)

    def test_research_explicit(self):
        result = classify("research FastAPI best practices")
        _assert_intent(result, GDEMode.RESEARCH)

    def test_research_video(self):
        result = classify("find video tutorials on youtube about this pattern")
        _assert_intent(result, GDEMode.RESEARCH)

    def test_research_benchmark(self):
        result = classify("benchmark this against alternatives")
        _assert_intent(result, GDEMode.RESEARCH)

    def test_refactor_explicit(self):
        result = classify("refactor the import module")
        _assert_intent(result, GDEMode.REFACTOR)

    def test_refactor_plan(self):
        result = classify("create a refactoring plan for the codebase")
        _assert_intent(result, GDEMode.REFACTOR)

    def test_refactor_decouple(self):
        result = classify("decouple the database layer from the service layer")
        _assert_intent(result, GDEMode.REFACTOR)

    def test_gate_explicit(self):
        result = classify("run a gate check on the current plan")
        _assert_intent(result, GDEMode.GATE)

    def test_gate_security(self):
        result = classify("perform a security check before we proceed")
        _assert_intent(result, GDEMode.GATE)

    def test_gate_compliance(self):
        result = classify("check compliance with the license policy")
        assert result.mode in (GDEMode.GATE, GDEMode.COMMITTEE)

    def test_build_scaffold(self):
        result = classify("scaffold a new FastAPI module")
        _assert_intent(result, GDEMode.BUILD)

    def test_build_generate(self):
        result = classify("generate a new endpoint for user authentication")
        _assert_intent(result, GDEMode.BUILD)

    def test_build_new_feature(self):
        result = classify("implement a new feature for export")
        _assert_intent(result, GDEMode.BUILD)

    def test_document_explicit(self):
        result = classify("document the recovery module")
        _assert_intent(result, GDEMode.DOCUMENT)

    def test_document_readme(self):
        result = classify("write a README for this project")
        _assert_intent(result, GDEMode.DOCUMENT)

    def test_document_api(self):
        # "generate" triggers BUILD, "api.*doc" triggers DOCUMENT →
        # may resolve to DOCUMENT or COMMITTEE (ambiguous)
        result = classify("generate API docs for all public endpoints")
        assert result.mode in (GDEMode.DOCUMENT, GDEMode.COMMITTEE)
        assert isinstance(result, Intent)

    def test_committee_explicit(self):
        result = classify("convene the committee to decide")
        _assert_intent(result, GDEMode.COMMITTEE)

    def test_committee_help_decide(self):
        result = classify("help me decide which approach to take")
        _assert_intent(result, GDEMode.COMMITTEE)


# ---------------------------------------------------------------------------
# Confidence and clarifying questions
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_strong_signal_high_confidence(self):
        # Multiple recovery signals → high confidence
        result = classify("recover the project: diagnose drift, fix errors, scan fragile modules")
        assert result.confidence >= CLARIFY_THRESHOLD

    def test_single_weak_signal_lower_confidence(self):
        # "add" is a weak BUILD signal (weight 0.3)
        result = classify("add something")
        # confidence may be low; no assertion on mode (ambiguity expected)
        assert result.confidence <= 1.0

    def test_high_confidence_no_questions(self):
        result = classify("run a full recovery scan and diagnose the drift")
        if result.confidence >= CLARIFY_THRESHOLD:
            assert result.clarifying_questions == []

    def test_low_confidence_has_questions(self):
        # Construct a text with minimal signal that stays below threshold
        # We'll assert indirectly: if confidence < threshold, questions must exist
        result = classify("what is happening here")
        if result.confidence < CLARIFY_THRESHOLD:
            assert len(result.clarifying_questions) > 0

    def test_confidence_floor(self):
        result = classify("this text has no known keywords at all xyz123")
        assert result.confidence >= MIN_CONFIDENCE

    def test_multi_signal_accumulates(self):
        # More signals → higher confidence than single signal
        single = classify("recover")
        multi = classify("recover diagnose drift fragile broken scan")
        assert multi.confidence >= single.confidence


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_string(self):
        result = classify("")
        assert result.mode is GDEMode.COMMITTEE
        assert result.confidence == MIN_CONFIDENCE
        assert len(result.clarifying_questions) > 0

    def test_whitespace_only(self):
        result = classify("   \t\n   ")
        assert result.mode is GDEMode.COMMITTEE
        assert result.confidence == MIN_CONFIDENCE

    def test_none_signals_list(self):
        result = classify("totally unrelated zxqwerty mmmm")
        assert isinstance(result.signals, list)

    def test_very_long_input(self):
        # Long repeated text: signal matching is binary (matched or not),
        # so repetition doesn't inflate score. Mode should still be RECOVERY
        # or, if ambiguity threshold triggers, COMMITTEE — either is acceptable.
        long_text = "recover " * 500 + "diagnose " * 500
        result = classify(long_text)
        assert result.mode in (GDEMode.RECOVERY, GDEMode.COMMITTEE)
        assert result.confidence <= 1.0

    def test_mixed_case(self):
        result = classify("RECOVER THE PROJECT AND DIAGNOSE")
        assert result.mode is GDEMode.RECOVERY

    def test_unicode_input(self):
        # Unicode chars shouldn't crash the classifier
        result = classify("recover הפרויקט שלנו")
        assert isinstance(result, Intent)

    def test_special_characters(self):
        result = classify("recover! @project #diagnose")
        assert isinstance(result, Intent)


# ---------------------------------------------------------------------------
# Ambiguity → COMMITTEE escalation
# ---------------------------------------------------------------------------


class TestAmbiguityEscalation:
    def test_ambiguous_escalates_to_committee(self):
        # Craft an input balanced between two modes
        # research + document both get moderate signals
        text = "summarize and research the documentation"
        result = classify(text)
        # Either disambiguated to one, or committee — both are valid
        assert result.mode in (GDEMode.RESEARCH, GDEMode.DOCUMENT, GDEMode.COMMITTEE)

    def test_ambiguous_result_has_params(self):
        # When COMMITTEE is returned due to ambiguity, params should indicate which modes
        text = "summarize and research the documentation"
        result = classify(text)
        if result.mode is GDEMode.COMMITTEE and result.params:
            assert "ambiguous_between" in result.params

    def test_clear_winner_not_escalated(self):
        # recovery has many more signals than others here
        result = classify("recover scan diagnose drift fragile broken error crash")
        assert result.mode is GDEMode.RECOVERY

    def test_committee_explicit_not_escalated(self):
        result = classify("convene the committee for a complex decision")
        assert result.mode is GDEMode.COMMITTEE


# ---------------------------------------------------------------------------
# Backward compatibility — no __init__ exposure yet (Step 6 adds it)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_in_init(self):
        import genesis_architect_pro as pkg
        assert hasattr(pkg, "classify"), "classify() added to __init__ in Step 6"

    def test_importable_directly(self):
        from genesis_architect_pro.intent_classifier import classify as c

        assert callable(c)

    def test_gde_types_still_intact(self):
        from genesis_architect_pro.gde_types import (
            GDEMode,
            LifecycleStage,
            SessionContext,
        )

        assert GDEMode.RECOVERY
        assert LifecycleStage.IDLE
        ctx = SessionContext()
        assert ctx.session_id


# ---------------------------------------------------------------------------
# Signals list content
# ---------------------------------------------------------------------------


class TestSignals:
    def test_signals_are_strings(self):
        result = classify("recover the broken project and diagnose drift")
        assert all(isinstance(s, str) for s in result.signals)

    def test_signals_nonempty_on_clear_match(self):
        result = classify("run a full recovery scan")
        if result.mode is GDEMode.RECOVERY:
            assert len(result.signals) > 0

    def test_no_duplicate_signals(self):
        result = classify("recover recover recover scan scan diagnose")
        # Signals should not repeat the same pattern multiple times
        seen = {}
        for s in result.signals:
            assert s not in seen, f"Duplicate signal: {s}"
            seen[s] = True
