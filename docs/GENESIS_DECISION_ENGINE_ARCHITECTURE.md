# Genesis Decision Engine — Architecture & Implementation Plan

**Document type:** Architecture specification and implementation plan  
**Status:** Pre-implementation — approved for design, not yet coded  
**Replaces:** "Governance Orchestrator (P1)"  
**Package:** `genesis_architect_pro`  
**Target module:** `genesis_architect_pro.decision_engine`

---

## 1. What Is the Genesis Decision Engine?

The Genesis Decision Engine (GDE) is the central brain of Genesis Architect PRO. It replaces ad-hoc per-feature coordination with a single, authoritative orchestration layer that decides:

- What Genesis should do
- In what order
- Which engines to invoke
- What questions to ask the user
- When to consult the Architecture Committee
- When to enter Research Mode or Recovery Mode
- When to stop and request approval
- When to continue automatically
- How confident it is in every decision it makes

Every other subsystem — Recovery Intelligence, Research Intelligence, Rules Engine, MCP Tools, Committee, Project Memory, Visual Workspace — becomes an **engine** behind the GDE. The GDE is the only caller that coordinates across multiple engines. Engines never coordinate with each other directly.

---

## 2. Design Principles

1. **Single entry point.** One function starts the Decision Engine for any intent. Callers do not choose which engines run — the GDE decides.
2. **State machine, not script.** The GDE advances through named states. Each state transition is explicit, logged, and recoverable.
3. **Confidence-first.** Every decision carries a confidence score inherited from its evidence. Low confidence → ask the user. High confidence + explicit approval gate → stop and request.
4. **Fail-open.** If an engine fails, the GDE degrades gracefully. It never crashes. It records the failure and continues with reduced confidence.
5. **Immutable intent.** The initial user intent is locked at session start. The GDE adapts strategy but never changes what was asked.
6. **Transparent decisions.** Every decision the GDE makes is recorded in a decision log. The user can always ask "why did you do that?"
7. **Pluggable engines.** Adding a new engine means registering it. No change to GDE core logic.
8. **Approval gates are explicit.** The set of actions that require user approval is enumerated in a policy table, not scattered in code.

---

## 3. Current Architecture Audit

### Existing engines (all become GDE clients)

| Engine | Module | Purpose | Mode |
|---|---|---|---|
| Architecture Scorer | `architecture_scorer` | 0-100 health score + history | Read-only |
| Anti-pattern Detector | `antipattern_detector` | 7-type structural anti-patterns | Read-only |
| Fragility Classifier | `fragility_classifier` | STABLE/FRAGILE/VOLATILE module classification | Read-only |
| Dependency Index | `dependency_index` | Reverse-dependency O(1) map | Read-only |
| Drift Detector | `drift_detector` | Vagrant + stale candidate flags | Read-only |
| Drift Scorer | `drift_scorer` | Numeric drift score [0, 100] | Read-only |
| Source Anchor | `source_anchor` | Responsibility → code mapping | Read + write |
| Recovery Report | `recovery_report` | Unified diagnostic report | Read-only |
| Recovery Scan | `recovery_scan` | Full pipeline scan | Orchestrated |
| Decay Regressor | `decay_regressor` | Temporal decay forecast | Read-only |
| Git Analyzer | `git_analyzer` | Per-module churn history | Read-only |
| Import Audit | `import_audit` | Declared vs actual edges | Read-only |
| Model Store | `model_store` | Architecture model persistence | Read + write |
| Research Orchestrator | `research_orchestrator` | Multi-stream research (Phase 2) | Read + write |
| Video Research | `video_research` | Media signal extraction | Read-only |
| Pitfall Ranker | `pitfall_ranker` | Cross-source pitfall ranking | Read-only |
| Refactoring Planner | `refactoring_planner` | Actionable refactoring plans | Read-only |
| C4 Generator | `c4_generator` | Architecture diagram generation | Read-only |
| Security Templates | `security_templates` | STRIDE + OWASP docs | Read-only |
| Package Registry | `package_registry` | PyPI/npm/crates health signals | Read-only |
| Cross Session Memory | `cross_session_memory` | Session state persistence | Read + write |
| MCP Tools | `mcp_tools` | External MCP tool exposure | Read-only |
| Rules Engine | `rules_engine` | Policy gate evaluation | Read-only |
| License | `license` | Ed25519 key validation | Read-only |

