# Genesis Architect - Structural Reference

How the analysis actually works: the graph it builds, the rules it applies to
that graph, the thresholds, and the discriminators that decide whether a
finding is a defect or a false alarm.

This document is about mechanism. For what Genesis produces, see the
[README](README.md).

---

## 1 · The dependency graph

Everything structural derives from one artifact: a directed graph of modules
and the imports between them.

### Extraction

Imports come from the parsed syntax tree, not from a text scan. The practical
consequence is that a module named in a docstring, a comment, or a string
literal is not an edge - a regex-based scanner reports those as dependencies
and inflates every downstream metric.

Five languages, each with its own extractor:

| Language | Detected by | Import forms read |
|---|---|---|
| Python | `pyproject.toml`, `setup.py` | `import x`, `from x import y` (dotted paths kept) |
| TypeScript / JavaScript | `package.json` | `import`, `require` |
| Go | `go.mod` | import blocks |
| Rust | `Cargo.toml` | `use`, `mod` |

For Python, `from app import billing` records the dotted candidate
`app.billing` as well as `app`, because the former is a real submodule edge
when `app/billing.py` exists. The resolver drops the candidate when it maps to
nothing on disk, so the guess costs nothing when wrong.

### What is deliberately not an edge

**`if TYPE_CHECKING:` bodies.** Those imports never execute. Counting them
overstates coupling, and it makes two reasonable goals mutually exclusive: a
module that declares its re-exports so type checkers can see a lazy API would
register that declaration as runtime fan-out.

Two cases inside the same construct *are* walked, because that code runs:

```python
if TYPE_CHECKING:
    from pkg.types_only import Thing      # not an edge
else:
    from pkg.at_runtime import Thing      # edge - else runs

if not TYPE_CHECKING:
    from pkg.also_runs import Other       # edge - negated guard runs
```

> Matching the bare name `TYPE_CHECKING` as the guard would invert the third
> case exactly. The negated form is checked for, not assumed away.

### Cycle detection

Cycles are found with Kahn's algorithm: repeatedly remove nodes with in-degree
zero. Whatever cannot be removed is, by construction, inside a cycle. This is
deterministic and reports the participating members rather than a single edge,
because a cycle has no privileged "cause" to point at.

---

## 2 · The analysis rules

Three structural rules, each with a threshold and - more importantly - a
discriminator that separates the pattern from the defect.

### god-class - fan-out

| | |
|---|---|
| Flags at | `fan_out > 15` |
| Critical at | `fan_out > 30` |
| Reads | outgoing edges |

A module importing many others has taken on many jobs, and a change to any of
them can reach it.

**Discriminator - the standalone script.** A file that nothing imports, living
outside any package, is a script. Its coupling is *terminal*: it cannot cascade
a change to anything, because nothing depends on it. An audit runner, a build
script or a one-off migration reaches across the whole system by design.

Both conditions are required:

```
fan_in == 0          nothing depends on it
not in a package     its directory holds no __init__.py
```

Requiring both is what stops the rule excusing a genuine god module that merely
has no importers *yet*. A module inside a package stays CRITICAL whether
anything imports it or not, and a script gains its verdict back the moment
something imports it. Package membership is derived from the graph itself, so
no directory layout is hardcoded.

### hub-file - fan-in

| | |
|---|---|
| Flags at | `fan_in > 10` |
| Critical at | `fan_in > 20` |
| Reads | incoming edges, excluding tests |

**Discriminator 1 - tests are not coupling.** A test is a leaf. Nothing depends
on it, so a change to the module cannot cascade *through* it to anything else.
Counting test importers meant **adding tests degraded a project's architecture
score**, which is an incentive no analysis tool should create.

Test importers are excluded from the verdict and reported separately, so
excluding them from the judgement does not hide them from the report:

```
metrics: { fan_in, fan_in_including_tests, test_importers, fan_out }
```

**Discriminator 2 - a vocabulary is not a hub.** A module with high fan-in and
*zero* fan-out is a shared type or constant vocabulary. It cannot propagate a
change it never receives. The standard advice - extract the stable interface
into its own module - is incoherent when the module already *is* that
interface; acting on it yields two vocabularies and duplicated definitions.
Reported at LOW, with a fix line that says to leave it alone.

### circular-dep

