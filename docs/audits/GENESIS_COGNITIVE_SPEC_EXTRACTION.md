# Genesis Cognitive Specification - Extraction Phase

**Scope:** READ-ONLY extraction. No `CLAUDE.md`, `AGENTS.md` or `GEMINI.md` created. No hooks, permissions, or configuration modified. No implementation.
**Sources read (content, not filenames):** `~/.claude/CLAUDE.md`, `SKILL.md` (468 lines), `references/` (6 files, 1,846 lines), `research_sources.json`, `gde_types.py`, `gde_gate_engine.py`, `gde_planner.py`, `genesis_memory`, `committee/pipeline.py`, `red_team_critic.py`, `mcp_advisor.py`, `drift_detector.py`, `scaffold_generator.py`, `~/.claude/settings.json`, `~/.claude/hooks/`, `~/.claude/agents/`.
**Method:** every item below is a *principle extracted from* a mechanism, never the mechanism itself.

---

## 1. Canonical Cognitive Specification

Extracted principles. Each is stated provider-neutrally, with the mechanism it was extracted from cited as evidence.

### P-01 Epistemic status is mandatory and ternary
Every sentence asserting fact carries exactly one of: `(user)` - stated this session; `(verified: source)` - established this session from a named artifact; `[assumed: X - if wrong: Y]` - a default, tagged, with blast radius inline. There is no fourth status. An untagged factual claim is a defect of the same class as a dead citation.
**Extracted from:** `SKILL.md:72-86`. **Corollary:** *training data is never a valid source*; only a this-session artifact counts as verified. Versions come from a lockfile, registry API or live check - never memory.

### P-02 A default is a disclosed decision; a guess presented as fact is a defect
When torn between asserting something unverified and spending a question, tag `[assumed]` with a basis. Neither invent nor interrogate.
**Extracted from:** `SKILL.md:167` (four-topics table).

### P-03 Every unasked decision is ledgered with blast radius
Each default adopted without asking gets a row: assumption, basis, blast radius if wrong, where it is checked. Absence must be *asserted* ("None - every decision is sourced"), never implied by an empty section.
**Extracted from:** `SKILL.md:436-443` (Assumptions Ledger). **Note:** this is the document-level form of the "absent is not zero" rule already enforced in code.

### P-04 Retrieval precedes interrogation
A fact that an environment probe or an ecosystem scan can settle is a lookup, not a question.
**Extracted from:** `SKILL.md:150` ("Look before asking").

### P-05 A question that does not fork the outcome must not be asked
Necessity test: name the two architectures the answer forks between. Same outcome either way ⇒ decide, tag `[assumed]`, proceed.
**Extracted from:** `SKILL.md:149`.

### P-06 Interrogation is budgeted and the budget is visible
One question per turn, last in the message, exactly one question mark. Every question ships a `Recommended:` line acceptable in one word. Running cost is displayed; a hard cap exists.
**Extracted from:** `SKILL.md:145-148`. **Portable form:** the numbers (8 cap, 3-5 target) are Genesis-tunable parameters, not universal constants.

### P-07 Evidence has a quantitative floor and the floor is a hard gate
Insufficient evidence halts the pipeline and surfaces explicit options; it never proceeds silently. An override is a recorded acknowledgment, never a silent bypass.
**Extracted from:** `SKILL.md:190-196` (research floor; `--override` re-records).

### P-08 Sources are stratified by credibility, numerically
11 tiers with explicit priority: `official`(100), `local`(99), `security`(98), `source`(97), `qa`(90), `packages`(88), `field`(85), `blog`(82), `research`(80), `learning`(76), `market`(40).
**Extracted from:** `research_sources.json`. **Already data, already portable.**

### P-09 Phase transitions require validation of the prior phase's output
"Phase 2 outputs must pass citation validation before Phase 3 begins."
**Extracted from:** `SKILL.md:212`.