### What does NOT exist yet

- A unified orchestration layer
- A state machine governing transitions between modes
- An explicit approval gate policy
- A context flow contract (what data flows where)
- A memory flow contract (what persists, what is ephemeral)
- A failure recovery protocol
- An engine registry (currently: direct imports everywhere)
- A decision log

---

## 4. Engine Responsibilities (Post-GDE)

Each engine has exactly one responsibility. The GDE composes them.

| Engine category | Responsibility boundary |
|---|---|
| **Analysis engines** | Accept input data; return structured output. No side effects. No knowledge of other engines. |
| **Persistence engines** | Accept data; read/write to disk. Expose clear read/write methods. No orchestration logic. |
| **Report engines** | Accept structured data; produce formatted output. No disk access. |
| **Research engines** | Invoke external sources (APIs, Exa, video); return ranked signals. |
| **Gate engines** | Accept facts; evaluate policy; return pass/warn/fail + reasons. |
| **Memory engines** | Accept session state; read/write to `.genesis/` files. |

The GDE alone crosses these boundaries. No engine invokes another engine.

---

## 5. Execution Lifecycle

The GDE follows a seven-stage lifecycle for every session.

```
INTAKE → PLAN → EXECUTE → GATE → REPORT → APPROVE → COMMIT
```

### Stage 1: INTAKE
- Receive user intent (free-text or structured command)
- Classify intent into one of the defined modes (see Section 6)
- Load project context (import graph, model state, session memory)
- Set initial confidence based on context completeness
- Produce: `Intent`, `ProjectContext`, initial `EngineQueue`

### Stage 2: PLAN
- Build the execution plan for the classified mode
- Resolve engine dependencies (topological sort)
- Identify approval gates required for this plan
- Identify questions the user must answer before proceeding
- Ask clarifying questions if confidence < threshold or required inputs missing
- Produce: `ExecutionPlan` (ordered list of `EngineTask` objects)

### Stage 3: EXECUTE
- Run each `EngineTask` in plan order
- Respect dependency constraints (parallel where safe, sequential where required)
- On engine failure: record in `DecisionLog`, set confidence penalty, continue with fallback
- Aggregate results into `SessionContext`
- Produce: `EngineResultSet`

### Stage 4: GATE
- Evaluate all approval gates against `EngineResultSet`
- Gates can be: auto-pass, warn, block-and-ask, or hard-block
- Compile gate results into `GateReport`
- If any hard-block: halt and surface reason to user
- Produce: `GateReport`

### Stage 5: REPORT
- Render output for the current mode (Recovery Report, Research Summary, Refactoring Plan, etc.)
- Attach `GateReport`, `DecisionLog`, and confidence breakdown
- Produce: `SessionReport` (format determined by mode)

### Stage 6: APPROVE
- Present `SessionReport` to user
- If mode requires approval before any write operations: wait
- User choices: approve, reject, partial-approve, modify, defer
- On approve: advance to COMMIT
- On reject or defer: save session state to memory; halt
- Produce: `ApprovalDecision`

### Stage 7: COMMIT
- Execute all approved write operations atomically
- Update session memory (`cross_session_memory`)
- Append to decision log
- Emit final status
- Produce: `CommitResult`

---

## 6. State Machine

The GDE operates in named **modes**. Each mode defines which engines run, which gates apply, and what approval is required.

### Mode definitions

```
IDLE
 │
 ├─── intent: diagnose ──────────────→ RECOVERY_MODE
 │
 ├─── intent: research ──────────────→ RESEARCH_MODE
 │
 ├─── intent: plan_refactor ─────────→ REFACTOR_MODE
 │
 ├─── intent: gate_check ────────────→ GATE_MODE
 │
 ├─── intent: build / scaffold ──────→ BUILD_MODE
 │
 ├─── intent: document ──────────────→ DOCUMENT_MODE
 │
 └─── intent: unknown / complex ─────→ COMMITTEE_MODE
```

### State transition table

