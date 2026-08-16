"""Red-Team Self-Critique — attacks a session's own plan before it's approved.

Runs late in the pipeline (after every write-producing engine for the mode),
looking for logical vulnerabilities in what the session is about to propose:
conflicting writes, irreversible writes resting on low-confidence output, and
overall confidence that isn't backed by any successful engine evidence.

Deterministic checks always run (no LLM, no network — same philosophy as the
rest of the analysis engines: routing/scoring/detection is regex/graph/stats,
never a guess). An LLM adversarial pass is optional and additive, following
Committee's own pattern (engines/committee/pipeline.py): the callable is
injected so it's testable without a real API key, and the caller decides
whether to attempt it and how to disclose when it didn't run.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from genesis_architect_pro.gde_types import EngineStatus, SessionContext

# Overall-confidence claimed with zero successful engine evidence behind it is
# exactly the anti-pattern architecture_scorer's confidence floor was fixed
# for: a conclusion drawn from nothing is not a strong conclusion.
_UNFOUNDED_CONFIDENCE_THRESHOLD = 0.85
_LOW_CONFIDENCE_THRESHOLD = 0.5

RedTeamCallable = Callable[[str, str], str]


@dataclass
class RedTeamFinding:
    severity: str  # "critical" | "high" | "medium" | "low"
    category: str
    description: str
    evidence: str = ""


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------


def _check_conflicting_writes(ctx: SessionContext) -> list[RedTeamFinding]:
    """Two engines proposing writes to the same path is a silent last-write-wins bug."""
    by_path: dict[str, set[str]] = {}
    for op in ctx.pending_write_operations:
        by_path.setdefault(op.target_path, set()).add(op.engine_id)

    findings: list[RedTeamFinding] = []
    for path, engine_ids in by_path.items():
        if len(engine_ids) > 1:
            findings.append(RedTeamFinding(
                severity="critical",
                category="conflicting_writes",
                description=f"Multiple engines propose writing to the same path: {path!r}",
                evidence=f"engines={sorted(engine_ids)!r}",
            ))
    return findings


def _check_irreversible_low_confidence(ctx: SessionContext) -> list[RedTeamFinding]:
    """An irreversible write resting on a low-confidence (or failed) engine result."""
    findings: list[RedTeamFinding] = []
    for op in ctx.pending_write_operations:
        if op.is_reversible:
            continue
        result = ctx.engine_results.get(op.engine_id)
        if result is None:
            findings.append(RedTeamFinding(
                severity="critical",
                category="irreversible_no_evidence",
                description=(
                    f"Irreversible write {op.operation_id!r} proposed by "
                    f"{op.engine_id!r}, which has no recorded engine result"
                ),
                evidence=f"target_path={op.target_path!r}",
            ))
        elif result.status != EngineStatus.SUCCESS or result.confidence < _LOW_CONFIDENCE_THRESHOLD:
            findings.append(RedTeamFinding(
                severity="high",
                category="irreversible_low_confidence",
                description=(
                    f"Irreversible write {op.operation_id!r} rests on "
                    f"{op.engine_id!r} (status={result.status.value}, "
                    f"confidence={result.confidence:.2f})"
                ),
                evidence=f"target_path={op.target_path!r}",
            ))
    return findings


def _check_unfounded_confidence(ctx: SessionContext) -> list[RedTeamFinding]:
    """High claimed confidence with no successful engine backing it."""
    if ctx.overall_confidence < _UNFOUNDED_CONFIDENCE_THRESHOLD:
        return []
    successes = [r for r in ctx.engine_results.values() if r.status == EngineStatus.SUCCESS]
    if not ctx.engine_results or not successes:
        return [RedTeamFinding(
            severity="critical",
            category="unfounded_confidence",
            description=(
                f"overall_confidence={ctx.overall_confidence:.2f} claimed with "
                f"{len(successes)} successful engine result(s) out of "
                f"{len(ctx.engine_results)} run"
            ),
            evidence="Confidence in a conclusion drawn from no evidence is zero.",
        )]
    return []


def critique_session(ctx: SessionContext) -> list[RedTeamFinding]:
    """Run every deterministic check against the session's current state."""
    findings: list[RedTeamFinding] = []
    findings.extend(_check_conflicting_writes(ctx))
    findings.extend(_check_irreversible_low_confidence(ctx))
    findings.extend(_check_unfounded_confidence(ctx))
    return findings


