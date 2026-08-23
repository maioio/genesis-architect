# Website Copy - v9.0.0

Copy blocks for the landing page (`genesis-react`), structured for direct
lifting into components. Dark-mode first.

**Voice rules for anything added later:** declarative, specific, no superlatives
Genesis has not earned. Every number on the page is measured and reproducible by
a visitor running one command. If a claim cannot survive `genesis recover .` on
our own repo, it does not ship.

---

## 1 · Hero

**Headline**

> ### Research before you build.

**Alternate headlines**, if the page needs a structural angle rather than a
research one:

> ### The architecture tool that audited itself.
> ### Most projects fail by repeating a solved mistake.

**Subheadline**

> Genesis reads the repositories that already solved your problem - their closed
> issues, their forks, their post-mortems - and scaffolds a project with those
> failures already mitigated. Then it stays, and tells you which modules have
> become too fragile to touch.

**Primary CTA:** `pip install genesis-architect` (click-to-copy)
**Secondary CTA:** View on GitHub

**Trust strip** - render as small monospace chips under the fold line:

```
AGPL-3.0   ·   Python 3.11+   ·   2,845 tests   ·   0 import cycles   ·   no telemetry by default
```

---

## 2 · The proof section

Place immediately below the hero. This is the strongest thing on the page: it
is the only claim a competitor cannot copy without doing the work.

**Eyebrow:** `v9.0.0 - The Architecture Milestone`

**Headline**

> ### We pointed it at ourselves. It failed.

**Body**

> The obvious question about a tool that grades architecture is whether it would
> survive its own grading. In 9.0.0 we ran it against its own source. It found
> four import cycles, seven critical anti-patterns, a 1,974-line CLI module
> importing 31 others, and 21 CI actions pinned to tags their owners could move
> at any time.
>
> All of it is now zero.

**Metric row** - four tiles, before → after:

| Label | Before | After |
|---|---|---|
| Import cycles | 4 | 0 |
| Critical anti-patterns | 7 | 0 |
| Unpinned CI actions | 21 | 0 |
| Architecture score | 67 | 89 |

**Footnote, small type**

> Three of the rules that produced those findings turned out to be wrong, and
> fixing them shipped in the same release. Scores may move on 9.0.0. That is the
> correction landing, not a regression.

---

## 3 · Under the hood

**Headline**

> ### Four mechanisms, each because the obvious alternative was measurably wrong.

Render as four cards. Title, one-line claim, then the mechanism.

```jsx
const mechanisms = [
  {
    title: "Graphs from the AST, not from text",
    claim: "A module named in a comment is not a dependency.",
    body:
      "Imports are read by walking the parsed syntax tree. A regex scanner " +
      "reports docstrings and string literals as edges and inflates every " +
      "metric downstream. Five languages: Python, TypeScript, JavaScript, Go, Rust.",
  },
  {
    title: "TYPE_CHECKING is not a dependency",
    claim: "Imports that never execute are not coupling.",
    body:
      "Imports under `if TYPE_CHECKING:` are pruned - they never run. The " +
      "`else:` branch and `if not TYPE_CHECKING:` are kept, because that code " +
      "does. Matching the bare name as the guard would invert the second case exactly.",
  },
  {
    title: "Discriminators, not just thresholds",
    claim: "A shared vocabulary is not a hub. A script is not a god class.",
    body:
      "High fan-in with zero fan-out is a type vocabulary: it cannot propagate " +
      "a change it never receives. A file nothing imports, outside any package, " +
      "is a script: its coupling is terminal. Both are reported, neither is a defect.",
  },
  {
    title: "Test files are not coupling",
    claim: "Adding tests must never lower your score.",
    body:
      "A test is a leaf - nothing depends on it, so a change cannot cascade " +
      "through it. Counting test importers created an incentive to delete tests. " +
      "They are excluded from the verdict and reported separately.",
  },
];
```

**Section footer**

> Every claim above is measured in CI, not asserted on a marketing page.
> `genesis recover .` reports the same numbers about your project.

---

## 4 · What it produces

Keep the README's worked example verbatim - real issue URLs, the generated
tree, the "every cited URL is checked by CI; a 404 fails the build" line. It is
the most persuasive block we have and it should not be paraphrased into
something softer for the web.

Render the pitfall table as-is. Do not truncate the issue links: the fact that
they are real, clickable, and CI-verified *is* the argument.

---

## 5 · Everything is free

> ⚠️ **Replaces the old "Pro vs Core" section.** There is no paid tier. Genesis
> was open-core until v8.0.0 - a free package plus a license-gated
> `genesis-architect-pro`. That tier is retired. Any page still showing a
> pricing table, a "Pro" badge, or an upgrade CTA is stale and should be
> removed, not restyled.

**Headline**

> ### There is no paid tier.

**Body**

> Genesis used to be open-core. As of v8.0.0 every engine that was behind the
> paywall ships in the package under AGPL-3.0: the decision engine, the
> knowledge graph, threat modelling, C4 diagrams, the voice companion,
> video-to-pitfall extraction. No key, no account, no telemetry by default.

**If the page needs a structural distinction**, this is the honest one - two
namespaces in one free package, not two products:

| | |
|---|---|
| `genesis_architect.core` | Research, scaffolding, the import graph, the base analysis rules. The primitives. |
| `genesis_architect.pro` | The intelligence layer built on them: decision engine, knowledge graph, threat modelling, companion. Named `pro` for historical reasons only. |

---

## 6 · Install

```bash
pip install genesis-architect
```

> That is the whole install. Optional extras add voice and the streaming
> Companion UI: `pip install "genesis-architect[all]"`.

**Three commands, as tabs or a terminal component:**

```bash
genesis init a Python CLI for analyzing log files   # research, then scaffold
genesis recover .                                   # drift, cycles, fragility
genesis harden .                                    # STRIDE, OWASP, secrets
```

---

## 7 · When not to use it

Keep this section. Naming where the tool is a bad fit buys more credibility
than another feature tile.

> Genesis is overkill for a throwaway script, a one-off utility, or anything
> under 100 lines you will delete next week. It earns its keep on projects you
> intend to maintain, anything touching auth, file I/O or external APIs, and
> libraries other people will depend on.

---

## 8 · Footer

```
AGPL-3.0-or-later · © 2026 Maio Eshet
Use, modify and redistribute freely, including commercially. The one obligation:
if you modify it and offer it to others over a network, publish your modified
source under the same license. Running it on your own code changes nothing.
```

---

## Numbers to update at each release

Single source of truth for the page. All are reproducible from the repo.

| Token | v9.0.0 | Source |
|---|---|---|
| `TESTS` | 2,845 | `pytest --co -q` |
| `CYCLES` | 0 | `build_graph('.')['cycle_count']` |
| `CRITICALS` | 0 | `detect_all('.').critical_count` |
| `SCORE` | 89 | `score_project('.')['total']` |
| `ENGINES` | 19 | `get_default_registry()` |
| `PY_MIN` | 3.11 | `pyproject.toml` |

> If any of these drift from the page, the page is wrong. Wire them to the
> release checklist rather than editing by hand.
