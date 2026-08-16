# Dry-Run Interview method: templates, rationale, worked examples

Companion to the compact rules in `SKILL.md` (Evidence Discipline, Phase 1's
question contract, Phase 4's landmine sweep). SKILL.md carries what governs
every run; this file carries what a session consults for calibration or a
concrete template to fill in.

## The turn template

Every question turn takes this shape. Copy it, fill the brackets.

```
Locked: [what is settled] | Open forks: [n] | Q[k]/8
[1-2 sentences naming the fork, citing any source]
Q[k]. [one specific question]
Recommended: [concrete answer] - [one-line basis].
```

Worked example, from a real fork:

```
Locked: goal, v1 scope | Open forks: 2 | Q3/8
The repo already streams CSV exports through src/export/writer.py
(verified: read that file), so extending it beats a parallel path. One thing
forks the design: soft-deleted rows.
Q3. Should exports include soft-deleted records, or exclude them?
Recommended: exclude - the existing export excludes them (verified:
src/export/writer.py) and nothing in the ask suggests audit use.
```

## Evidence Discipline: the full rationale

Every sentence that states a fact carries exactly one of three statuses:
`(user)`, `(verified: source)`, or `[assumed: default X - if wrong: Y]`.
There is no fourth. The reasoning behind each rule:

**Training data is never a valid source.** A version number, an API shape, a
CLI flag or a config key known only from model memory is `[assumed]`, never
`(verified)`. `(verified)` requires a concrete artifact from this session -
a tool call, a command, a file read, a URL fetched - that could be shown to
the user. This is the rule that actually separates a researched architecture
from one that merely sounds confident, which is the entire value
proposition the tool is selling.

**Versions come from a lockfile, a registry API, or a live check, never from
memory.** Phase 2 already queries PyPI, npm and crates.io for velocity
scoring; those same responses are the source, not a second lookup.

**A default is not an invention.** Torn between stating an unverified fact
and spending one of the 8 questions, do neither: adopt a default, tag it,
add an Assumptions Ledger row. A guess written as `[assumed: ... - if
wrong: ...]` is a disclosed decision; the same guess stated as fact is a
defect on the same order as an issue URL that 404s.

**The provenance scan, before Phase 6.** Read back every factual sentence in
RESEARCH.md, PITFALLS.md, and ROADMAP.md. An untagged claim is either
verified now or downgraded to `[assumed]`. A `(verified)` tag whose actual
source is "general knowledge" is downgraded too - the tag has to name a real
artifact or it doesn't count.

## Landmine sweep: the worked example

**A detonated landmine must visibly change the architecture, not earn a
sentence in the docs.** Concretely: "the factory floor has no internet" does
not become a deployment note. It flips the design to local-first with
periodic sync, moves storage on-device, changes which dependencies are
allowed (nothing that phones home to check a license), and adds an offline
smoke test to the Build Phases. Re-run Phase 3 synthesis from the top when a
landmine like this fires - patching one section while the rest of the
architecture still assumes connectivity produces a document that
contradicts itself.

## Where this comes from

This is a distilled excerpt of a separate, general-purpose planning method
("The Dry-Run Interview") - the same discipline, applied outside Genesis to
any software task, not only architecture builds. What's folded in here is
the subset that applies inside a Genesis build specifically; the full
method (all ten task tracks, the Critique Engine) is out of scope for this
project's own `SKILL.md` and lives wherever that separate method is
installed for a given operator, not as part of this repository.