Every cycle is CRITICAL. There is no threshold, because there is no acceptable
number of import cycles: each one means neither module can be understood,
tested or loaded without the other.

---

## 3 · The engine DAG

Analysis engines are registered as descriptors carrying two different kinds of
edge. Conflating them is the mistake this design exists to prevent.

| Edge | Direction | Meaning | Cycles |
|---|---|---|---|
| `requires` | backward | hard ordering constraint | **must stay acyclic** |
| `handoffs` | forward | "having run, this is useful next" | **legal** |

`requires` is topologically sorted to produce the execution plan, so a cycle
there means no valid order exists and the plan is refused.

`handoffs` is advisory and deliberately exempt from cycle detection. The
shipped registry contains a real handoff loop:

```
recovery_report → refactoring_planner → rules_engine → recovery_report
```

That is `diagnose → plan → enforce → re-diagnose` - an iterative workflow, not
a structural defect. Handoff targets are existence-checked so they cannot rot
into dangling references, and nothing more.

> Nothing traverses `handoffs` at runtime. The runner iterates a pre-computed
> list of phases, so each engine executes at most once per session and a handoff
> loop cannot spin. The day something *does* follow them, the bound belongs at
> the point of traversal.

### The composition root

Registration is owned by one module. Previously it had no owner: whichever
module first noticed the registry was empty triggered it, which meant the
registry imported the thing that fills it, and a descriptor provider imported
its sibling. Three of four import cycles came from that.

```
gde_types                    imports nothing intra-package
    ↑
engine_registry              a container, and only a container
    ↑
gde_engine_registration      providers; they import the registry
gde_knowledge_graph_adapter  to register into it
    ↑
engine_bootstrap             imports the providers, in order
    ↑
decision_engine / CLI        entry points ask for the bootstrap
```

Every arrow points one way. The registry can no longer reach the providers, so
the cycle cannot re-form by someone adding another lazy import - there is now
an obvious place for that code to go instead.

---

## 4 · The gate table

Fourteen gates evaluate a session before any write is approved. Each carries an
action and a confidence penalty.

| Action | Gates | Overridable |
|---|---|---|
| `HARD_BLOCK` | `PLAN_WRITE`, `RULES_FAIL` | **no** |
| `BLOCK_AND_ASK` | `CONFIDENCE_LOW`, `DRIFT_CRITICAL`, `SECURITY_RISK`, `POLICY_VIOLATION`, `COMMIT_CONFLICT`, `RED_TEAM_CRITICAL`, `RESEARCH_COVERAGE_LOW` | yes |
| `WARN` | `WRITE_SCOPE`, `REQUIRED_FAILED`, `DEGRADED_MODE`, `NO_ENGINES`, `RESEARCH_STALE` | yes |

Penalties run 0.05 for warnings to 0.15 for soft blocks, subtracted from the
session's overall confidence.

Several gates scan *every* engine's output for a signal key rather than naming
one engine. `SECURITY_RISK` looks for `security_risk` from any engine, so a new
analysis engine wires into the gate by emitting the key - the gate does not
change.

### Absent is not zero

A metric that was never measured is reported as `None`, never as `0`. Coverage
with no outline to measure against is "not applicable"; a repository with no
star count is unknown, not unpopular. Rules skip on `None` rather than treating
it as a failing value, and the report says *skipped* rather than *passed*.

> "Checked and clean" and "nothing to check" are different results. Only one of
> them is evidence.

---

## 5 · How structural changes are verified

The 9.0.0 refactor moved roughly 2,000 lines across nine new modules. Three
techniques carried that, and they generalise.

### Behavioural oracle before a mechanical move

A snapshot tool walks the argument parser and dumps every subcommand, flag,
`nargs`, default, type, `choices` and help string - 413 lines. Captured from a
worktree at the pre-refactor commit, diffed after every step.

That turns "did the CLI change?" from a hope into a fact. It stayed
byte-identical through all six steps of the split.

### Static undefined-name checking after every move

`ruff --select F821` ran after each extraction. It caught **three defects the
full 2,845-test suite passed straight over**, because they sat on uncovered
error paths: a relocated module lost its `sys` import, and a formatter lost
`Path`. Tests alone are not sufficient for relocations.

### Conserved lint debt as evidence

Before the CLI split: 19 `I001` findings. After: 19. None introduced.