### P-10 Completeness is machine-checked, not judged
Evidence-pack and mitigation checks exit non-zero and block progress.
**Extracted from:** `SKILL.md:337` (`require-evidence-pack`, exits non-zero), `SKILL.md:386` (`validate`, "Exit 1 blocks git commit").

### P-11 Approval requirement scales with reversibility
Non-destructive acts proceed unannounced. Irreversible or outward-facing acts require per-action approval and are never auto-run.
**Extracted from:** `SKILL.md:341` ("Non-destructive - no approval needed") vs `SKILL.md:391` ("ask before each: git init… never auto-run").

### P-12 Capability expansion is adjudicated before implementation
Before adding any source, adapter, MCP, API, dependency or output file: produce a value/cost/risk/decision table and obtain approval. Prefer lightweight adapters over heavy integrations; prefer selection and ranking over scanning everything; prefer stubs for low-priority items; reject noisy, unstable, redundant or token-expensive additions.
**Extracted from:** `SKILL.md:449-459`. **This is the single most portable governance policy in the system.**

### P-13 Failure modes are pre-enumerated with predetermined actions
Every anticipated failure has a table row and an action. Tool unavailability degrades to a named fallback and is reported.
**Extracted from:** `SKILL.md:198-208`.

### P-14 Degradation is explicit, quantified, and never silent
A component that could not do its job reports `degraded`, a reason, and a confidence value. It does not return zero.
**Extracted from:** `gde_types.EngineResult`; observed at runtime: `git_analyzer degraded 50% - no git history found`.

### P-15 A metric that was not measured is `None`, never `0`
**Extracted from:** `ARCHITECTURE_INVARIANTS.json` invariants list.

### P-16 Absence of precedent triggers a declared mode change
Zero comparable prior art ⇒ announce the switch and name the substituted basis (first principles).
**Extracted from:** `SKILL.md:445-447` (Architect Mode).

### P-17 Findings carry their basis
Every finding ships `basis`, `confidence`, affected scope, and a concrete suggested fix.
**Extracted from:** observed `recover` output - `basis: "cycle_length=2, deterministic graph cycle"`.

### P-18 Decisions are journalled or they did not happen
"A decision with no entry here is treated as not made."
**Extracted from:** `MEMORY_FILES['decision_log.md']`.

### P-19 Memory is scoped by purpose, not by recency
Six separated scopes: project state, decision journal, research history, architecture decisions (drift baseline), known risks, lessons learned.
**Extracted from:** `MEMORY_FILES`.

### P-20 Deliverables are environment-neutral
Machine-specific values (paths, usernames, home directories) appear as placeholders. Literal measured paths never enter committed artifacts.
**Extracted from:** `SKILL.md:430-431` (Privacy). **This is a security policy, provider-neutral.**

### P-21 Secrets are structurally excluded, not merely avoided
Never commit `.env`; always commit `.env.example`.
**Extracted from:** `SKILL.md:392`.

### P-22 Adversarial review is a required phase, not an optional pass
**Extracted from:** `red_team_critic.py`, `RED_TEAM_CRITICAL` gate. **Caveat:** currently degrades to deterministic-only without `ANTHROPIC_API_KEY`.

### P-23 Output format is contractual
Respond in the user's detected language; code, filenames and comments in English; tables over paragraphs; no em dashes.
**Extracted from:** `SKILL.md:462-468`.

### P-24 Enforcement decisions derive from evidence, not from a summary field
*(Anti-principle - currently violated.)* `commit()` trusts `gate_report.overall`, a stored field defaulting to `PASS`, rather than deriving from `hard_blocks`. Proven bypassable.
**Extracted from:** `decision_engine.py:230` + `gde_session.py:112-120`.

---

## 2-6. Classification inventory

