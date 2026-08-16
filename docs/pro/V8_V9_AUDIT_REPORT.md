# Genesis v8→v9 Audit Report

**Date:** 2026-08-17 · **Version audited:** `genesis-architect-pro` 8.0.0 · **Branch:** `pro-v3-analysis`

Every claim below was produced by executing code against the shipped
registry, not by reading it. Commands and their raw output are reproduced so
each line can be re-run. Where something is unverified, it says so.

---

## Status summary

| # | Capability | Status |
|---|---|---|
| 1 | Deterministic Decision Engine (GDE) | **PASS** |
| 2 | Adversarial Red-Team Gate | **PASS** |
| 3 | Auto-Purge & Ephemeral Hygiene | **PASS** (1 unverified platform path) |
| 4 | Two-Tier MCP Advisor | **PASS** |
| 5 | Dynamic Skill Fetcher & Purge | **PASS** (1 supply-chain gap) |
| 6 | Architecture & Research Integrations (A1–A5, R1–R6) | **PARTIAL — 3 of 11** |

**Headline:** five of six subsystems verify clean. Item 6 is **PARTIAL by
construction, not by defect**: A1, A2 and A3 are implemented and proven;
A4, A5 and R1–R6 were scoped as backlog and were never built. Reporting item 6
as PASS would be false.

**Totals:** 2029 passed · 1 skipped · 0 failed · ruff clean across `src/` and `tests/`.

---

## 1. Deterministic Decision Engine — PASS

```
classify() determinism over 100 runs: STABLE
registry validate():                  CLEAN
recovery    phases=5 engines=8      research    phases=4 engines=4
refactor    phases=4 engines=8      gate        phases=4 engines=10
build       phases=2 engines=2      document    phases=3 engines=4
committee   phases=5 engines=6
```

- **Routing is deterministic.** 100 identical invocations of `classify()`
  produced one mode. Classification is a weighted regex table — no LLM call,
  no sampling, so identical input cannot diverge.
- **The DAG resolves for all 7 modes**, each into an ordered phase list.
- **Zero circular dependencies.** Independently confirmed twice: the
  registry's own Kahn's-algorithm check returns CLEAN, and a separate
  DFS over the module import graph found no cycle across 13 modules,
  arranged in a strict 4-layer structure (kernel → services → composition →
  orchestration).

## 2. Adversarial Red-Team Gate — PASS

```
recovery/research/refactor/gate/build/document/committee:
    red_team_last=1   RED_TEAM_CRITICAL_gate=True     (all 7 modes)
gate policy: action=block_ask overridable=True
total gates in policy table: 13
```

- `red_team_critic` lands in the **final phase of every mode**, so the
  critique always sees the complete set of pending writes.
- `RED_TEAM_CRITICAL` is in every mode's required gates.
- The gate is `BLOCK_AND_ASK` and **overridable**, which is correct: findings
  are heuristic, so unlike `PLAN_WRITE`/`RULES_FAIL` it must never hard-block.
  A dedicated test asserts it never becomes `HARD_BLOCK`.
- Three deterministic checks run with no LLM. The adversarial LLM pass is
  additive, and its absence is **disclosed in `_warnings`** rather than left
  to look like full coverage.

## 3. Auto-Purge & Ephemeral Hygiene — PASS

```
read-only pack removal:   PASS
unmarked dir preserved:   PASS
dry-run is default:       PASS
```

- **Read-only git pack objects are handled.** This was a live defect: `git`
  writes `.git/objects/pack/*.idx` read-only, and `shutil.rmtree` failed with
  `WinError 5`, so an expired sandbox was detected but unremovable.
  `remove_tree()` clears the bit and retries; three regression tests
  reproduce the exact condition.
- **Opt-in only.** A directory with no `.ephemeral.json` survives `--apply`.
- **Dry run is the default**; `--apply` is the only deleting path.
- Refusals are recorded with reasons in `PurgeReport.protected`, so safety is
  visible in output rather than implied by silence.