| From state | Trigger | To state | Approval required? |
|---|---|---|---|
| IDLE | Any intent received | INTAKE | No |
| INTAKE | Intent classified | PLAN | No |
| PLAN | Questions resolved | EXECUTE | No |
| PLAN | Confidence < 0.40 | COMMITTEE_MODE | Yes |
| EXECUTE | All engines complete | GATE | No |
| EXECUTE | Critical engine failure | DEGRADED | No |
| GATE | All gates pass | REPORT | No |
| GATE | Hard-block gate fires | BLOCKED | Yes |
| REPORT | Report generated | APPROVE | Yes (if write ops pending) |
| REPORT | No write ops | IDLE | No |
| APPROVE | User approves | COMMIT | No |
| APPROVE | User rejects | IDLE | No |
| APPROVE | User defers | SUSPENDED | No |
| COMMIT | All writes succeed | IDLE | No |
| COMMIT | Write failure | ROLLBACK | No |
| DEGRADED | Sufficient engines available | GATE | No |
| DEGRADED | Too few engines | BLOCKED | Yes |
| SUSPENDED | User resumes | PLAN (reload) | No |
| ROLLBACK | Complete | IDLE | No |

### Mode-to-engine mapping

| Mode | Required engines | Optional engines | Approval gate |
|---|---|---|---|
| RECOVERY_MODE | recovery_scan, recovery_report | decay_regressor | project_risk_level ≥ high |
| RESEARCH_MODE | research_orchestrator, pitfall_ranker | video_research, package_registry | Before writing vault |
| REFACTOR_MODE | antipattern_detector, fragility_classifier, refactoring_planner | import_audit | Before writing plan |
| GATE_MODE | rules_engine, architecture_scorer | import_audit, drift_detector | Always (gate exists to block) |
| BUILD_MODE | model_store, source_anchor | c4_generator, security_templates | Before any model.json write |
| DOCUMENT_MODE | c4_generator, security_templates | recovery_report | Before writing docs |
| COMMITTEE_MODE | All above + cross_session_memory | None | Always |

---

## 7. Approval Gates

Approval gates are declared in a policy table. They are not hardcoded in engine logic.

### Gate policy table

| Gate ID | Trigger condition | Default action | Override allowed? |
|---|---|---|---|
| `RISK_HIGH` | `project_risk_level` ≥ high | Block and ask | Yes, with reason |
| `DRIFT_CRITICAL` | `drift_score.overall_score` ≥ 75 | Warn and ask | Yes |
| `VAGRANT_HIGH_CONF` | Any vagrant candidate with confidence ≥ 0.85 | Warn and ask | Yes |
| `MODEL_WRITE` | Any write to `model.json` | Block and ask | No |
| `PLAN_WRITE` | Any write to `planned.json` | Hard-block | Never |
| `VAULT_WRITE` | Writing research to vault | Block and ask | Yes |
| `REFACTOR_PLAN_WRITE` | Writing REFACTORING.md | Block and ask | Yes |
| `RULES_FAIL` | Any rules_engine FAIL result | Hard-block | No |
| `RULES_WARN` | Any rules_engine WARN result | Warn only | Implicit |
| `LOW_CONFIDENCE` | Session confidence < 0.45 | Ask before proceeding | Yes |
| `RESUME_STALE` | Session > 72h old | Ask to confirm resume | Yes |
| `ENGINE_FAILURE` | Any required engine fails | Warn and ask to proceed | Yes |

### Gate resolution protocol

```
1. Evaluate all gate conditions against EngineResultSet
2. Sort by severity: hard-block → block-and-ask → warn → pass
3. If any hard-block: halt. Emit reason. Do not proceed.
4. If any block-and-ask: surface to user with recommended action.
5. User can approve to downgrade block → warn.
6. If all gates are warn or pass: continue.
7. All gate outcomes recorded in DecisionLog.
```

---

## 8. Engine Interfaces

Every engine exposed to the GDE implements a standard interface via a registration descriptor. The GDE never imports engines directly — it discovers them through the registry.

### `EngineDescriptor` (registration contract)

