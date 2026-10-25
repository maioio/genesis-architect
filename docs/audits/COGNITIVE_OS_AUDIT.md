# Genesis as a Cognitive Operating System - Read-Only Audit

**Target:** `maioio/genesis-architect` @ `8e8d5a4` (v9.0.0) + local agent environment
**Date:** 2026-08-23
**Constraint:** READ-ONLY. No file created except this report. No `GEMINI.md`, no `AGENTS.md`, no changes to `CLAUDE.md`, hooks, or permissions.
**Unverifiable items are marked UNKNOWN. Nothing is guessed.**

---

## 1. Cognitive Architecture Audit

The requested behavioural model mapped against the pipeline Genesis actually implements (`LifecycleStage`, verified by enum inspection).

**Genesis actual pipeline:** `idle → intake → plan → execute → gate → report → approve → commit`
**Non-linear states:** `degraded`, `blocked`, `suspended`, `rollback`

| # | Requested stage | Genesis stage | Status | Evidence |
|---|---|---|---|---|
| 1 | INPUT | `intake` | ✅ Exists | `LifecycleStage.intake` |
| 2 | Intent Understanding | `intake` → `classify()` | ✅ **Strong** | `intent_classifier.py` - deterministic regex scoring, zero LLM refs, 17 adversarial inputs × 50 runs, zero variance |
| 3 | Context Retrieval | — | ⚠️ **Partial, not a stage** | 6 scoped memory files exist (`MEMORY_FILES`) and `knowledge_graph` runs as an engine, but no pipeline stage retrieves context *before* planning |
| 4 | Constraint Detection | `gate` | 🔴 **Wrong position** | `gate` runs **after** `execute`. `build_plan()` declares *required gates* at plan time (`gde_planner.py:44-52`) but evaluation is post-execution. Constraints are verified after work is done, not before |
| 5 | Task Decomposition | `plan` | ✅ Exists | `build_plan()` → `ExecutionPlan` with topologically-sorted parallel phases |
| 6 | Tool / Source Selection | `plan` (engines only) | ⚠️ **Partial** | Engine selection is deterministic via DAG. Research source selection is tiered (11 tiers, priority 100→40). **No mechanism decides whether a tool is needed at all** |
| 7 | Execution | `execute` | ✅ Exists | `run_plan()` |
| 8 | Verification | `gate` | ✅ Exists | 14-gate policy table, 2 hard / 7 soft / 5 warn |
| 9 | Self-Critique | `red_team_critic` (engine) | ⚠️ **Engine, not stage** | Runs as one engine inside `execute`, not as a pipeline phase. LLM pass is Anthropic-locked |
| 10 | Correction | `rollback` (state) | 🔴 **State, not stage** | `LifecycleStage.rollback` exists but no automatic correction loop was found. `CommitResult.rolled_back` records ops, does not re-attempt |
| 11 | Final Output | `report` | ✅ Exists | `SessionReport`, `render_report` |
| 12 | Approval / Commit | `approve` → `commit` | ✅ **Beyond spec** | Two stages the requested model does not include |

### Cognitive policy layers already specified

| Requested section | Where it exists today | Portability |
|---|---|---|
| §2 Context / fact-vs-assumption | **Evidence Discipline**, `SKILL.md:72-86` - three statuses `(user)` / `(verified: source)` / `[assumed: X - if wrong: Y]`; *"Training data is never a valid source"*; mandatory provenance scan before Phase 6 | **Provider-neutral prose**, Claude-only container |
| §3 Reasoning discipline | `SKILL.md` question contract, landmine sweep, Assumptions Ledger; `references/dry-run-interview.md` | Same |
| §5 Research quality | `research_sources.json` - 11 tiers with explicit priority: `official`(100), `local`(99), `security`(98), `source`(97), `qa`(90), `packages`(88), `field`(85), `blog`(82), `research`(80), `learning`(76), `market`(40) | **Genesis-native, data-driven, portable** |
| §6 Self-verification | Research floor (hard gate), evidence gate (Step 0), MVP validation, smoke test | Encoded as workflow steps in `SKILL.md` |
| §7 Error handling | `degraded` status + explicit reason + confidence per engine | **Genesis-native, in code** |
| §8 Memory | 6 files: `project_memory`, `decision_log`, `research_history`, `architecture_decisions`, `known_risks`, `lessons_learned`. *"A decision with no entry here is treated as not made"* | **Genesis-native, portable** |

**Memory gaps against §8:** no *permanent user preferences* file, no *generated artifacts* registry, no *system configuration* scope. Temporary task context lives in session state, separate from `MEMORY_FILES`.