**Unverified path:** the symlink-escape test is **skipped on Windows**
(`symlink creation needs privileges`). `_within_root()` resolves before
comparing and is platform-independent, so it very likely holds — but on the
primary development platform this guarantee is *reasoned*, not *observed*.
See D-2.

## 4. Two-Tier MCP Advisor — PASS

```
empty override does NOT fall through to ~/.claude.json:  PASS
override is authoritative:                               PASS
hermetic fixture refs in tests:                          5
```

- **Both tiers work.** LOCAL inspects manifests, git config, Dockerfile,
  `manifest_version`, migration dirs. GLOBAL reads `learning_engine` outcomes.
- **`GENESIS_MCP_CONFIG` is strictly authoritative.** This was a real bug: an
  override yielding no names fell through to the real `~/.claude.json`, so
  behaviour depended on the machine. Now the override wins outright, verified
  in both directions (empty override → empty set; populated → exactly those).
- **The suite is hermetic.** An autouse fixture pins every test to an empty
  config. Before this, the suite read the developer's actual `~/.claude.json`
  and would have passed locally and failed in CI.
- No recommendation can be emitted without the file that triggered it —
  enforced structurally, and asserted by a test iterating every recommendation.

*Scope note:* LOCAL inspection is **manifest- and file-based, not AST-based**.
The checklist says "AST/manifest inspection"; only the manifest half exists.
Adequate for tooling advice, but the wording overstates it. See D-5.

## 5. Dynamic Skill Fetcher & Purge — PASS

```
whitelist rejects url/traversal/case/injection:  PASS
execute() refuses:                               PASS
subprocess uses: ['subprocess.run', ...]         (git clone only)
eval/exec/__import__ present:                    False
--no-recurse-submodules:                         True
```

- **Whitelist-only.** Raw URLs, `../` traversal, case variants and
  `;`-injection are all refused. A fetch is addressed by `source_id` against a
  static registry, so "fetch this URL" is not a capability that exists.
- **Zero execution capability.** The only `subprocess` use is the `git clone`;
  no `eval`, `exec`, or `__import__` anywhere in the module. `execute()`
  exists solely to raise `NotImplementedError`, so the refusal is discoverable
  in the API rather than an absence someone later "fixes".
- `--no-recurse-submodules` prevents a submodule entry redirecting the fetch.
- **Multi-format packs handled.** Verified live against the real repo: 42
  `SKILL.md` files correctly reported as *14 distinct in 3 packaged formats*.
- **Sandbox discarding verified live**: fetch → read → purge, 1 removed, 0 errors.

**Supply-chain gap:** the clone is `--depth 1` with **no commit pin**. The
whitelist controls *who* is trusted, not *what version* arrives. A compromised
or force-pushed trusted repo would be fetched without detection. See D-1.

## 6. Architecture & Research Integrations — PARTIAL (3 of 11)

```
handoffs populated:                        16/18
validate() with handoff cycle present:     CLEAN
vendored external code:                    NONE
A5 failure_modes field:                    ABSENT
A4 evidence/inference split:                ABSENT
R1 research_outline module:                 ABSENT
R3 uncertain field:                        ABSENT
R4 RESEARCH_COVERAGE_LOW gate:              ABSENT
```

| Item | Status |
|---|---|
| A1 `handoffs` field | **PASS** |
| A2 populate handoffs | **PASS** — 16/18 (2 terminal on purpose) |
| A3 registry validation | **PASS** |
| A4 evidence/inference split | **NOT BUILT** |
| A5 `failure_modes` field | **NOT BUILT** |
| R1–R6 research protocol | **NOT BUILT** (0 of 6) |

**What is proven:** the shipped registry contains a genuine handoff cycle —
`recovery_report → refactoring_planner → rules_engine → recovery_report`
(diagnose → plan → enforce → re-diagnose) — and `validate()` is CLEAN with it
present. That is the A1 design decision demonstrated in production, not just
in a fixture: `requires` must stay acyclic because the planner sorts on it;
`handoffs` is advisory, so an iterative loop is a legitimate workflow.

