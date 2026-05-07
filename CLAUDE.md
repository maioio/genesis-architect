# Genesis Architect - Claude Code Instructions

This is a **Claude skill** project. The primary deliverable is `SKILL.md` — a Markdown file
that defines how Claude behaves when invoked.

## Project structure

```
SKILL.md                        # Main skill - read this first
references/
  architecture-patterns.md      # Boilerplate templates per language/tier
  mcp-strategy.md               # MCP tool usage and fallback logic
```

## How this skill works

Genesis Architect triggers on natural language like "I want to build X" or via
the explicit command `genesis init [vision]`.

It runs 7 phases:
1. Vision Alignment - 2-3 focused questions
2. Deep Discovery - scan 15-20 GitHub repos
3. Architecture Analysis - synthesize the "wise average"
4. Pitfall Identification - extract from GitHub Issues
5. Interactive Choice - Minimalist vs Scalable
6. Genesis Build - create scaffold with tests and CI/CD
7. Development Companion Mode - stays active, keeps searching and suggesting

## Development workflow

When working on this skill:

1. **Edit `SKILL.md`** for workflow changes (phases, prompts, rules)
2. **Edit `references/architecture-patterns.md`** to add language templates
3. **Edit `references/mcp-strategy.md`** for tool strategy changes
4. **Test** by invoking: `genesis init a [simple project description]`
5. **Update `CHANGELOG.md`** with what changed

## Key constraints (enforced in SKILL.md)

- User-facing communication: Auto-detect user language and respond in kind (language-agnostic since v1.1.0)
- Code, filenames, comments: English only
- No em dashes anywhere
- SKILL.md must stay under 400 lines
- Research Approval Checkpoint must run between Phase 2 and Phase 3
- `genesis init` must skip Phase 1 questions and go straight to research

## Adding a new language template

Add to `references/architecture-patterns.md`:

```markdown
## [Language] - Minimalist
[folder structure]

## [Language] - Scalable
[folder structure]
```

Follow the existing JS/TS and Python patterns exactly.

## Versioning

This project uses Semantic Versioning:
- Patch (1.0.x): wording fixes, minor template corrections
- Minor (1.x.0): new language templates, new MCP strategies
- Major (x.0.0): changes to the 7-phase workflow structure (now 8 phases with Phase 0)