The relocated function-local import blocks carried their own pre-existing
formatting debt along unchanged. That equality is the cheapest available
evidence that the moves were faithful rather than rewritten - a genuine
rewrite would almost certainly have changed the count in one direction.

---

## 6 · Genesis measured against itself

Every number below is produced by the rules above, run against this repository.

| | before 9.0.0 | after |
|---|---|---|
| Import cycles | 4 | **0** |
| Critical anti-patterns | 7 | **0** |
| Unpinned CI actions | 21 | **0** |
| Largest module fan-out | 31 | **9** |
| Largest module, lines | 1,974 | 390 |
| Architecture score | 67 | **89** |
| Tests | 2,337 | **2,845** |

The CLI package after the split, against a self-imposed ceiling of 11:

| Module | fan-out | lines |
|---|---|---|
| `commands/parser.py` | 0 | 246 |
| `commands/formatting.py` | 1 | 335 |
| `commands/voice_setup.py` | 3 | 217 |
| `commands/session_cmds.py` | 4 | 259 |
| `commands/project_cmds.py` | 7 | 268 |
| `commands/analysis_cmds.py` | 7 | 232 |
| `commands/router.py` | 8 | 154 |
| `commands/companion_cmds.py` | 8 | 350 |
| `commands/companion_backend.py` | 9 | 112 |
| `gde_cli.py` (compatibility shim) | 1 | 132 |

> The ceiling is 11 against a rule that flags at 15. A module sitting exactly on
> a threshold is a latent breach, not a pass - the next feature tips it over.

`companion_backend.py` exists because relocation alone could not get the
companion family under the ceiling: it measured 14, and every pure-move seam
landed at 11 or 12. The cause was real duplication - `--serve` and `--ui`
brought the backend up with the same seven imports and the same seven steps in
the same order. Two copies of a startup sequence is a live bug risk on its own,
since a fix to one can miss the other.

Their *teardowns* genuinely differ, and that asymmetry was preserved rather
than tidied away. Unifying it would have been a behaviour change wearing the
costume of a refactor.

---

## 7 · Function-level mechanisms

Sections 1 to 6 describe what the system guarantees. This section describes
how four of those guarantees are implemented, and where each one stops. Every
limit below is a real property of the code, not a caveat added for modesty.

### Static and dynamic imports

`core/import_graph.py` - `_extract_python_imports`, `_runtime_nodes`

An edge exists when the syntax tree contains an `ast.Import` or
`ast.ImportFrom` node that runs. Two words in that sentence carry weight.

**Contains.** Nesting depth is irrelevant. `_runtime_nodes` recurses through
every child node, so an import inside a function body, a `try:` block, or a
class definition is an edge exactly like a top-of-file one. Deferring an
import to break a cycle at *startup* does not hide it from the graph, which is
the point: the coupling is still there.

**Runs.** The one construct excluded is the body of `if TYPE_CHECKING:`, for
the reasons in section 1. The `else:` branch and `if not TYPE_CHECKING:` are
both walked.

What is not an edge, and cannot be:

```python
importlib.import_module(name)      # invisible
__import__("app." + suffix)        # invisible
entry_point.load()                 # invisible
```

A module named only by a runtime string is not a dependency the tool can
verify. Resolving it would mean executing the code or guessing at string
values, and a graph built on guesses is worse than one with a documented
floor. Genesis reports what it can prove.

Two further behaviours worth knowing:

- Files are read as `utf-8-sig`. With plain `utf-8` a byte-order mark, which
  Windows editors add freely, reaches `ast.parse` as `U+FEFF` and the entire
  file is discarded as a syntax error, silently.
- A file that raises `OSError` or `SyntaxError` yields no imports. It remains
  a node and other modules still point at it, so its fan-in is intact, but its
  fan-out reads zero and it looks like a leaf. A repository that fails to
  parse therefore looks *cleaner* than one that parses. Treat a parse failure
  as a broken measurement, never as a good score.

### Cycle detection, and what the reported set means

`pro/engine_registry.py` - `_detect_cycles`

Kahn's algorithm, with edges running dependency to dependant: the direction a
topological sort consumes, since an engine becomes runnable once everything it
`requires` has been emitted. Seed the queue with every zero-in-degree node,
pop, decrement each dependant, enqueue on reaching zero. `O(V + E)`, and
deterministic given a stable descriptor order.