**No vendoring.** Nothing from either external MIT pack was copied in;
patterns were read and reimplemented against Genesis's own types.

---

## Findings requiring hardening

Ordered by risk. None block current use; all are real.

### D-1 · No commit pinning in the fetcher — *medium*
`git clone --depth 1` with no ref. Trust is per-repository, not per-revision,
so a force-push or compromise of a whitelisted repo is fetched silently.
**Fix:** add `commit` or `tag` to `TrustedSource`, clone then `rev-parse HEAD`
and refuse on mismatch. Small change; closes the gap the whitelist implies is
already closed.

### D-2 · Symlink containment unverified on Windows — *medium*
The test proving a symlink cannot escape the sandbox is skipped on the primary
dev platform. The property is argued, not observed, exactly where it matters.
**Fix:** run that test in CI on Linux, or gate it on Developer Mode and let it
run when available.

### D-3 · `hygiene_notice()` walks the whole tree, unbounded — *medium*
Measured **0.85s on this repo**, after *every* CLI command. It `rglob`s the
entire project including `.venv` (4 GB here) and `node_modules`, which can
never contain a manifest. On a larger tree or slower disk this becomes a
visible tax on unrelated commands.
**Fix:** prune known-heavy directories during the walk. Note a
`.claudeignore` with exactly these exclusions already exists at the user
level — and `ephemeral_purge` does not read it. Wiring the two together fixes
this correctly rather than hardcoding a second list.

### D-4 · `knowledge_graph` handoff coupling is convention, not enforced — *low*
`knowledge_graph` registers through a conditional `try/except`. A handoff
pointing at it would make `validate()` report a dangling reference in exactly
the degraded state that fallback exists to tolerate. Currently avoided by
convention; **nothing prevents the next contributor adding one.**
**Fix:** mark descriptors as optionally-registered and exempt them from the
handoff existence check, or register `knowledge_graph` unconditionally.

### D-5 · Advisor LOCAL tier is manifest-based, not AST-based — *low*
Detection reads `package.json`, `pyproject.toml`, git config, `manifest.json`.
It does not parse source. Sufficient for tooling advice; the checklist wording
("AST/manifest inspection") claims more than the code does.
**Fix:** either narrow the claim, or add AST-based framework detection for
projects whose manifests under-describe them.

### D-6 · `_pid_alive` fails safe, so some stale locks persist — *low*
Any undeterminable PID counts as alive. Correct default — never delete a lock
whose owner might be running — but it means a lock left by a hard-killed
process on a platform where the check errors is never collected.
**Fix:** none recommended. Documented deliberate tradeoff; note it rather than
"fix" it toward deletion.

### D-7 · Red-team LLM path is exercised only through injected fakes — *low*
The adversarial pass has no test against a real API. Deterministic checks are
fully covered; the LLM branch is covered for parsing and failure handling only.
**Fix:** acceptable as-is. The disclosed-skip warning means a missing key can
never masquerade as coverage.

---

## Reproduction

```bash
python -m pytest tests/ -q          # 2029 passed, 1 skipped
python -m ruff check src/ tests/    # All checks passed!
python -c "import genesis_architect_pro.gde_engine_registration; \
  from genesis_architect_pro.engine_registry import get_default_registry; \
  print(get_default_registry().validate() or 'CLEAN')"
```

## Verdict

The v8 guardrails — deterministic routing, the 13-gate policy table, the
adversarial pre-approval critique, whitelist-only fetching with no execution
path, and delete-nothing-by-default purging — are **implemented, wired into
every mode, and covered by tests that assert refusals rather than
capabilities**. Three of the seven bugs fixed during this arc were found by
running the code against reality (a live clone, the developer's real MCP
config, a real repository's read-only pack files) rather than by the test
suite, which is itself the argument for keeping live verification in the loop.

The one honest deficiency is scope, not quality: **8 of 11 blueprint items
remain unbuilt**, and item 6 is reported PARTIAL accordingly.
