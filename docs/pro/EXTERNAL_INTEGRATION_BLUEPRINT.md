# External Integration Blueprint

**Sources read in full, not summarised from a file listing.** Both packs were
fetched with `genesis fetch` (whitelist-only, read-only) into an ephemeral
sandbox and their `SKILL.md` bodies read directly. Every pattern below is
quoted or paraphrased from source, and every claim about Genesis's own
structure comes from a dependency graph extracted from the code.

| Source | Verified |
|---|---|
| `45ck/software-architecture-skills` | MIT · 14 distinct skills in 3 packaged formats (42 files) |
| `Weizhena/Deep-Research-skills` | MIT · 5 distinct skills in 4 packaged formats (20 files) |

---

## Part 1 — Architectural integration

### 1.1 Boundary review (their procedure, our code)

`component-boundary-reviewer` prescribes: *"Separate facts, assumptions,
constraints... Make tradeoffs and uncertainty explicit."* Applied to the five
subsystems named in the brief, plus their transitive dependencies:

```
gde_types                    -> (none)
ephemeral_purge              -> (none)
learning_engine              -> (none)
engine_registry              -> gde_types
gde_gate_engine              -> gde_types
gde_runner                   -> gde_types
red_team_critic              -> gde_types
skill_fetcher                -> ephemeral_purge
mcp_advisor                  -> learning_engine
gde_planner                  -> engine_registry, gde_types
gde_engine_registration      -> engine_registry, gde_types
gde_engine_adapters          -> gde_types, red_team_critic
decision_engine              -> engine_registry, gde_gate_engine,
                                gde_planner, gde_runner, gde_types
```

**Cycle detection: NONE — acyclic.**

**Finding (evidence, not assumption): the boundaries are already clean.** The
graph is a strict 4-layer DAG:

- **L0 — pure kernel:** `gde_types`, `ephemeral_purge`, `learning_engine`
  depend on nothing internal. Two of the three newest subsystems (Auto-Purge,
  learning) sit here, which is why they were safe to build against.
- **L1 — single-dependency services:** each imports exactly one L0 module.
- **L2 — composition:** planner/registration/adapters.
- **L3 — orchestration:** `decision_engine` alone.

Engine adapters reach their engines through **function-level imports**, not
module-level ones, so the adapter layer never widens the import surface at
load time. That is the property keeping L2 from becoming a hub.

**Honest conclusion:** the brief asked for patterns "to ensure zero circular
dependencies as Genesis scales." There are zero today. The valuable adoption
from this pack is therefore **not a refactor** — it is a set of *declared
contracts* that keep the property true as the graph grows. Recommending a
restructure here would be exactly the failure mode their own skill warns
against: *"Do not recommend a style because it sounds modern."*

### 1.2 Patterns to adopt (exact, from source)

**Pattern A — the declared skill contract.** Every skill in the pack carries
the same frontmatter:

```yaml
name: "component-boundary-reviewer"
purpose: "..."
inputs:   ["architecture or code structure", "key modules/components", ...]
outputs:  ["boundary findings", "dependency issues", ...]
handoffs: ["runtime-view-writer", "deployment-view-writer", "adr-writer"]
```

Genesis's `EngineDescriptor` already has `input_keys`, `output_keys`, and
`requires` — the *backward* edge. It has no **`handoffs`**: the forward edge
saying what should run next. That is the one genuine gap.

**Pattern B — the minimum output skeleton.** Each skill declares a required
report shape:

```md
## Summary
## Findings or proposal
## Evidence vs assumptions
## Risks or tradeoffs
## Recommended next skill
```

`Evidence vs assumptions` as a *mandatory section* is stronger than what most
Genesis engines do today. `mcp_advisor` already enforces it structurally (no
recommendation without its triggering file); `recovery_report` and
`red_team_critic` state evidence but don't separate it from inference.

**Pattern C — declared failure modes per component.** Each skill lists what it
must not do. Genesis encodes this centrally in `_GATE_POLICY`, but individual
engines don't declare their own. Making it per-descriptor puts the constraint
next to the thing it constrains.

### 1.3 Concrete changes

| # | Module | Change | Effort |
|---|---|---|---|
| A1 | `gde_types.py` | Add `handoffs: list[str] = field(default_factory=list)` to `EngineDescriptor` | S |
| A2 | `gde_engine_registration.py` | Populate `handoffs` for all 18 descriptors (e.g. `recovery_report → refactoring_planner`) | M |
| A3 | `engine_registry.py` | Add `validate()` check: every `handoffs` id must exist (mirrors the existing `requires` check) — this is what keeps the DAG honest as it grows | S |
| A4 | `red_team_critic.py` | Split findings into `evidence` vs `inference` fields, per Pattern B | S |
| A5 | `gde_types.py` | Add `failure_modes: list[str]` to `EngineDescriptor`, surfaced in reports | S |

**A3 is the load-bearing one.** It is the mechanism that prevents the cycle
count from drifting from zero; A1/A2 without A3 are documentation.

---

## Part 2 — Research protocol integration

