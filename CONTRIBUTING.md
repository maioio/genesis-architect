# Contributing to Genesis Architect

Thank you for helping improve Genesis Architect.

## What to contribute

- **New language templates** - Go and Rust are already implemented; add boilerplate for Java, C#, Swift, or other languages in `references/architecture-patterns.md`
- **Better MCP strategies** - improve tool usage in `references/mcp-strategy.md`
- **Workflow improvements** - refine phases in `SKILL.md`
- **Bug reports** - open an issue with the template

## How to contribute

1. Fork the repository
2. Create a branch: `git checkout -b improve/rust-templates`
3. Make your changes
4. Open a pull request with a clear description

## Editing the skill

The skill is plain Markdown - no build step required.

- `SKILL.md` - main skill logic and phase definitions
- `references/architecture-patterns.md` - language boilerplate templates
- `references/mcp-strategy.md` - MCP tool strategy and fallback logic

## Testing changes

After editing, test by invoking the skill in Claude Code:

```
genesis init a simple CLI tool in [your language]
```

Verify that:
1. The skill triggers correctly
2. Phase 0 runs silently and detects OS, Python version, and package manager
3. Research phase runs
4. Architecture options are presented
5. Generated scaffold matches the updated templates
6. The smoke test (`[entrypoint] --help` or `pytest` / `npm test`) passes with exit code 0

## Updating the README

Three tools make README maintenance easier:

**[readme.so](https://readme.so/editor)** - Visual drag-and-drop editor for README sections. Use it
to draft new sections (Contributing, FAQ, Environment Variables, etc.) and download the markdown.
Copy the output into README.md - no CLI or build step needed.

**[shields.io](https://shields.io)** - Badge generator. All badges in README.md follow this format:
```
https://img.shields.io/badge/[label]-[message]-[color]
```
For live GitHub data use the endpoint badges:
```
# CI status:  https://img.shields.io/github/actions/workflow/status/{user}/{repo}/{workflow.yml}
# Stars:      https://img.shields.io/github/stars/{user}/{repo}
# Version:    https://img.shields.io/github/v/release/{user}/{repo}
```
Style options: `flat` (default), `flat-square`, `for-the-badge`.

**[asciinema](https://asciinema.org)** - Terminal session recorder. To update the demo recording:
```bash
asciinema rec demo.cast          # record a session
asciinema upload demo.cast       # get a shareable URL
agg demo.cast assets/demo.gif   # convert to GIF for GitHub (needs agg installed)
```
GitHub markdown does not render `<script>` tags, so the GIF files in `assets/` are the primary
demo format. The asciinema link in README.md is for the interactive player on asciinema.org.

## Style guide

- All user-facing text in the skill: auto-detect the user's language and respond in kind (language-agnostic since v1.1.0)
- All code, file names, variable names, comments: English
- No em dashes - use hyphens or colons
- Keep SKILL.md under 400 lines