Three constraints shape it:

1. **Only `requires` edges count.** `handoffs` are forward hints about what
   tends to run next, and they are permitted to cycle. Two engines that hand
   off to each other describe an iterative loop, which is a legal workflow.
   Feeding them to the same acyclicity check would make that unrepresentable.
2. **A requirement naming an unregistered engine is skipped**, not treated as
   an edge. It is a genuine error, reported separately by the caller. Counting
   it here would surface a missing dependency as a phantom cycle and send the
   reader hunting for a loop that does not exist.
3. **The reported set is the blocked set, not the cycle.** If `visited` falls
   short, every node with residual in-degree is named. That includes engines
   downstream of a cycle, which never reach zero either. The set is a superset
   of the cycle, deliberately: a cycle has no privileged member to blame, and
   over-reporting is recoverable where a confidently wrong single edge is not.

### Lazy attribute resolution

`pro/__init__.py` - `__getattr__`, `__dir__`

The package exports over two hundred names from dozens of modules. Importing
them eagerly makes `import genesis_architect.pro` pay for the entire surface
no matter which single command the user ran. PEP 562 defers that cost.

Resolution order for `genesis_architect.pro.X`:

1. Ordinary attribute lookup on the module's `globals()`. Python calls
   `__getattr__` **only on a miss**, so anything already imported or already
   resolved never reaches the hook.
2. `_LAZY_EXPORTS[X]` gives the defining module path. A miss raises
   `AttributeError` with the standard message, so `hasattr` and
   `getattr(..., default)` behave normally.
3. `_LAZY_ALIASES[X]` is consulted, because five names are re-exported under a
   name their defining module does not use. Looking up the exported name on
   that module would raise for those five.
4. The resolved object is written into `globals()`. Step 1 catches it forever
   after, so the hook runs at most once per name.

Three consequences that are easy to get wrong:

- `from genesis_architect.pro import X` works unchanged: the import machinery
  falls back to `getattr` on the module, which is the hook.
- `dir()` and tab-completion would otherwise show only what happened to be
  resolved already, so `__dir__` unions `globals()` with `_LAZY_EXPORTS`.
- Step 4 is a cache, and `importlib.reload` does not clear it. A reloaded
  submodule leaves the stale object bound in the parent. `_clear_lazy_cache()`
  exists for exactly that case, and the tests use it.

The `if TYPE_CHECKING:` block restates the same names as real imports. Type
checkers, IDEs and CodeQL read it, the runtime never executes it, and by
section 1 it is not a dependency edge, so declaring the API costs no fan-out.

### Host matching

`core/urls.py` - `host_of`, `host_matches`

Genesis weights research by source, and that weight is a security boundary:
whoever controls a URL in a search result controls part of the input. The
substring test this replaced accepted both of these as `reddit.com`:

```
https://evil.example/reddit.com/thread     in the path, not the host
https://reddit.com.attacker.example/x      a prefix of a different domain
```

`host_of` parses instead. A scheme-less input is prefixed with `//` so
`urlparse` treats it as a host rather than a path; the hostname is lowercased;
a leading `www.` is stripped; and `ValueError`, which `urlparse` raises on
malformed IPv6 literals among other things, returns `""`. A `[a-z0-9.-]+`
check rejects anything that is not a hostname at all, without which `urlparse`
reports `not a url` as the host of `//not a url`.

`host_matches` then accepts a host that either equals a domain or ends with
`"." + domain`. The dot is what defeats the second attack: a plain
`endswith("reddit.com")` also matches `notreddit.com`. Every failure path
returns `False`, so malformed input degrades to "no match" rather than to a
trusted one.

---

## 8 · Reproducing any of this

```bash
# Structure of your own project
genesis recover .

# The same graph Genesis uses on itself
python -c "from genesis_architect.core.import_graph import build_graph; \
           g = build_graph('.'); \
           print(g['cycle_count'], 'cycles across', g['module_count'], 'modules')"

# Full suite plus end-to-end CLI checks against a real install
docker build -f Dockerfile.test -t genesis-test . && docker run --rm genesis-test
```

Nothing in this document is asserted rather than measured. If a number here
disagrees with what the tool reports on your machine, the tool is right.
