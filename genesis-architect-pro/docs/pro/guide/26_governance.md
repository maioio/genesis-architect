# Governance + Progressive Autonomy

**Pro.** Governance is the safety layer: it decides what Genesis may do on its
own, what needs your approval, and what is never done unattended.

## The autonomy ladder

| Level | Behavior |
|-------|----------|
| **Guided** | Genesis proposes; you approve each step. |
| **Assisted** | Routine steps proceed; consequential ones are gated. |
| **Trusted** | Most work proceeds; only high-stakes actions are gated. |
| **Autonomous** | Genesis runs the loop; **dangerous actions are still gated.** |

Autonomy is **earned gradually** — it is not a switch you flip on day one.

## The binding rule

> Dangerous actions **always** require approval — at every autonomy level,
> including Autonomous.

"Dangerous" includes deleting files, removing features, rewriting major
architecture, changing public APIs, and any destructive or hard-to-reverse
operation. The first build of a project is also a hard gate.

## Approval gates in the loop

The Decision Engine consults the approval gate before the consequential lifecycle
transitions (notably **EXECUTE** and **COMMIT**). A blocked gate stops the
lifecycle at that phase and records why. The actual prompt is delegated to the
host (Claude Code: a question; desktop: a dialog) — Governance decides *whether*
to ask, the host decides *how*.

## Why it matters

Progressive autonomy is what makes an AI partner safe to give real
responsibility: it can move fast on the routine and reversible, while the
irreversible always pauses for a human.