```python
@dataclass
class EngineDescriptor:
    id: str                         # unique, kebab-case: "recovery-scan"
    name: str                       # human-readable: "Recovery Scan"
    module: str                     # import path: "genesis_architect_pro.recovery_scan"
    entry_point: str                # function name: "scan"
    category: EngineCategory        # ANALYSIS | PERSISTENCE | REPORT | RESEARCH | GATE | MEMORY
    input_keys: list[str]           # keys this engine reads from SessionContext
    output_keys: list[str]          # keys this engine writes to SessionContext
    requires: list[str]             # engine IDs that must run before this one
    is_optional: bool               # False = required for its mode; True = best-effort
    write_operations: list[str]     # non-empty = requires APPROVE gate before execution
    timeout_seconds: int            # per-engine timeout; default 60
```

### `EngineResult` (output contract)

```python
@dataclass
class EngineResult:
    engine_id: str
    status: EngineStatus            # SUCCESS | DEGRADED | FAILED | SKIPPED
    output: dict                    # key→value pairs written to SessionContext
    confidence: float               # 0.0–1.0 inherited from engine's own scoring
    warnings: list[str]             # non-fatal issues
    error: str | None               # set on FAILED
    duration_ms: int
```

### Calling convention

The GDE calls each engine like this:

```python
result = engine_runner.run(
    descriptor=descriptor,
    context=session_context,        # read-only view of accumulated results
    project_dir=project_dir,
)
```

Engines receive only what they declared in `input_keys`. They return an `EngineResult`. The GDE merges `output` into `SessionContext`.

---

## 9. Context Flow

`SessionContext` is the single shared data structure that flows through the entire lifecycle. It is append-only during EXECUTE. No engine may modify keys written by a previous engine.

### `SessionContext` structure

```python
@dataclass
class SessionContext:
    # Identity
    session_id: str                 # uuid4, stable across resume
    intent: Intent                  # classified user intent
    mode: GDEMode                   # current execution mode
    project_dir: Path

    # Project state (loaded at INTAKE)
    import_graph: dict              # from import_graph.load_or_build()
    model_state: dict               # from model_store (committed + planned summary)
    session_memory: dict            # from cross_session_memory.restore_session()

    # Accumulated engine outputs (grows during EXECUTE)
    engine_results: dict[str, EngineResult]

    # Derived aggregate views (computed after EXECUTE)
    overall_confidence: float
    project_risk_level: str         # none/low/medium/high/critical
    pending_write_operations: list[WriteOperation]

    # Decision log (append-only throughout)
    decision_log: list[DecisionEntry]
```

### Context flow diagram

```
INTAKE
  └─ load: import_graph, model_state, session_memory
  └─ write: session_id, intent, mode, project_dir

PLAN
  └─ read: intent, mode, session_memory
  └─ write: execution_plan, clarifying_questions

EXECUTE (per engine, in plan order)
  └─ read: context keys declared in engine.input_keys
  └─ write: context keys declared in engine.output_keys
  └─ each engine gets a read-only snapshot; writes are queued then merged

GATE
  └─ read: all engine_results, overall_confidence, project_risk_level
  └─ write: gate_report (does not modify engine outputs)

REPORT
  └─ read: entire SessionContext
  └─ write: session_report (formatted output, not stored in context)

APPROVE
  └─ read: pending_write_operations, gate_report
  └─ write: approval_decision

COMMIT
  └─ read: approval_decision, pending_write_operations
  └─ execute: writes atomically
  └─ write: commit_result, updated session_memory
```

### Key isolation guarantee

- Engines in the same phase that have no declared dependencies on each other may run in parallel.
- Engines with declared `requires` run strictly after their dependencies complete.
- The context is the only communication channel between engines. No engine may import or call another engine.

---

## 10. Memory Flow

Two memory tiers:

### Tier 1: Session memory (ephemeral, within `.genesis/`)

Managed by `cross_session_memory`. Persists across restarts; expires after configurable TTL (default 72h).

```
.genesis/
  gde_session.json          # current session state (SessionContext snapshot)
  gde_decision_log.jsonl    # append-only decision log across all sessions
  gde_last_run.json         # last completed session summary
```

**Written at:** end of every stage (PLAN, EXECUTE, GATE, COMMIT)  
**Read at:** INTAKE (to resume a suspended session)  
**TTL:** 72h (configurable). Stale sessions surface a `RESUME_STALE` gate.

### Tier 2: Project memory (permanent, within `.genesis/`)

Managed by existing engines (`model_store`, `research_orchestrator.vault`, `score_history.jsonl`).

