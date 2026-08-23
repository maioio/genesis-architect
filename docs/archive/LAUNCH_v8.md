# Launch material for v8.0.1

Every number here is verified. Sources: `docker/capability_audit.py` (62 checks),
the test suite (2358), and the v8.0.1 release notes. If a claim is not in one of
those, it does not go in a post.

**The angle.** Not "17 engines, 30 sources". A feature list reads as marketing
and gets ignored. The story developers actually respond to is the one that is
also true: *a tool whose job is telling you the truth about your code shipped
while overstating its own results, a user caught it in an afternoon, and here is
the fix plus a re-runnable audit.* Lead with that. It is unusual, it is
verifiable, and it demonstrates the product's value proposition on the product
itself.

**What to avoid.** Do not post the capability matrix. Do not say "everything
works perfectly" — the audit says 57 working, 5 environment-limited, 0 broken,
and that precision is the point. Do not bury the licence change; AGPL is the
first question a commenter will ask.

---

## Hacker News — Show HN

Post Tuesday to Thursday, 09:00–11:00 ET. Title (80 char limit):

```
Show HN: Genesis Architect – mines GitHub issues to find bugs before you write code
```

First comment, posted by you immediately after:

> I built this over the past months. It scans repositories solving the problem
> you described, mines their closed issues for failures that keep recurring, and
> generates a scaffold with those mitigations already in place. Afterwards it
> stays: scoring architecture, detecting drift, and flagging modules too fragile
> to touch.
>
> It used to be open-core with a $9/mo Pro tier. I never got it in front of
> enough people for that to mean anything, and the licence check was mostly
> creating work for me. As of v8.0.0 everything is free under AGPL-3.0 — the
> decision engine, knowledge graph, threat modelling, voice companion, all of it
> in one package.
>
> The part worth talking about: I shipped 8.0.0, someone ran it on a real
> project, and reported four bugs the same day. Three were the tool overstating
> its own results, which for a diagnostic tool is the worst possible failure
> mode:
>
> - An empty project scored a perfect 100/100. Every dimension is "100 minus
>   penalties", so a directory with nothing to analyse collects no penalties. A
>   mistyped --dir got you a clean bill of health.
> - The five-advisor "Committee" reported 100% confidence without running. It
>   needs an LLM key; without one it silently aggregated engine perspectives and
>   printed that under a Committee heading. The fallback confidence started at
>   1.0 and only dropped when advisors disagreed — and on an empty project
>   nothing disagrees.
> - A long project description crashed `genesis init` with a bare HTTP 422.
>   GitHub caps search queries at 256 chars. The advice on an empty result made
>   it worse: "try a more specific vision", when over-specificity causes it.
>
> All fixed in 8.0.1. I also wrote a capability audit that runs one check per
> claim on the website against the published package rather than the source
> tree: 57 working, 5 needing a device/key/network, 0 broken. It is in the repo
> so the claim is re-runnable rather than asserted.
>
> Two earlier bugs are worth mentioning because they only appear when you test
> the packaged install: the scaffolder read a data file by walking up to the
> repo root, which does not exist in a wheel and happens at import time, so
> `pip install` shipped a version where `genesis init` could not import. And the
> test suite was running a real `pip install` mid-run, mutating its own
> environment and making results depend on execution order.
>
> AGPL because I would rather someone not wrap it as a paid SaaS without
> publishing changes. For running it on your own code it behaves like GPL.
>
> Happy to answer anything.

Then stay in the thread for several hours. Answering every comment matters more
than the post.

**Prepared answers for the obvious questions:**

*Why AGPL and not MIT?* — Honest version: it stops someone reselling it as a
hosted service without contributing back, and for a locally-run CLI the network
clause essentially never triggers. Acknowledge the real cost: some companies
blanket-ban AGPL dependencies, and that will cost adoption.

*Is this just an LLM wrapper?* — No, and be specific: routing between the seven
modes is deterministic with no LLM in the path; the import graph, architecture
scoring, anti-pattern detection, fragility classification, C4 generation and
secrets scanning are all static analysis. The LLM is used for scaffold
generation and the advisor debate, and the tool now says so when it is absent.

*Does it work on my language?* — Import graph and analysis: Python, TypeScript,
JavaScript, Go, Rust. Scaffolding: those four. Be direct about the boundary.

*How is this different from Sonar/CodeQL?* — They analyse the code you have.
This reads what broke for *other people building the same thing*, before you
have code. Different input, different moment.

---

## Reddit

Rewrite for each. Never cross-post the same text; it is the fastest way to get
removed. Space them out by days.

**r/Python** — post in the Saturday Showcase thread. Lead with the packaging
bug, since that audience will recognise it immediately:

> I shipped a package where `pip install` produced a broken CLI, and the tests
> did not catch it because they ran from the repo. The scaffolder loaded a data
> file with `Path(__file__).parent.parent.parent.parent / "references" / ...`,
> which resolves fine in a checkout and does not exist in a wheel — and it
> happened at import time, so the module was unimportable. Now shipped as
> package data, with a CI job that installs the built wheel into a clean
> container and fails if a required data file is missing.
>
> The tool itself is Genesis Architect: it mines closed GitHub issues from
> similar projects and scaffolds with those failures mitigated. Just went fully
> free/AGPL. [link]

**r/programming** — lead with the false-green story. It is the most interesting
one and generalises beyond this tool.

**r/opensource** — lead with the open-core-to-free transition and what it cost:
zero paying customers, a licence system that was more work than it was worth,
and the leftover `license_tier` check still withholding output from free users
that only turned up while fixing something else.

---

## X / Twitter

One thread, six posts. No hashtags.

1. I shipped a code-analysis tool. A user ran it on a real project and found
   four bugs in an afternoon. Three were the tool overstating its own results —
   the worst failure mode a diagnostic tool has. Here is what broke.
2. An empty project scored a perfect 100/100. Every dimension is "100 minus
   penalties", so a directory with nothing in it collects no penalties. A
   mistyped path got you a clean bill of health.
3. The five-advisor debate reported 100% confidence without running. It needs an
   LLM key; without one it quietly aggregated something else and printed it
   under the same heading. Confidence started at 1.0 and only fell when advisors
   disagreed — with nothing analysed, nothing disagrees.
4. A long project description crashed it with a raw HTTP 422. GitHub caps search
   queries at 256 characters. The error advice said "try a more specific
   description", which is exactly backwards.
5. All fixed. I also wrote an audit that runs one check per claim on the site,
   against the published package rather than the source tree: 57 working, 5
   needing a device or key, 0 broken. In the repo, so you can re-run it.
6. Genesis Architect mines closed issues from projects like yours and scaffolds
   with those failures already mitigated. Everything that used to be paid is now
   free under AGPL-3.0. [link]

---

## Before posting

- [ ] Rotate the API key that appeared in a screenshot.
- [ ] Unpublish the two Gumroad products (see `GUMROAD_RETIREMENT.md`).
- [ ] Archive `maioio/genesis-architect-pro`, pointing at this repo.
- [ ] Confirm <https://maioio.github.io/genesis-architect/> shows no pricing.
- [ ] `pip install genesis-architect` in a clean container returns 8.0.1.