---

## 2. Provider Parity Matrix

| Cognitive policy | Claude Code | Codex | Gemini CLI | Mechanism today |
|---|---|---|---|---|
| Receives Genesis cognitive spec | ✅ via skill loader | ❌ | ❌ | `SKILL.md` frontmatter is Anthropic Agent Skills format |
| Evidence Discipline (3-status tagging) | ✅ | ❌ | ❌ | Prose inside `SKILL.md` |
| Intent routing | ✅ | ✅ | ✅ | `genesis decide` CLI - any shell can call it |
| Deterministic analysis | ✅ | ✅ | ✅ | CLI, no LLM required |
| Research tiering | ✅ | ✅ | ✅ | JSON data file, engine-side |
| Memory scoping | ✅ | ✅ | ✅ | `.genesis/*.md`, filesystem-based |
| Committee debate | ✅ | ❌ | ❌ | `anthropic.Anthropic()` hardcoded |
| Red-team LLM critique | ✅ | ❌ | ❌ | `anthropic.Anthropic()` hardcoded |
| Gate enforcement on agent writes | ⚠️ Genesis writes only | ❌ | ❌ | In-process `commit()` check |
| Tool-call interception | ⚠️ Claude hooks (not Genesis) | ❌ | ❌ | `PreToolUse` is a Claude Code feature |
| Standing instructions at session start | ✅ | ❌ | ❌ | `CLAUDE.md` tree-walk |
| Config format | `settings.json` + `CLAUDE.md` + skills | `config.toml` (trust flags only) | `settings.json` (auth only) | Three incompatible schemas |

**Adapter reality:** COMMON POLICY exists (Evidence Discipline, research tiers, memory scoping, deterministic engines). PROVIDER ADAPTER does not exist for any provider. PROVIDER-SPECIFIC LIMITATION: Codex reads only `AGENTS.md`; Gemini reads only `GEMINI.md` (**0 exist machine-wide**); neither has a skill loader, a hook system, or a permission engine.

---

## 3. Current Genesis Capabilities (provider-independent, verified by execution)

| Capability | Evidence |
|---|---|
| Deterministic intent routing | Zero LLM refs in `intent_classifier.py`; 850 runs, zero variance; prompt injection did not alter routing |
| Structural analysis offline | `decide` completed with **no** `ANTHROPIC_API_KEY`; `import_graph` 100% confidence |
| Explicit degradation | `git_analyzer degraded 50% - no git history found`; engines report reason + confidence, never silent zero |
| Evidence-bearing findings | Every anti-pattern carries `basis`, `confidence`, `suggested_fix`, `affected_modules` |
| Research source stratification | 11 tiers × 30 sources with numeric priority |
| Scoped auditable memory | 6 purpose-separated files; decision-journal discipline |
| Cross-provider enforcement primitive | `scaffold_generator.py:86-123` emits `.pre-commit-config.yaml` - git-level, binds any agent |
| Decision log | `DecisionEntry`: stage, `decision_type` (`GATE_FIRED`/`ENGINE_INVOKED`/`ENGINE_FAILED`), actor, confidence before/after, outcome |
| Provider-neutral inference | `core/llm.py` → litellm → Anthropic/OpenAI/Google/Ollama by model string |

---

## 4. Claude-only Capabilities

| Capability | Why it is Claude-only | Evidence |
|---|---|---|
| Delivery of the cognitive spec | `SKILL.md` is the Anthropic Agent Skills container; comment states *"Claude Code only reads `name` and `description`"* | `SKILL.md:1-17` |
| Committee (5-advisor debate) | Bypasses `llm.py`; `anthropic.Anthropic()`; `model="claude-sonnet-4-6"`; requires `ANTHROPIC_API_KEY` | `engines/committee/pipeline.py:60-75` |
| Red-team LLM pass | Identical pattern | `red_team_critic.py:172-190` |
| MCP discovery | Reads **only** `Path.home()/".claude.json"` | `mcp_advisor.py:499` |
| Session-start instruction injection | `CLAUDE.md` upward tree-walk is a Claude Code feature | Verified: cwd had no `CLAUDE.md`; `C:\Users\User\CLAUDE.md` loaded |
| Tool-call gating | `PreToolUse` hooks belong to Claude Code, not Genesis | Genesis writes no hooks: no `hooksPath`/`PreToolUse` in `src/` |

> **Critical:** the cognitive spec is not merely Claude-formatted, it is **not shipped at all**. Wheel inspection: `SKILL.md in package: False`, `references/ in package: False`. `pip install genesis-architect` delivers the engines without the operating system. All 2,314 lines of cognitive policy (468 `SKILL.md` + 1,846 `references/`) reach an agent only through the Claude Code skills directory.