```
.genesis/
  model.json                # committed architecture model (model_store)
  planned.json              # planned architecture model (READ-ONLY to GDE)
  score_history.jsonl       # architecture score history (architecture_scorer)
  source_map.json           # responsibility→code anchors (source_anchor)
  vault/                    # research cache (research_orchestrator)
  rules.json                # gate policy overrides (rules_engine)
```

**Written by:** approved write operations only (post-APPROVE stage)  
**Read by:** multiple engines at INTAKE and EXECUTE  
**Never modified by GDE directly** — GDE queues operations; engines execute them.

### Memory flow rules

1. The GDE reads session memory at INTAKE; never mid-session.
2. Writes to project memory only happen in COMMIT, after approval.
3. The decision log is append-only; it is never overwritten.
4. A suspended session can be resumed from `gde_session.json` exactly where it stopped.
5. `planned.json` is immutable from the GDE's perspective. No engine registered with the GDE may write it.

---

## 11. Failure Recovery

### Engine failure protocol

```
Engine fails (exception or timeout)
   │
   ├─ Engine is_optional=True
   │    └─ Record FAILED in EngineResult
   │    └─ Apply confidence penalty: -0.10
   │    └─ Continue with remaining engines
   │
   └─ Engine is_optional=False (required)
        ├─ Attempt once (no auto-retry — silent retries mask real failures)
        ├─ Record FAILED in EngineResult
        ├─ Apply confidence penalty: -0.20
        ├─ Set mode to DEGRADED
        └─ Surface to user: "Engine X failed. Proceed with reduced confidence?"
             ├─ User approves → continue in DEGRADED
             └─ User rejects → save session; halt
```

### Session crash recovery

If the process is killed mid-session (crash, timeout, user kill):
- `gde_session.json` contains the last completed stage snapshot
- On next invocation with the same project, INTAKE detects the suspended session
- `RESUME_STALE` gate fires if session is >72h old
- User is shown: "Previous session found (EXECUTE stage, 3/8 engines complete). Resume?"
- On resume: re-run only incomplete engines from the saved plan

### Write failure recovery

If a write operation fails during COMMIT:
- The GDE rolls back any writes completed so far (using temp files + atomic rename)
- State returns to pre-COMMIT (approved but uncommitted)
- User is shown: "Write failed: [reason]. Retry?"
- The approval decision is preserved; no re-approval needed on retry

### Rollback strategy

All write operations use this pattern:
```
1. Write to temp file (e.g., model.json.gde_tmp)
2. Validate written content (parse and verify)
3. Atomic rename to target path
4. Record in commit_result
```
If step 3 fails for any operation, all successfully-renamed files in this batch are reverted from the decision log.

---

## 12. Extensibility Rules

### Adding a new engine

1. Create the module in `genesis_architect_pro/<engine_name>.py`
2. Implement the engine's entry point function with this signature:
   ```python
   def run(context_inputs: dict, project_dir: Path) -> dict:
       # context_inputs: only the keys declared in EngineDescriptor.input_keys
       # returns: only the keys declared in EngineDescriptor.output_keys
   ```
3. Register an `EngineDescriptor` in `genesis_architect_pro/engine_registry.py`
4. Add the engine to the relevant mode's engine list in `gde_mode_config.py`
5. Write tests. No changes to GDE core logic required.

### Adding a new mode

1. Add the mode enum value to `GDEMode`
2. Define the mode's engine list and gate policy in `gde_mode_config.py`
3. Add the intent classifier rule in `intent_classifier.py`
4. No changes to the state machine or EXECUTE logic required.

### Adding a new gate

1. Add the gate condition to `GatePolicyTable` in `gate_engine.py`
2. Define: trigger condition (lambda over SessionContext), default action, override-allowed flag
3. No changes to GDE core logic required.

### Adding a new approval action

Any write operation that an engine wants to perform must be declared in its `EngineDescriptor.write_operations`. The GDE automatically collects these and presents them in APPROVE. No special registration needed.

### Rules for engine authors

- **No cross-engine imports.** An engine must not import or call another engine.
- **No direct disk writes during EXECUTE.** Queue a `WriteOperation` instead.
- **Declare all I/O in the descriptor.** The GDE enforces this at registration time.
- **Return confidence.** Every engine result carries a confidence float. Never omit it.
- **Never raise.** Engines catch all exceptions internally and return a FAILED result.