# ---------------------------------------------------------------------------
# Optional LLM adversarial pass (mirrors engines/committee/pipeline.py)
# ---------------------------------------------------------------------------


def _default_llm_call(system: str, user: str) -> str:
    """Call Claude claude-sonnet-4-6 via the Anthropic SDK."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK not installed. Run: pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def _build_attack_prompt(ctx: SessionContext) -> tuple[str, str]:
    system = (
        "You are a red-team critic reviewing a software agent's execution plan "
        "before it is approved. Attack it: find logical vulnerabilities, missing "
        "dependencies, unfounded assumptions, and anything that could go wrong. "
        "Do not restate what looks fine — only report real vulnerabilities. If "
        "you find none, say so plainly."
    )
    writes = "\n".join(
        f"- {op.operation_id} ({op.engine_id}) -> {op.target_path} "
        f"[{'reversible' if op.is_reversible else 'IRREVERSIBLE'}]"
        for op in ctx.pending_write_operations
    ) or "(none pending)"
    results = "\n".join(
        f"- {eid}: status={r.status.value}, confidence={r.confidence:.2f}"
        for eid, r in ctx.engine_results.items()
    ) or "(no engine results)"
    user = (
        f"MODE: {ctx.mode.value}\n"
        f"OVERALL CONFIDENCE: {ctx.overall_confidence:.2f}\n\n"
        f"PENDING WRITES:\n{writes}\n\n"
        f"ENGINE RESULTS:\n{results}\n\n"
        "For each vulnerability found, respond with a block in exactly this "
        "format (repeat as needed):\n"
        "FINDING: <critical|high|medium|low>\n"
        "CATEGORY: <short category>\n"
        "DESCRIPTION: <what could go wrong, one or two sentences>\n"
        "---\n"
        "If there are no real vulnerabilities, respond with exactly: NONE"
    )
    return system, user


def _parse_llm_findings(raw: str) -> list[RedTeamFinding]:
    if raw.strip().upper() == "NONE":
        return []
    findings: list[RedTeamFinding] = []
    for block in raw.split("---"):
        severity_match = re.search(r"^FINDING:\s*(\w+)", block, re.MULTILINE)
        category_match = re.search(r"^CATEGORY:\s*(.+)$", block, re.MULTILINE)
        desc_match = re.search(r"^DESCRIPTION:\s*(.+)$", block, re.MULTILINE | re.DOTALL)
        if not severity_match or not desc_match:
            continue
        severity = severity_match.group(1).strip().lower()
        if severity not in ("critical", "high", "medium", "low"):
            severity = "medium"
        findings.append(RedTeamFinding(
            severity=severity,
            category=category_match.group(1).strip() if category_match else "llm_finding",
            description=desc_match.group(1).strip(),
        ))
    return findings


def critique_with_llm(
    ctx: SessionContext,
    llm_call: RedTeamCallable = _default_llm_call,
) -> list[RedTeamFinding]:
    """Run the adversarial LLM pass. Raises if the LLM backend is unavailable —
    callers decide how to disclose that (see gde_run_red_team_critic)."""
    system, user = _build_attack_prompt(ctx)
    raw = llm_call(system, user)
    return _parse_llm_findings(raw)


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------


def run_red_team(
    ctx: SessionContext,
    *,
    use_llm: bool = False,
    llm_call: RedTeamCallable = _default_llm_call,
) -> dict:
    """Run deterministic checks, optionally plus the LLM adversarial pass.

    Returns a dict with `findings` (list of dicts), `critical_count`, and
    `finding_count` — shaped for direct use as an EngineResult.output.
    """
    findings = critique_session(ctx)
    if use_llm:
        findings = findings + critique_with_llm(ctx, llm_call)

    critical = [f for f in findings if f.severity == "critical"]
    return {
        "findings": [
            {"severity": f.severity, "category": f.category,
             "description": f.description, "evidence": f.evidence}
            for f in findings
        ],
        "critical_count": len(critical),
        "finding_count": len(findings),
    }