---

## 5. Missing Gemini Capabilities

| Missing | Evidence | Severity |
|---|---|---|
| Any standing instruction whatsoever | **0 `GEMINI.md` found machine-wide**; `~/.gemini/settings.json` contains only `security.auth.selectedType` and session retention | 🔴 Total |
| Evidence Discipline | Not delivered - no container | 🔴 |
| Memory continuity | No mechanism reads `.genesis/*.md` on Gemini start | 🟠 |
| MCP servers | None configured for Gemini | 🟠 |
| Committee / red-team participation | Anthropic-hardcoded | 🟡 |
| Extensions / commands | `~/.gemini/extensions` and `~/.gemini/commands` absent | 🟡 |

Gemini CLI v0.47.0 **is installed and functional**. Your global `CLAUDE.md` states *"Gemini is used for large repository analysis"* - it receives zero policy. Every invocation starts from nothing.

---

## 6. Missing Codex Capabilities

| Missing | Evidence | Severity |
|---|---|---|
| User-level instructions | No `~/.codex/AGENTS.md`; no `~/AGENTS.md` | 🔴 Total |
| Evidence Discipline | Not delivered | 🔴 |
| Genesis workflow phases | Not delivered | 🔴 |
| Config beyond trust | `~/.codex/config.toml` contains **only** `[projects.*] trust_level = "trusted"` × 10 | 🟠 |
| Memory continuity | Same gap as Gemini | 🟠 |

Codex is invoked *from* Claude Code (`codexIntegration` key in `settings.json`), so it inherits scope from the calling prompt only - never a standing policy. The 9 `AGENTS.md` files on disk are project-local or vendored inside plugins/extensions; none is a Genesis artifact.

---

## 7. Enforcement vs Advisory Matrix

| Mechanism | Provider | Class | Bypassable | Scope |
|---|---|---|---|---|
| `commit()` HARD_BLOCK check | Genesis in-process | ENFORCEMENT | ✅ **Yes** - proven via session-file desync | Genesis writes only |
| Claude `PreToolUse` hook | Claude only | ENFORCEMENT | Unknown | Global |
| Claude `permissions.deny` | Claude only | ENFORCEMENT | 4 relative-path rules vs 670 allow | Global |
| `.pre-commit-config.yaml` | **All** | ENFORCEMENT | Yes (`--no-verify`) | Project, scaffold-time |
| Research floor gate | Genesis | ENFORCEMENT (workflow) | UNKNOWN | Session |
| Rules engine | Genesis | ADVISORY (fail-open) | N/A - absent policy ⇒ PASS | Project |
| Evidence Discipline | Claude only | **ADVISORY** | Trivially | Session |
| `SKILL.md` phases | Claude only | **ADVISORY** | Trivially | Session |
| `CLAUDE.md` tree-walk | Claude only | **ADVISORY** | Trivially | Global |
| `drift_detector` | Genesis | **ADVISORY** by design (*"All output is advisory"*) | N/A | Project |
| `hygiene_notice` | Genesis | **ADVISORY** (read-only) | N/A | Project |
| Secrets scan in `harden` | — | **NONE** (unwired) | N/A | — |

**Summary:** every cognitive policy currently in force is ADVISORY. The only ENFORCEMENT that reaches all three providers is the git pre-commit hook, and Genesis emits it at scaffold time only.

---

## 8. Proposed Canonical Cognitive Specification - OUTLINE ONLY

*Structure only, per the read-only constraint. No content authored, no files created.*

The canonical source **already exists at roughly 70% completeness** - it is `SKILL.md` + `references/`, trapped in a Claude-proprietary container and excluded from the wheel. The proposal is therefore extraction and compilation, not authorship.

