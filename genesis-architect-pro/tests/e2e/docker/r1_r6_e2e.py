"""R1-R6 pipeline E2E simulation: outline -> deep research -> report.

Not a unit test. This drives the whole outline-driven research chain through
one real project directory, in the order a live GDE session would, and
asserts on the seams between the six commits rather than inside any one of
them:

  R1  domain-aware research floor
  R2  Outline accepted, coverage computed
  R3  unconfident values withheld from the rendered report
  R4  RESEARCH_COVERAGE_LOW gate
  R5  outline wired into registry, gate list, and floor
  R6  advisor names the outline -> deep -> report flow

Run inside the clean-room container, where nothing is pre-provisioned.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from genesis_architect_pro import research_orchestrator as ro
from genesis_architect_pro.gde_engine_adapters import gde_run_research_outline
from genesis_architect_pro.gde_gate_engine import evaluate_gates
from genesis_architect_pro.gde_planner import build_plan
from genesis_architect_pro.gde_types import (
    EngineResult,
    EngineStatus,
    GateAction,
    GDEMode,
    SessionContext,
)
from genesis_architect_pro.research_outline import Outline, load_outline, save_outline

FAILURES: list[str] = []
STEPS = 0


def _fired(report):
    """Every gate that actually triggered, at any severity.

    GateReport buckets by outcome rather than exposing a flat list, so a
    caller asking "did this gate fire?" has to union the three non-passing
    buckets - checking only `blocks` would miss a gate demoted to a warning.
    """
    return [*report.hard_blocks, *report.blocks, *report.warnings]


def check(label: str, condition: bool, detail: str = "") -> None:
    global STEPS
    STEPS += 1
    if condition:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" -- {detail}" if detail else ""))
        FAILURES.append(label)


TOPIC = "self-hosted vector databases for a RAG service"
ITEMS = ["qdrant", "weaviate", "milvus", "pgvector"]
FIELDS = ["license", "hybrid_search", "ops_burden"]


def build_summary(project, findings, uncertain):
    outline = load_outline(project)
    summary = ro.ResearchSummary(
        vision=TOPIC,
        outline=outline,
        item_findings=findings,
        uncertain=uncertain,
    )
    summary.coverage = ro.compute_coverage(summary)
    return summary


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)

        # -- R2/R5: an outline is stated before any research happens ---------
        print("\nR2/R5 -- outline stated up front, then read back")
        save_outline(Outline(topic=TOPIC, items=ITEMS, fields=FIELDS), project)
        reloaded = load_outline(project)
        check("outline round-trips through .genesis/research/", reloaded is not None)
        check("outline grid preserved", reloaded.items == ITEMS and reloaded.fields == FIELDS)

        # -- R5: the outline is reachable as a real engine --------------------
        print("\nR5 -- outline surfaced through the engine adapter")
        ctx = SessionContext(mode=GDEMode.RESEARCH, project_dir=project)
        adapter_out = gde_run_research_outline(ctx)
        check("adapter returns the confirmed topic", adapter_out.get("topic") == TOPIC,
              repr(adapter_out.get("topic")))
        check("adapter reports no 'opportunistic' warning once an outline exists",
              not adapter_out.get("_warnings"))

        # -- R5: the gate is actually required in RESEARCH mode ---------------
        plan = build_plan(ctx)
        gate_ids = getattr(plan, "required_gate_ids", None) or getattr(plan, "gates", [])
        check("RESEARCH mode requires RESEARCH_COVERAGE_LOW",
              "RESEARCH_COVERAGE_LOW" in gate_ids, str(gate_ids))

        # -- R2: coverage measured against the declared grid ------------------
        print("\nR2 -- coverage measured against the grid (thin pass)")
        thin = build_summary(project, {
            "qdrant": {"license": "Apache-2.0", "hybrid_search": "yes"},
            "weaviate": {"license": "BSD-3-Clause"},
        }, [])
        check("thin pass coverage is 3/12", abs(thin.coverage - 0.25) < 1e-9,
              str(thin.coverage))

        # -- R5: coverage IS the floor when an outline was used ---------------
        floor_ok, floor_msg = ro.check_floor(thin)
        check("floor not met at 25% coverage", floor_ok is False, floor_msg)

        # -- R4: the gate fires and pauses the session ------------------------
        print("\nR4 -- gate fires below the 50% threshold")
        ctx.engine_results["field_intelligence"] = EngineResult(
            engine_id="field_intelligence",
            status=EngineStatus.SUCCESS,
            output={"coverage": thin.coverage, "outline": {"topic": TOPIC}},
        )
        report = evaluate_gates(ctx, list(gate_ids))
        fired = {r.gate_id: r for r in _fired(report)}
        check("RESEARCH_COVERAGE_LOW triggered", "RESEARCH_COVERAGE_LOW" in fired,
              str(sorted(fired)))
        if "RESEARCH_COVERAGE_LOW" in fired:
            g = fired["RESEARCH_COVERAGE_LOW"]
            check("gate asks rather than hard-blocks", g.action == GateAction.BLOCK_AND_ASK,
                  str(g.action))
            check("gate reason cites the measured coverage", "25%" in g.reason, g.reason)

        # -- absent coverage is "not applicable", never a low score -----------
        print("\nR2/R4 -- no outline means no coverage, and no false alarm")
        bare = ro.ResearchSummary(vision=TOPIC)
        check("coverage is None without an outline", ro.compute_coverage(bare) is None)
        ctx_bare = SessionContext(mode=GDEMode.RESEARCH, project_dir=project)
        ctx_bare.engine_results["field_intelligence"] = EngineResult(
            engine_id="field_intelligence", status=EngineStatus.SUCCESS,
            output={"coverage": None},
        )
        bare_fired = {r.gate_id for r in _fired(evaluate_gates(ctx_bare, list(gate_ids)))}
        check("gate stays silent when coverage is None",
              "RESEARCH_COVERAGE_LOW" not in bare_fired, str(sorted(bare_fired)))

        # -- deep pass: the grid gets filled in -------------------------------
        print("\nR1/R5 -- deep pass clears the floor")
        full_findings = {i: {f: i + "-" + f + "-value" for f in FIELDS} for i in ITEMS}
        full_findings["milvus"]["ops_burden"] = "[uncertain]"
        deep = build_summary(project, full_findings, ["pgvector:hybrid_search"])
        check("deep pass coverage is 100%", abs(deep.coverage - 1.0) < 1e-9,
              str(deep.coverage))
        deep_ok, deep_msg = ro.check_floor(deep)
        check("floor met at full coverage", deep_ok is True, deep_msg)
        check("uncertain cells still count toward coverage (completeness != confidence)",
              abs(deep.coverage - 1.0) < 1e-9)

        # -- R3: unconfident values are withheld from the report --------------
        print("\nR3 -- unconfident values withheld from the rendered report")
        check("[uncertain] marker detected",
              ro.is_uncertain(deep, "milvus", "ops_burden") is True)
        check("uncertain list entry detected",
              ro.is_uncertain(deep, "pgvector", "hybrid_search") is True)
        check("a confident cell is not flagged",
              ro.is_uncertain(deep, "qdrant", "license") is False)

        rendered = ro.format_summary(deep)
        check("report keeps a confident value", "qdrant-license-value" in rendered)
        check("report withholds the [uncertain] value",
              "milvus-ops_burden-value" not in rendered)
        check("report withholds the listed-uncertain value",
              "pgvector-hybrid_search-value" not in rendered)

        # -- R1: domain-aware floor still applies without an outline ----------
        print("\nR1 -- domain classification still drives the outline-free floor")
        code_domain = ro.classify_domain("build a FastAPI service with JWT auth")
        non_code = ro.classify_domain(
            "compare hiring policy and onboarding process for a design studio")
        check("code vision classified as code", code_domain == "code", code_domain)
        check("non-code vision classified as non_code", non_code == "non_code", non_code)
        # Documented behaviour, not an accident: with no signal either way the
        # classifier resolves to `code`, because under-applying the code floor
        # is the more expensive mistake.
        check("a signal-free vision ties to code",
              ro.classify_domain("compare options in Tel Aviv") == "code")
        outline_free = ro.ResearchSummary(vision="build a FastAPI service with JWT auth")
        ok, msg = ro.check_floor(outline_free)
        check("empty outline-free summary does not meet the floor", ok is False, msg)

        # -- R6: the advisor names the flow -----------------------------------
        print("\nR6 -- advisor names the outline -> deep -> report flow")
        from genesis_architect_pro import mcp_advisor
        source = Path(mcp_advisor.__file__).read_text(encoding="utf-8").lower()
        for term in ("outline", "deep", "report"):
            check("advisor names the '" + term + "' stage", term in source)

    print("\n" + "-" * 62)
    if FAILURES:
        print("R1-R6 E2E: " + str(len(FAILURES)) + " of " + str(STEPS) + " checks FAILED")
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("R1-R6 E2E: all " + str(STEPS) + " checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
