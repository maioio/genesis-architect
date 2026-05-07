# Changelog

All notable changes to Genesis Architect will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

---

## [1.1.0] - 2026-05-07

### Added
- **Phase 7 - Development Companion Mode**: after scaffolding, the skill stays active as a
  research partner throughout the project lifecycle
- **Language auto-detection**: skill now responds in the user's language (Hebrew, English, or any other)
- **`scripts/scaffold_generator.py`**: stdlib-only Python script that creates project structure
  for TypeScript, Python, Go, and Rust (minimalist + scalable tiers)
- **`scripts/research_validator.py`**: validates generated RESEARCH.md for completeness
- **`scripts/eval_runner.py`**: prints test queries and report templates for trigger-rate testing
- **`evals/test_queries.json`**: 31 test cases (18 should-trigger, 13 should-not-trigger)
- **`examples/typescript-cli/`**: real output example with RESEARCH.md, PITFALLS.md, ROADMAP.md
- **`assets/`**: output templates for RESEARCH.md, PITFALLS.md, ROADMAP.md
- **`plugin.json`**: machine-readable manifest for skill marketplaces
- **Go templates**: Minimalist and Scalable boilerplate in `references/architecture-patterns.md`
- **Rust templates**: Minimalist and Scalable boilerplate in `references/architecture-patterns.md`
- **YAML frontmatter** in SKILL.md (required by agentskills.io spec)
- README badges and structured installation one-liner

### Changed
- SKILL.md rewritten to be language-agnostic (removed hardcoded Hebrew prompts)
- Phase 2 search approval checkpoint improved with clearer table format
- Phase 6 now references `scaffold_generator.py` when available
- README completely restructured with phase table, file structure, and install one-liner

---

## [Unreleased]

---

## [1.0.0] - 2026-05-07

### Added
- 6-phase workflow: Vision Alignment, Deep Discovery, Architecture Analysis,
  Pitfall Identification, Interactive Choice, Genesis Build
- `genesis init [vision]` explicit invocation command
- Research Approval Checkpoint between discovery and architecture phases
- Mandatory deliverables: RESEARCH.md, PITFALLS.md, ROADMAP.md
- Functional boilerplate templates for JavaScript/TypeScript and Python (Minimalist + Scalable)
- GitHub Actions CI/CD template
- MCP tool priority chain with graceful fallback (GitHub MCP → Exa → Firecrawl → Web search)
- Architect Mode for first-principles design when no comparable projects exist
- Engineering decision comment format for all generated code