```
COGNITIVE SPEC (single source of truth, provider-neutral)
├── 00-identity          role, authority, escalation
├── 01-behavioral-model  the 12 stages of §1, with the two ordering fixes
├── 02-context-model     6 context classes; UNKNOWN over invention
│                        ← lift verbatim from SKILL.md:72-86 Evidence Discipline
├── 03-reasoning         fact / inference / assumption; assumption confirmation
├── 04-tool-policy       need-a-tool test; selection; post-call evaluation
├── 05-research-policy   DISCOVER→COLLECT→CROSS-CHECK→VERIFY→SYNTHESIZE
│                        ← already data: research_sources.json, 11 tiers
├── 06-verification      pre-answer checklist; technical validation
├── 07-error-policy      DETECT→CLASSIFY→EXPLAIN→RECOVER→VERIFY
│                        ← partially in code: degraded + reason + confidence
├── 08-memory-model      6 existing scopes + 3 missing (preferences,
│                        artifacts, system config)
├── 09-intent-policy     outcome vs literal text; when to ask
├── 10-output-contract   format, length discipline, no unsupported claims
└── 11-adaptation        language, depth, verbosity by context

COMPILER (does not exist today)
   spec → CLAUDE.md        (tree-walk container)
   spec → SKILL.md         (Anthropic skill container, frontmatter)
   spec → AGENTS.md        (Codex container)
   spec → GEMINI.md        (Gemini container)
   spec → machine-readable policy for runtime enforcement

VERIFIER (does not exist today)
   detect: provider without instructions
   detect: compiled artifact stale vs spec
   detect: instruction claims vs measured reality
           (your CLAUDE.md: "18 skills auto-load" vs 70 measured)
```

**Container requirements observed, not assumed:** Claude reads `CLAUDE.md` (tree-walk, verified) and `SKILL.md` (frontmatter `name`+`description` only). Codex reads `AGENTS.md`. Gemini reads `GEMINI.md`. UNKNOWN: whether Gemini CLI v0.47.0 supports a user-level vs project-level `GEMINI.md` precedence order - not verifiable read-only, since no such file exists to test.

---

## 9. Top 10 Highest-Value Gaps

| # | Gap | Evidence | Why it ranks here |
|---|---|---|---|
| 1 | **No compiler from one spec to N providers** | 0 hits for `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` in `src/` | Upstream of every other gap |
| 2 | **Cognitive spec not shipped** | `SKILL.md in package: False`, `references/: False` | The OS does not travel with the engine |
| 3 | **Spec locked in Claude container** | Anthropic Agent Skills frontmatter | 2,314 lines unreachable by 2 of 3 providers |
| 4 | **Two judgment engines Anthropic-hardcoded** | `pipeline.py:60-75`, `red_team_critic.py:172-190` | Provider parity impossible while these bypass `llm.py` |
| 5 | **All cognitive policy is advisory** | §7 matrix - only pre-commit reaches all providers | An OS that cannot enforce is a style guide |
| 6 | **No provider identity in state** | `DecisionEntry.actor` = `gde｜user｜engine_id` | Cannot attribute or audit any decision to a model |
| 7 | **Constraint detection after execution** | `gate` follows `execute` | Work is done before constraints are verified |
| 8 | **No config-drift detection** | Repo-only `architecture_invariants.py`, not shipped | Your own `CLAUDE.md` is wrong on 2 counts, undetected |
| 9 | **No correction loop** | `rollback` is a state; no re-attempt found | Stages 10-11 of the requested model absent |
| 10 | **MCP advice Claude-blind** | `mcp_advisor.py:499` reads only `~/.claude.json` | Tool-layer parity invisible |

---

## Final verdict

**Genesis is a Claude OS with a large number of genuine Agent OS components.**

The Agent-OS half is real and was verified by execution, not inspection: deterministic routing that survived 850 adversarial runs with zero variance, a full analysis session completing with no API key, explicit degradation with per-engine reasons and confidence, 11-tier research stratification as data rather than prose, six scoped auditable memory files, and a fact-tagging discipline (`(user)` / `(verified:)` / `[assumed:]`) that is genuinely provider-neutral in its wording.

The Claude-OS half is equally demonstrable: the entire cognitive specification is delivered through the Anthropic Agent Skills container and is absent from the installable artifact; both engines that exercise judgment bypass the provider-neutral `llm.py` to instantiate `anthropic.Anthropic()` with a hardcoded model; tool discovery reads only `~/.claude.json`; and no state object anywhere records which provider acted.

The decisive fact is this: **the cognitive specification already exists and is already provider-neutral in content - it is only provider-locked in packaging.** Genesis does not need a new brain. It needs its existing brain extracted from `SKILL.md` into a canonical source, a compiler that emits the three container formats, and at least one enforcement path that is not a Claude feature.

Until that compiler exists, Gemini and Codex are not running a degraded Genesis - they are running no Genesis at all.

---

### Coverage caveats

**UNKNOWN (not guessed):** Gemini CLI `GEMINI.md` precedence semantics (no file exists to test); whether Claude `PreToolUse` hooks can be bypassed; whether the research floor gate is hard or soft at runtime; the four MCP servers configured but not loaded; origin of `NVIDIA_API_KEY`/`POSTHOG_API_KEY`.

**Not done:** no file modified; no `GEMINI.md`/`AGENTS.md` created; `CLAUDE.md`, hooks and permissions untouched; no architecture implemented.
