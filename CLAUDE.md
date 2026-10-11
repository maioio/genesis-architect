@AGENTS.md

# Claude Code notes

Repository guidance lives in [AGENTS.md](AGENTS.md) and applies to Claude as to any agent. This
file adds only what is specific to Claude Code. [SKILL.md](SKILL.md) is the runtime workflow
Claude follows when Genesis is invoked as a skill (`genesis init ...`); it is a product
artifact, not a contributor guide, and it is edited only for workflow changes.

## Editing SKILL.md

- Keep it under 480 lines. Check with `wc -l SKILL.md`.
- Respond to the user in their language; code, filenames and comments stay in English.
- No em dashes or en dashes.
- The phase structure (Phases 0-7) is part of the product contract. Phase 0 always runs, even when
  `genesis init` skips Phase 1 questions. A change to the phase structure is a major-version
  change (see [docs/reference/versioning.md](docs/reference/versioning.md)).
- `genesis init` goes straight to research. The Phase 5 research summary and the A/B architecture
  choice are one combined message.
- Any `SKILL.md` change needs a [CHANGELOG.md](CHANGELOG.md) entry.

## Claude Code hooks in this repo

`.claude/hooks/protect_files.py` blocks edits to `.env*`, `.git/` and lockfiles. `.claude/hooks/format_file.py`
formats edited files. `.claude/skills/` holds repo-local skills (`fix-issue`, `repo-polish`).
Do not work around a hook block; change the approach.

## Working agreement

- Run the commands in AGENTS.md before declaring a change done, and report what you ran.
- Stage files by name. Never stage `FRAGILITY_MAP.md` from the repo root.
- Commits end with the `Co-Authored-By` trailer configured for the session.
- Pushing, merging, tagging, publishing and repository settings are owner actions: prepare, show
  the exact command, and ask.
