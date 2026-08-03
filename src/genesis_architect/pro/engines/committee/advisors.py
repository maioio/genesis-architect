"""Committee engine — five advisor prompt templates.

Each advisor uses a structurally different reasoning method.
Based on Zhang et al. 2025 / Cambridge MAD 2026: homogeneous agents
amplify errors; distinct methods force genuine disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass

from genesis_architect.pro.engines.committee.types import CommitteeRequest


@dataclass(frozen=True)
class AdvisorTemplate:
    name: str
    method: str
    known_blind_spot: str
    system_prompt: str


_ADVISORS: list[AdvisorTemplate] = [
    AdvisorTemplate(
        name="The Contrarian",
        method="Inductive reasoning from failure cases",
        known_blind_spot="Pessimism bias; may over-weight tail risks",
        system_prompt=(
            "You reason inductively from failure cases. "
            "Your job is to find what has gone wrong in similar situations before — "
            "real incidents, regressions, architectural mistakes that look like this one. "
            "Do NOT validate the proposed approach. Look for the crack in it. "
            "If you find no credible failure mode, say so explicitly (do not manufacture risk). "
            "Output: a concise stance (1-3 sentences) and a confidence score 0.0-1.0."
        ),
    ),
    AdvisorTemplate(
        name="The First Principles Thinker",
        method="Deductive from base axioms — no analogies, no patterns",
        known_blind_spot="Misses domain-specific constraints",
        system_prompt=(
            "You reason purely from first principles. "
            "No analogies. No patterns. No 'this is like X'. "
            "Strip the question to its logical primitives and reason from there. "
            "State the axioms you are using. Challenge any assumption in the question itself. "
            "Output: a concise stance (1-3 sentences) and a confidence score 0.0-1.0."
        ),
    ),
    AdvisorTemplate(
        name="The Expansionist",
        method="Historical analogy and pattern matching across domains",
        known_blind_spot="May import inapplicable context from other fields",
        system_prompt=(
            "You reason by historical analogy across domains. "
            "How did civil engineering, biology, logistics, or other fields solve problems "
            "that are structurally similar to this one? "
            "Find the cross-domain pattern and apply it. Be explicit about what transfers "
            "and what does not. "
            "Output: a concise stance (1-3 sentences) and a confidence score 0.0-1.0."
        ),
    ),
    AdvisorTemplate(
        name="The Outsider",
        method="Statistical base rates and prior distributions only",
        known_blind_spot="Ignores project-specific signals",
        system_prompt=(
            "You use statistical base rates and prior distributions only. "
            "Ignore the specifics of this project entirely. "
            "What does the base rate say? How often do similar decisions go well? "
            "What is the prior probability of success given the class of problem? "
            "Do NOT be swayed by project-specific details — treat this as a draw from a distribution. "
            "Output: a concise stance (1-3 sentences) and a confidence score 0.0-1.0."
        ),
    ),
    AdvisorTemplate(
        name="The Executor",
        method="Causal chain backward from desired outcome",
        known_blind_spot="May rationalize a conclusion by selecting a convenient causal chain",
        system_prompt=(
            "You reason by working backward from the desired outcome. "
            "Start with the goal. What must be true for it to be achieved? "
            "What must be true for THAT to be true? Trace the causal chain back to the present state. "
            "Where does the chain break? What is the weakest link? "
            "Output: a concise stance (1-3 sentences) and a confidence score 0.0-1.0."
        ),
    ),
]

ADVISOR_NAMES: list[str] = [a.name for a in _ADVISORS]


def get_all_advisors() -> list[AdvisorTemplate]:
    return list(_ADVISORS)


def build_position_prompt(advisor: AdvisorTemplate, request: CommitteeRequest) -> str:
    context_block = ""
    if request.context.evidence:
        context_block += f"\n\nEVIDENCE:\n{request.context.evidence}"
    if request.context.engine_outputs:
        outputs = "\n".join(
            f"- {k}: {v}" for k, v in request.context.engine_outputs.items()
        )
        context_block += f"\n\nENGINE ANALYSIS:\n{outputs}"
    if request.context.prior_decisions:
        prior = "\n".join(f"- {d}" for d in request.context.prior_decisions)
        context_block += f"\n\nPRIOR DECISIONS:\n{prior}"

    return (
        f"{advisor.system_prompt}\n\n"
        f"QUESTION: {request.question}\n"
        f"MODE: {request.mode.value.upper()}{context_block}\n\n"
        "Respond in this exact format:\n"
        "STANCE: <your position in 1-3 sentences>\n"
        "CONFIDENCE: <0.0-1.0>\n"
        "WHAT_WOULD_CHANGE_IT: <what evidence or condition would shift your position>"
    )


def build_peer_review_prompt(
    reviewer: AdvisorTemplate,
    reviewer_position: str,
    other_positions: list[str],
) -> str:
    others_block = "\n\n".join(
        f"Position {i + 1}:\n{pos}" for i, pos in enumerate(other_positions)
    )
    return (
        f"{reviewer.system_prompt}\n\n"
        f"YOUR CURRENT POSITION:\n{reviewer_position}\n\n"
        f"OTHER ADVISORS' POSITIONS (anonymized):\n{others_block}\n\n"
        "After reading the other positions:\n"
        "1. Rate your agreement with the group consensus (0.0 = total disagreement, 1.0 = full agreement)\n"
        "2. Write a brief critique of the strongest opposing view\n"
        "3. State whether your stance has changed (and if so, how)\n\n"
        "Respond in this exact format:\n"
        "AGREEMENT: <0.0-1.0>\n"
        "CRITIQUE: <1-2 sentences on the strongest opposing view>\n"
        "REVISED_STANCE: <your updated position, or 'unchanged'>"
    )
