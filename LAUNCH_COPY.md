# Launch Copy - Genesis Architect

Ready-to-post text for each platform. Use after you have a real demo GIF.

---

## Hacker News - Show HN

**Title (max 80 chars):**
```
Show HN: Genesis Architect - scaffolder that mines GitHub Issues before writing code
```

**First comment (post immediately after submission):**
```
Hi HN,

I built Genesis Architect, a Claude Code skill that does something before
scaffolding a project that I haven't seen other tools do: it researches
what actually broke in production.

Before writing a single file, it:
1. Scans 15-20 real GitHub repos matching your vision
2. Mines up to 100 Issues per repo, ranked by comments + reactions
3. Extracts recurring failures, security patches, architecture regrets
4. Builds your scaffold specifically to avoid those mistakes
5. Validates every cited issue URL - a 404 fails the build

The result is a PITFALLS.md with real root causes (like click#2416,
tqdm#1139) and a codebase that already knows about the mistakes that
took other teams weeks to find.

After scaffolding it stays active: `genesis resolve "path traversal python"`
checks a local vault first (instant, free), then falls back to Stack Overflow.

It ships with: 4 parallel CI jobs (secret scanning, SAST, quality gate),
non-root Dockerfile, env validation, and a working test suite on day one.

Repo: https://github.com/maioio/genesis-architect
Works with Claude Code, Cursor, Codex. No API key needed.

Happy to answer questions about the architecture or the research approach.
```

**When to post:** Tuesday or Wednesday, 9-11am ET. Avoid Mondays and Fridays.

---

## Reddit - r/ClaudeAI

**Title:**
```
I built a Claude Code skill that reads GitHub Issues before scaffolding your project
```

**Body:**
```
Most scaffolding tools generate from templates. They have no idea what broke
in production for the 50,000 developers who built the same thing before you.

I built Genesis Architect to fix that.

Before writing a single file, it:
- Scans 15-20 real GitHub repos matching your vision
- Mines Issues ranked by comments + reactions (what actually hurt people)
- Builds your scaffold to avoid those specific failures
- Validates every cited URL (a 404 fails the CI build)

Example from a Python CLI project it scaffolded:
- click#2416: business logic inside Click callback = untestable
- click#2558: type annotation conflicts break mypy in Click 8.1+
- typer#522: no input validation = cryptic tracebacks as error messages

The output includes a PITFALLS.md with root causes and mitigations already
built into the scaffold.

After scaffolding it stays active as a "genesis resolve" command that checks
a local vault first (instant, free), then Stack Overflow.

GitHub: https://github.com/maioio/genesis-architect

Works with Claude Code (one git clone, no setup). Also works with Cursor
and Codex by copying SKILL.md to the right folder.

Happy to answer questions!
```

---

## Reddit - r/programming (only after you have a demo GIF)

**Title:**
```
My scaffolding tool reads GitHub Issues to find what broke in production before creating a single file
```

**Body:** Same as r/ClaudeAI but open with the GIF as the first thing.

---

## Reddit - r/webdev

**Title:**
```
Built a tool that researches GitHub Issues for production failures before scaffolding your TypeScript project
```

**Focus on:** TypeScript CLI and Web Service archetypes specifically.
Lead with the `examples/typescript-cli/PITFALLS.md` findings.

---

## X/Twitter thread

**Tweet 1 (hook):**
```
Most scaffolding tools generate from templates.

They have no idea what broke in production for the 50,000 devs
who built the same thing before you.

I built something different. Thread:
```

**Tweet 2:**
```
Before Genesis Architect writes a single file, it:

1. Scans 15-20 real GitHub repos
2. Mines up to 100 Issues per repo
3. Ranks by comments + reactions (what actually hurt people)
4. Extracts recurring failures and security patches
5. Validates every cited URL - a 404 fails the build
```

**Tweet 3 (concrete example):**
```
Real example from a Python CLI it scaffolded:

- click#2416: logic in Click callback = untestable code
- click#2558: type annotations break mypy in Click 8.1+
- typer#522: no input validation = cryptic tracebacks

These are in PITFALLS.md with mitigations built into the scaffold.
Not theoretical. From real production Issues.
```

**Tweet 4 (features):**
```
It also ships with:

- 4 parallel CI jobs (secret scanning, SAST, quality gate, tests)
- Non-root Dockerfile + env validation
- "genesis resolve" with local vault (instant, no API call)
- Works with Claude Code, Cursor, Codex

MIT, no API key needed.
```

**Tweet 5 (CTA):**
```
https://github.com/maioio/genesis-architect

If this is useful, a star helps others find it.
Feedback welcome - especially from people who've been burned
by scaffolding that didn't age well.
```

---

## Discord - Anthropic Claude / AI Engineer communities

**Short version (for #tools or #showcase channels):**
```
Shipped: Genesis Architect - a Claude Code skill that researches GitHub
Issues before scaffolding your project.

Instead of templates, it scans 15-20 real repos, mines Issues ranked by
comments+reactions, and builds your scaffold to avoid what actually broke
in production. Every cited issue URL is HTTP-verified in CI.

https://github.com/maioio/genesis-architect

Works with Claude Code (one git clone). Also Cursor/Codex.
93 tests, MIT.
```

---

## Timing strategy

| Platform | Best time | Expected |
|----------|-----------|----------|
| HN Show HN | Tue/Wed 9-11am ET | 5-50 points, 500-5000 views if front page |
| r/ClaudeAI | Weekday morning | 50-200 upvotes |
| r/programming | Only with GIF | Unpredictable |
| X/Twitter | Tue-Thu, any time | Depends on followers |
| Discord | Anytime | 10-50 direct clicks |

**Critical:** Post HN and Reddit on different days. HN traffic is highest
value but shortest window. Reddit compounds over 24-48h.

---

## What increases chances of going viral

1. **Demo GIF** - the single biggest unlock. Record with DEMO_SCRIPT.md.
2. **Concrete numbers** - "mines 100 Issues per repo" beats "researches repos"
3. **Specific examples** - click#2416 beats "common CLI pitfalls"
4. **Respond to every comment** in the first 2 hours of HN/Reddit post
5. **Cross-post to nitayk** - ask him to upvote/comment, he's clearly engaged