---

## 13. How Future Systems Plug In

### Plug-in contract

A future system (Committee, Visual Workspace, Future AI Agents) becomes a GDE engine by:

1. Implementing the `run(context_inputs, project_dir) -> dict` function
2. Registering an `EngineDescriptor`
3. Declaring its input/output keys and dependencies

### Specific future systems

**Architecture Committee**
- Engine ID: `architecture-committee`
- Mode: COMMITTEE_MODE
- Input keys: `engine_results`, `intent`, `overall_confidence`
- Output keys: `committee_recommendation`, `committee_questions`
- Write operations: none (read-only deliberation output)
- Triggers: when `overall_confidence` < 0.40 or mode = COMMITTEE_MODE

**Visual Workspace**
- Engine ID: `visual-workspace`
- Mode: DOCUMENT_MODE, BUILD_MODE
- Input keys: `c4_output`, `model_state`, `recovery_report`
- Output keys: `workspace_render_path`
- Write operations: `workspace/<session_id>/`

**Future AI Agents**
- Engine ID: `<agent-name>-agent`
- Mode: Any
- Input keys: declared per-agent
- Output keys: declared per-agent
- All agent engines must declare `requires: ["recovery-scan"]` at minimum to ensure they have project context
- Agent outputs are treated as advisory signals — they do not bypass approval gates

**MCP Intelligence (expanded)**
- Current `mcp_tools` becomes a thin adapter layer
- The GDE's `SessionContext` becomes the authoritative MCP resource
- External MCP clients can query the GDE for live state rather than calling engines directly

**Project Memory (future)**
- Extends `cross_session_memory` with long-horizon memory (beyond 72h)
- Plugs in as a memory engine at INTAKE and COMMIT
- Provides "what did we decide last month about this module?" context

---

## 14. Decision Log

Every decision the GDE makes is recorded as an immutable entry in `gde_decision_log.jsonl`.

### `DecisionEntry` schema

```python
@dataclass
class DecisionEntry:
    session_id: str
    timestamp: str                  # ISO 8601
    stage: str                      # INTAKE | PLAN | EXECUTE | GATE | REPORT | APPROVE | COMMIT
    decision_type: str              # ENGINE_INVOKED | ENGINE_FAILED | GATE_FIRED | APPROVAL_REQUESTED |
                                    # APPROVAL_GRANTED | APPROVAL_REJECTED | WRITE_COMMITTED | MODE_TRANSITION
    actor: str                      # "gde" | "user" | engine_id
    subject: str                    # what the decision is about
    detail: str                     # human-readable explanation
    confidence_before: float
    confidence_after: float
    outcome: str                    # the result or user's choice
```

The decision log is the audit trail. Users can always ask: "Why did Genesis do that?" and receive a factual answer from the log.

---

## 15. Implementation Plan

The GDE is built in six implementation steps. Each step is independently testable and merges cleanly.

### Step 1: Foundation — Types, Registry, Context

**Files to create:**
- `genesis_architect_pro/gde_types.py` — all dataclasses: `Intent`, `GDEMode`, `EngineCategory`, `EngineDescriptor`, `EngineResult`, `EngineStatus`, `SessionContext`, `DecisionEntry`, `WriteOperation`, `ApprovalDecision`, `CommitResult`, `GateResult`, `GatePolicyTable`
- `genesis_architect_pro/engine_registry.py` — `EngineRegistry` class; descriptor registration; topological sort for dependency ordering
- `genesis_architect_pro/gde_session.py` — `SessionContext` builder, serialiser, deserialiser; `.genesis/gde_session.json` read/write

**Test targets:** descriptor validation, topological sort with cycles, context serialisation roundtrip, load/save session

**Completion criteria:** All existing engines can be described by an `EngineDescriptor` without any code change to those engines.

---

### Step 2: Intent Classifier

**Files to create:**
- `genesis_architect_pro/intent_classifier.py` — `classify_intent(text: str, project_context: dict) -> Intent`

**`Intent` fields:**
```python
@dataclass
class Intent:
    raw_text: str
    mode: GDEMode
    confidence: float
    signals: list[str]              # which keywords/patterns triggered the classification
    clarifying_questions: list[str] # questions needed before plan can be built
    params: dict                    # mode-specific extracted parameters
```

