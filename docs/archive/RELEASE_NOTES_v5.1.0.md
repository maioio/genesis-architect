# Genesis Architect v5.1.0

**Released:** 2026-05-30

## Genesis V5.1 - Development Partner Mode

Genesis no longer generates code at you. It partners with you.

### The problem this solves

Previous versions of Genesis were smart about research but silent about decisions. It would find real production pitfalls, synthesize the wise average of 15-20 repos, then quietly choose Minimalist or Scalable and start building. The research was excellent. The decision handoff was not.

V5.1 changes that. Before any decision that affects your product, architecture, or direction, Genesis presents options, explains the tradeoff, recommends a default, and waits for your input.

### What changed

**Experience Selection** replaces the old "Quick Scaffold vs Full Genesis" choice:

| Mode | Research | Questions | For |
|------|----------|-----------|-----|
| A: Fast Build | 5 min cap, 10 repos | 3-5 | Hackathon, experiment, personal tool |
| B: Professional [default] | Full, no cap | 5-10 | Serious project, maintained codebase |
| C: Founder | Full + commercial | 10-20 | SaaS, startup, product strategy |
| D: Auto | Inferred | Varies | Let Genesis decide and explain |

**Development Partner Rules** define exactly when Genesis asks vs. decides:

Genesis MUST present options before:
- Architecture selection (Minimalist vs Scalable, monolith vs multi-service, local vs cloud)
- MVP scope (what is in, what is explicitly out)
- Technology selection (when multiple viable options exist with real tradeoffs)
- Product direction (target user definition, pivots, market positioning)
- Business decisions (monetization, open-source vs commercial, pricing)

Genesis decides alone on:
- File names and folder structure details
- Formatting, linting, and convention choices
- Small implementation details
- Internal refactors

**Standard question format:**

```
[Decision context]

A: [Option]   B: [Option]   C: [Option] [Recommended]   D: [Option]

Why C: [one sentence explanation]
Risk if you choose differently: [one sentence]
Press Enter to accept C, or type A/B/D.
```

The key design rule: **fewer, better-timed questions**. Success is measured by better decisions and less rework - not by asking more questions.

### What stays the same

Everything from V4:
- Phase 2 GitHub Issue mining (15-20 repos, up to 100 issues each)
- Implementation Extraction (every pitfall becomes a real file, test, and constraint - not a document)
- 9-step Genesis Build with hard smoke-test gate
- Phase 7 Companion Mode (genesis check, resolve, research, help)
- 386 passing tests, ruff clean, no em dashes

### New command

```bash
genesis init --partner a SaaS billing system
```

Forces Professional mode with Development Partner Rules active from the first message.

### Tests

386 total (372 existing + 14 new in `tests/test_partner_mode.py`).

New tests verify:
- A/B/C/D format present in Experience Selection
- Recommended marker exists
- Major decisions list (5 categories) is in SKILL.md
- Excluded decisions list is in SKILL.md
- Question format has Why, Risk, and Enter-to-accept fields
- Partner rules persist into Phase 7
- SKILL.md stays under 400 lines
- No em dashes in SKILL.md

### Upgrade

```bash
git pull origin main
pip install -e . --upgrade
```

No configuration changes needed. Existing projects continue with companion mode as before.
The Experience Selection question only appears on new `genesis init` invocations triggered by natural language.

---

V5.2 (Product Discovery - "Should I build this?") requires a Design Review before implementation begins.
