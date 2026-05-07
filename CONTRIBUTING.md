# Contributing to Genesis Architect

Thank you for helping improve Genesis Architect.

## What to contribute

- **New language templates** — Go and Rust are already implemented; add boilerplate for Java, C#, Swift, or other languages in `references/architecture-patterns.md`
- **Better MCP strategies** — improve tool usage in `references/mcp-strategy.md`
- **Workflow improvements** — refine phases in `SKILL.md`
- **Bug reports** — open an issue with the template

## How to contribute

1. Fork the repository
2. Create a branch: `git checkout -b improve/rust-templates`
3. Make your changes
4. Open a pull request with a clear description

## Editing the skill

The skill is plain Markdown — no build step required.

- `SKILL.md` — main skill logic and phase definitions
- `references/architecture-patterns.md` — language boilerplate templates
- `references/mcp-strategy.md` — MCP tool strategy and fallback logic

## Testing changes

After editing, test by invoking the skill in Claude Code:

```
genesis init a simple CLI tool in [your language]
```

Verify that:
1. The skill triggers correctly
2. Research phase runs
3. Architecture options are presented
4. Generated scaffold matches the updated templates

## Style guide

- All user-facing text in the skill: auto-detect the user's language and respond in kind (language-agnostic since v1.1.0)
- All code, file names, variable names, comments: English
- No em dashes — use hyphens or colons
- Keep SKILL.md under 400 lines