| Item (extracted policy) | Current Location | Genesis-native? | Claude-specific? | Codex-compatible? | Gemini-compatible? | Enforcement Possible? | Evidence |
|---|---|---|---|---|---|---|---|
| P-01 Ternary epistemic status | `SKILL.md:72-86` | ✅ Yes | ❌ container only | ✅ | ✅ | ⚠️ Partial - lint for untagged claims | Prose, provider-neutral wording |
| P-02 Default ≠ guess | `SKILL.md:167` | ✅ | ❌ | ✅ | ✅ | ❌ Judgment | Prose |
| P-03 Assumptions Ledger | `SKILL.md:436-443` | ✅ | ❌ | ✅ | ✅ | ✅ Schema-checkable | Table schema defined |
| P-04 Retrieval before questions | `SKILL.md:150` | ✅ | ❌ | ✅ | ✅ | ❌ | Prose |
| P-05 Necessity test | `SKILL.md:149` | ✅ | ❌ | ✅ | ✅ | ❌ | Prose |
| P-06 Question budget | `SKILL.md:145-148` | ✅ | ❌ | ✅ | ✅ | ✅ Countable | Explicit cap |
| P-07 Evidence floor + logged override | `SKILL.md:190-196` | ✅ | ❌ | ✅ | ✅ | ✅ **Already exit-code** | `genesis_state.py write-phase2` |
| P-08 11-tier source ranking | `research_sources.json` | ✅ **Data** | ❌ | ✅ | ✅ | ✅ | JSON, priority ints |
| P-09 Phase-transition validation | `SKILL.md:212` | ✅ | ❌ | ✅ | ✅ | ✅ | Citation validation |
| P-10 Machine-checked completeness | `SKILL.md:337,386` | ✅ | ❌ | ✅ | ✅ | ✅ **Exit 1 blocks commit** | Non-zero exit |
| P-11 Approval ∝ reversibility | `SKILL.md:341,391` | ✅ | ⚠️ Claude has richer UI | ✅ | ✅ | ✅ via gates | Contrasting rules |
| P-12 Committee adjudication | `SKILL.md:449-459` | ✅ | ❌ | ✅ | ✅ | ✅ Table required | Governance policy |
| P-13 Pre-enumerated failure table | `SKILL.md:198-208` | ✅ | ❌ | ✅ | ✅ | ⚠️ | Explicit matrix |
| P-14 Explicit degradation | `gde_types.EngineResult` | ✅ **Code** | ❌ | ✅ | ✅ | ✅ | Runtime-observed |
| P-15 Absent ≠ zero | `ARCHITECTURE_INVARIANTS.json` | ✅ **Code** | ❌ | ✅ | ✅ | ✅ | Invariant list |
| P-16 Architect Mode fallback | `SKILL.md:445-447` | ✅ | ❌ | ✅ | ✅ | ⚠️ | Prose |
| P-17 Findings carry basis | `antipattern_detector` | ✅ **Code** | ❌ | ✅ | ✅ | ✅ | Runtime-observed |
| P-18 Journal or it didn't happen | `MEMORY_FILES` | ✅ **Code** | ❌ | ✅ | ✅ | ✅ | File template text |
| P-19 Purpose-scoped memory | `MEMORY_FILES` | ✅ **Code** | ❌ | ✅ | ✅ | ✅ | 6 files |
| P-20 Environment-neutral output | `SKILL.md:430-431` | ✅ | ❌ | ✅ | ✅ | ✅ Path regex | Privacy rule |
| P-21 `.env` never committed | `SKILL.md:392` | ✅ | ❌ | ✅ | ✅ | ✅ pre-commit | Explicit |
| P-22 Mandatory adversarial pass | `red_team_critic.py` | ⚠️ Policy yes, impl no | ✅ **LLM path** | ❌ | ❌ | ✅ Gate exists | `anthropic.Anthropic()` hardcoded |
| P-23 Output contract | `SKILL.md:462-468` | ✅ | ❌ | ✅ | ✅ | ✅ Linted in CI today | Em-dash gate in `ci.yml` |
| **Spec delivery mechanism** | `SKILL.md` frontmatter | ❌ | ✅ **Yes** | ❌ | ❌ | N/A | Anthropic Agent Skills format |
| **Session-start injection** | `CLAUDE.md` tree-walk | ❌ | ✅ **Yes** | ❌ | ❌ | N/A | Verified: parent-dir file loaded |
| **Tool-call gating** | `PreToolUse` hooks | ❌ | ✅ **Yes** | ❌ | ❌ | ✅ Claude only | `settings.json` hooks |
| **Permission allow/deny** | `settings.json` | ❌ | ✅ **Yes** | ❌ | ❌ | ✅ Claude only | 670 allow / 4 deny |
| **MCP discovery** | `mcp_advisor.py:499` | ⚠️ Genesis code, Claude-bound | ✅ | ❌ | ❌ | N/A | Reads only `~/.claude.json` |
| **Subagent dispatch** | `~/.claude/agents/` | ❌ | ✅ **Yes** | ❌ | ❌ | N/A | 23 `.md` definitions |
| **Skill autoload** | `~/.claude/skills/` | ❌ | ✅ **Yes** | ❌ | ❌ | N/A | 103 dirs, 70 auto-load |
| **Committee LLM debate** | `pipeline.py:60-75` | ⚠️ Policy yes | ✅ **Impl** | ❌ | ❌ | N/A | Hardcoded model + key |
| **Git pre-commit emission** | `scaffold_generator.py:86` | ✅ | ❌ | ✅ | ✅ | ✅ **Cross-provider** | `.pre-commit-config.yaml` |