**Classification rules (priority order):**

| Signal keywords / patterns | Mode |
|---|---|
| "recover", "drift", "what's wrong", "health", "diagnose" | RECOVERY_MODE |
| "research", "investigate", "competitors", "what's out there" | RESEARCH_MODE |
| "refactor", "fix", "clean up", "improve", "restructure" | REFACTOR_MODE |
| "gate", "check", "validate", "block", "policy", "rules" | GATE_MODE |
| "build", "scaffold", "create", "generate", "init" | BUILD_MODE |
| "document", "diagram", "C4", "README", "security" | DOCUMENT_MODE |
| Low confidence on all above | COMMITTEE_MODE |

**Test targets:** each mode classified correctly, ambiguous intents → COMMITTEE_MODE, confidence scores calibrated

---

### Step 3: Execution Planner + Engine Runner

**Files to create:**
- `genesis_architect_pro/gde_planner.py` — builds `ExecutionPlan` from mode + registry; resolves dependencies; identifies parallel groups
- `genesis_architect_pro/engine_runner.py` — executes a single `EngineDescriptor` against a `SessionContext`; enforces timeout; catches all exceptions; returns `EngineResult`

**`ExecutionPlan` structure:**
```python
@dataclass
class ExecutionPlan:
    mode: GDEMode
    phases: list[list[EngineDescriptor]]  # outer = sequential phases; inner = parallel group
    required_approvals: list[str]          # gate IDs that will fire
    estimated_duration_seconds: int
    write_operations_pending: list[str]    # what will be written if approved
```

**Execution model:**
- Engines in the same inner list run concurrently (ThreadPoolExecutor, max 4 workers)
- Engines in different outer-list phases run sequentially
- Each engine has a per-engine timeout (from descriptor)
- Thread safety: each engine receives a frozen snapshot of SessionContext inputs

**Test targets:** plan builds correctly for each mode, parallel groups respect dependency order, engine runner handles exceptions, timeout fires correctly

---

### Step 4: Gate Engine

**Files to create:**
- `genesis_architect_pro/gate_engine.py` — evaluates all registered gates against `SessionContext`; returns `GateReport`

**`GateReport` structure:**
```python
@dataclass
class GateReport:
    passed: list[GateResult]
    warnings: list[GateResult]
    blocks: list[GateResult]        # block-and-ask
    hard_blocks: list[GateResult]   # cannot proceed
    overall: GateOutcome            # PASS | WARN | BLOCK | HARD_BLOCK
```

**Test targets:** each gate condition fires on correct input, override-allowed gates can be downgraded, hard-block gates cannot be overridden

---

### Step 5: Approval + Commit Layer

**Files to create:**
- `genesis_architect_pro/gde_approval.py` — formats approval requests; records decisions; returns `ApprovalDecision`
- `genesis_architect_pro/gde_commit.py` — executes approved `WriteOperation` list atomically; rollback on failure; updates session memory

**Test targets:** write operations execute atomically, rollback reverts all writes on partial failure, decision log updated correctly, session memory reflects committed state

---

### Step 6: GDE Entry Point + CLI Integration

**Files to create:**
- `genesis_architect_pro/decision_engine.py` — `GenesisDecisionEngine` class; `run(intent_text, project_dir, *, auto_approve=False) -> SessionReport`; full state machine
- `genesis_architect_pro/gde_mode_config.py` — mode-to-engine mapping table; gate policy table

**Update:**
- `genesis_architect_pro/__init__.py` — export `GenesisDecisionEngine`, `GDEMode`, `Intent`, `SessionReport`
- `pyproject.toml` — add `genesis` CLI entry point: `genesis = "genesis_architect_pro.decision_engine:cli_main"`

**CLI commands:**
```
genesis run "<intent>"              # full GDE pipeline
genesis recover                     # shortcut: RECOVERY_MODE
genesis gate                        # shortcut: GATE_MODE
genesis research "<topic>"          # shortcut: RESEARCH_MODE
genesis resume                      # resume last suspended session
genesis log                         # show decision log
genesis status                      # show current session state
```

---

## 16. File Inventory (New Files)