### 2.1 What the pack actually does (read from source)

Three phases, each a separate skill:

**Phase 1 — `research`: outline before investigation.**
1. Generate an initial framework *from model knowledge* — items list + field framework.
2. **`request_user_input` to confirm** — add/remove items, is the field framework right?
3. Ask for a time range.
4. Launch a web-search agent to *supplement* the framework — verify missing objects, add items, add fields.
5. Emit `outline.yaml` (items) + `fields.yaml` (field definitions).

**Phase 2 — `research-deep`: fan out per item.**
- Auto-locate `outline.yaml`.
- **Resume check** — "Check completed JSON files in output_dir; skip completed items."
- Batch execution with **user approval required before the next batch**.
- One agent per item; output structured JSON at `{output_dir}/{item_slug}.json`.
- **Mark uncertain field values with `[uncertain]`, and add an `uncertain` array listing every uncertain field name.**
- A validation script enforces complete field coverage; *"Task is complete only after validation passes."*

**Phase 3 — `research-report`: synthesise.**
- Read all JSON, **skip fields containing `[uncertain]` and fields listed in the `uncertain` array**.
- Generate markdown: TOC with anchor links + user-chosen summary metrics, then detail by field category.

### 2.2 Why this maps unusually well onto Genesis

Genesis's `research_orchestrator` runs streams A/B/C/D → `merge_streams` →
ranked pitfalls → Evidence Pack. It is **opportunistic**: it gathers, then
ranks what it happened to find. There is no outline phase, so nothing defines
what *should* have been found — which is precisely why `check_floor()` exists
as a blunt after-the-fact count (`FLOOR_MIN_REPOS = 12`).

The pack's items×fields grid is the missing structure: it states the target
*before* gathering, so coverage becomes measurable instead of estimated.

Two mechanisms transfer almost unchanged:

- **`[uncertain]` + skip-on-report** is the same discipline as this repo's
  honesty clause — and the same bug class as the star-count fix, where an
  unreported value was being coerced to `0` and rendered indistinguishable
  from a real zero. `RepoResult.stars: int | None` is already this pattern;
  the research pack generalises it to every field.
- **Resume check** is `load_from_vault()` generalised from whole-summary
  caching to per-item caching, which is what makes a long research run
  interruptible.

### 2.3 Concrete changes

| # | Module | Change | Effort |
|---|---|---|---|
| R1 | **new** `research_outline.py` | `Outline` (topic, items, fields) + `outline.yaml`/`fields.yaml` read/write. Pure data, L0 — no internal deps, so it can't add a cycle | M |
| R2 | `research_orchestrator.py` | Accept an optional `Outline`; compute **coverage** (fields filled / fields defined per item) instead of only counting repos | M |
| R3 | `research_orchestrator.py` | Add `uncertain: list[str]` to `ResearchSummary`; `format_summary()` skips uncertain values rather than printing them | S |
| R4 | `gde_gate_engine.py` | New gate `RESEARCH_COVERAGE_LOW` (BLOCK_AND_ASK, overridable) — the batch-approval checkpoint, expressed in Genesis's existing gate vocabulary rather than a new mechanism | S |
| R5 | `gde_engine_registration.py` | Register `research_outline` engine for `RESEARCH` mode, ahead of `field_intelligence`; `check_floor` becomes coverage-based | M |
| R6 | `mcp_advisor.py` | Already recommends `deep-research-skills`; extend `orchestration` text to name the outline→deep→report flow | S |

### 2.4 Applying it to a new project spec

For a greenfield app, the flow becomes:

1. `genesis fetch deep-research-skills` — read the protocol (ephemeral, auto-purged).
2. **Outline first:** items = candidate libraries/approaches; fields = the
   decision criteria (license, maintenance, bundle size, CVE history).
   Confirm the grid before any searching.
3. **Deep pass per item**, resumable, every unknown explicitly `[uncertain]`.
4. **Report** skips uncertainties instead of guessing — feeding the Evidence
   Pack a grid with holes visibly marked, which is far more useful to a
   `decide` session than smooth prose hiding the same holes.

---

## Implementation order

Dependency-ordered, each step independently shippable and testable:

1. **A1 + A3** — `handoffs` field + registry validation. Smallest change, and
   it is the structural guarantee everything else leans on.
2. **A2** — populate handoffs across the 18 descriptors.
3. **R1** — `research_outline.py` as a pure L0 module with its own tests.
4. **R3** — `uncertain` propagation (independent of R1; ships alone).
5. **R2 + R5** — wire the outline into the orchestrator and registry.
6. **R4** — the coverage gate, once coverage is actually computed.
7. **A4 + A5** — evidence/inference split and declared failure modes.

Steps 1–2 and 3–4 are parallelisable. Nothing here requires executing fetched
code: both packs are markdown, which is why fetch-and-read was sufficient.

## Provenance

Both packs are MIT. Nothing from either was vendored into this repository —
patterns were read and reimplemented against Genesis's own types. The
sandboxes are ephemeral and Auto-Purge removes them on TTL expiry.