**Summary:** of 24 extracted principles, **21 are Genesis-native and provider-neutral in content**. Only P-22 has a Claude-bound *implementation*. Everything in the lower block is a *mechanism*, not a policy.

---

## 7. Missing capabilities

| Missing | Requested section | Status |
|---|---|---|
| Context-retrieval as a pipeline stage | §1 stage 3 | Memory + KG exist as engines; no stage retrieves before planning |
| Constraint detection **before** execution | §1 stage 4 | `gate` follows `execute`; only gate *declaration* happens at plan time |
| Correction loop | §1 stage 10 | `rollback` is a state; no re-attempt found |
| "Do I need a tool at all?" test | §4 | No mechanism decides against tool use |
| Post-tool-call relevance/contradiction evaluation | §4 | UNKNOWN - not found in `src/` |
| Permanent user-preferences memory scope | §8 | Not among the 6 `MEMORY_FILES` |
| Generated-artifacts registry | §8 | Absent |
| System-configuration memory scope | §8 | Absent |
| Provider identity in any state object | §12 | `DecisionEntry.actor` = `gde｜user｜engine_id` only |
| Compiler: one spec → N containers | §13 | **0 hits** for `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` in `src/` |
| Drift detection for configuration/docs | §14 | `drift_detector` covers architecture only, and is advisory by design |
| Contradiction detection across context | §3 | UNKNOWN |

---

## 8. Conflicting / duplicated rules

| Conflict | Evidence | Risk |
|---|---|---|
| Global `CLAUDE.md` misstates skill counts | Claims "18 skills auto-load; ~42 STANDBY"; measured **70 auto-load / 33 STANDBY** of 103 | Agents inherit false environment facts |
| Global `CLAUDE.md` misstates licensing | Claims "Genesis Pro (paid, v5.4.1) is active"; no paid tier since v8.0.0, current v9.0.0 | Same |
| Two response-mode systems | Global `CLAUDE.md` "Compact / Full reasoning"; `SKILL.md` Format Rules | Overlapping, non-identical output contracts |
| Two source-priority systems | Global `CLAUDE.md` RULE 1-6 tool routing; `research_sources.json` 11 tiers | Different vocabularies for the same decision |
| Em-dash rule stated twice | Global `CLAUDE.md` + `SKILL.md:463` + enforced in `ci.yml` | Triple statement, single enforcement |
| Agent definitions duplicated | 18 byte-identical files in `~/.claude/agents` and `~/.cursor/agents`; 5 missing from the copy | Coverage drift, no sync |
| `memory` MCP defined twice | Global `mcpServers` + `C:/Users/User` project scope | Precedence UNKNOWN |
| `.claude.json` case collisions | 6 of 23 project keys differ only by drive-letter case | Split trust/history per launch capitalisation |