| File | Purpose | Step |
|---|---|---|
| `gde_types.py` | All GDE dataclasses and enums | 1 |
| `engine_registry.py` | Engine descriptor store + dependency resolver | 1 |
| `gde_session.py` | SessionContext persistence | 1 |
| `intent_classifier.py` | User intent → GDEMode + Intent | 2 |
| `gde_planner.py` | ExecutionPlan builder | 3 |
| `engine_runner.py` | Single-engine executor with timeout + catch | 3 |
| `gate_engine.py` | Gate policy evaluator | 4 |
| `gde_approval.py` | Approval request formatter + recorder | 5 |
| `gde_commit.py` | Atomic write executor + rollback | 5 |
| `decision_engine.py` | GenesisDecisionEngine main class + CLI | 6 |
| `gde_mode_config.py` | Mode→engine mapping + gate policy table | 6 |

**No existing files are modified during implementation** (except `__init__.py` and `pyproject.toml`). All 22 existing engines plug in through the registry with zero changes to their source.

---

## 17. Testing Strategy

Each step has a dedicated test file:

| Test file | Step | Target |
|---|---|---|
| `test_gde_types.py` | 1 | Dataclass validation, serialisation roundtrips |
| `test_engine_registry.py` | 1 | Descriptor registration, topological sort, cycle detection |
| `test_gde_session.py` | 1 | Context load/save, resume from file |
| `test_intent_classifier.py` | 2 | All modes, ambiguous inputs, confidence calibration |
| `test_gde_planner.py` | 3 | Plan generation, dependency ordering, parallel grouping |
| `test_engine_runner.py` | 3 | Success, failure, timeout, exception isolation |
| `test_gate_engine.py` | 4 | Each gate, override, hard-block enforcement |
| `test_gde_approval.py` | 5 | Approval formatting, decision recording |
| `test_gde_commit.py` | 5 | Atomic write, rollback on partial failure |
| `test_decision_engine.py` | 6 | End-to-end per mode, CLI commands |

**Coverage requirement:** Every gate, every state transition, every engine failure path must be tested before the step is considered complete.

---

## 18. Compatibility and Non-Goals

### Compatibility

- All 34 existing `__init__.py` exports remain unchanged
- All 998 existing tests continue to pass throughout implementation
- Each step is independently deployable — no big-bang integration
- Existing callers of `generate_report_for_project()`, `scan()`, etc. are unaffected

### Non-goals for v1.0 of GDE

- No LLM calls within the GDE itself (engines may use LLMs; the GDE does not)
- No network access by the GDE itself (engines handle their own I/O)
- No GUI
- No streaming progress to callers (milestone-level progress only)
- No multi-project coordination
- No team/multi-user session sharing

---

## 19. Confidence Model

The GDE maintains a running `overall_confidence` that starts at 1.0 and is adjusted throughout the session.

| Event | Confidence delta |
|---|---|
| Optional engine FAILED | -0.10 |
| Required engine FAILED (DEGRADED) | -0.20 |
| Gate WARN fired | -0.05 |
| Gate BLOCK fired | -0.15 |
| Required clarifying questions answered | +0.10 |
| Project has complete model.json | +0.05 |
| Project has score history ≥ 3 records | +0.05 |
| Confidence floor: | 0.10 |
| Confidence ceiling: | 1.00 |

When `overall_confidence` drops below 0.45 mid-EXECUTE, the GDE surfaces a warning to the user before continuing. When it drops below 0.30, it halts and enters COMMITTEE_MODE or BLOCKED.

---

## 20. Summary

The Genesis Decision Engine transforms Genesis Architect PRO from a collection of powerful but disconnected analysis modules into a coherent, orchestrated system with a clear execution lifecycle, explicit approval gates, a persistent decision log, and a clean extension model for all future systems.

**What exists today:** 22 capable engines with no coordinator.  
**What the GDE adds:** one authoritative coordinator that composes them correctly, safely, and transparently.

**Frozen:** Recovery Intelligence v1.0 — read-only from GDE perspective.  
**Owned by GDE:** Execution order, approval gates, memory flow, decision log.  
**Owned by engines:** Their own logic, inputs, and outputs — nothing else.

The design is additive. No existing engine is modified. The GDE wraps them.

---

*Document complete. Awaiting approval to begin Step 1 implementation.*