---

## 9. Drift risks

| Risk | Mechanism absent | Already materialised? |
|---|---|---|
| Instruction claims vs measured reality | No shipped verifier | ✅ **Yes** - two false claims in global `CLAUDE.md` |
| Spec vs compiled artifacts | No compiler, so no staleness concept | N/A yet |
| Provider silently without policy | No provider enumeration | ✅ **Yes** - Gemini and Codex have zero |
| Cognitive spec vs engine version | `SKILL.md` and `references/` excluded from wheel | ✅ **Yes** - `pip install` ships engine without OS |
| Duplicated agent definitions | No sync | ✅ **Yes** - 5 agents behind |
| Config collisions | No hygiene engine | ✅ **Yes** - 6 collisions |
| Gate state vs gate evidence | `overall` stored, not derived | ✅ **Yes** - bypass proven |

---

## 10. Recommended canonical source structure (structure only)

```
genesis-cognitive-os/                  ← single source of truth
├── spec/
│   ├── 00-identity.md                 role, authority, escalation
│   ├── 01-lifecycle.md                stages + ordering invariants
│   ├── 02-epistemics.md               P-01..P-03  ← lift from SKILL.md:72-86
│   ├── 03-intent.md                   P-04..P-06
│   ├── 04-tool-policy.md              need-test, selection, post-eval  [NEW]
│   ├── 05-research.md                 P-07..P-09  ← research_sources.json
│   ├── 06-verification.md             P-10, P-17
│   ├── 07-self-critique.md            P-22
│   ├── 08-error-recovery.md           P-13..P-16
│   ├── 09-memory.md                   P-18, P-19 + 3 missing scopes
│   ├── 10-governance.md               P-11, P-12
│   ├── 11-security.md                 P-20, P-21
│   ├── 12-output.md                   P-23
│   └── 13-observability.md            provider identity  [NEW]
│
├── adapters/                          how each provider receives the spec
│   ├── claude/     → CLAUDE.md + SKILL.md frontmatter + hooks + permissions
│   ├── codex/      → AGENTS.md
│   ├── gemini/     → GEMINI.md
│   └── _generic/   → git pre-commit  (the only cross-provider enforcement)
│
├── enforcement/                       policies expressible as exit codes
│   └── (P-07, P-10, P-20, P-21, P-23 are already exit-code shaped)
│
└── verify/
    ├── artifacts-current-vs-spec
    ├── provider-has-policy
    └── claims-vs-measured-reality     ← would have caught both CLAUDE.md errors
```

**Packaging requirement (evidence-based):** the spec must ship inside the wheel. Today `SKILL.md in package: False` and `references/ in package: False`, so the cognitive OS does not travel with the engine.

---

## Answer to the standing question

**Genesis is a Claude OS with a large number of genuine Agent OS components** - and the extraction sharpens why.

Of 24 principles extracted, **21 are already provider-neutral in their wording and 8 are already implemented in provider-neutral Python or data**. The specification is not missing. It is 2,314 lines of coherent cognitive policy sitting in `SKILL.md` and `references/`, written in language that names no provider.

What is missing is three things, none of which is a brain:

1. A **canonical source** those 21 principles live in, rather than a Claude skill file.
2. A **compiler** that emits the three container formats from it.
3. An **enforcement path** that is not a Claude Code feature - noting that five principles (P-07, P-10, P-20, P-21, P-23) are *already* exit-code shaped and one, `.pre-commit-config.yaml`, already binds every provider.

Gemini and Codex are not running a degraded Genesis. They are running no Genesis at all - not because the policy does not exist, but because the only delivery channel is a container neither of them can open.

---

### UNKNOWN (not guessed)

Post-tool-call relevance evaluation; contradiction detection across context sources; precedence between the two `memory` MCP definitions; whether the research floor is hard or soft at CLI runtime; Gemini CLI `GEMINI.md` precedence semantics (no file exists to test); whether Claude `PreToolUse` hooks can be bypassed.
