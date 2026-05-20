# Enforcement Depth Report
<!-- Genesis Architect internal audit document -->
<!-- Generated: 2026-05-20 | Version: v2.6.0 -->

This document classifies every enforcement mechanism by its actual depth.
No inflation. If something is heuristic, it is labeled heuristic.

---

## Classification Key

| Level | Meaning |
|-------|---------|
| **AST** | Parses Python source to AST, no execution |
| **Symbol** | Verifies named function/class exists in AST |
| **Import** | Verifies specific module is imported in AST |
| **Structural** | Compares filesystem layout to expected layout |
| **Regex** | Pattern match on text - fragile to wording changes |
| **Existence** | Checks file exists on disk - no content verification |
| **Heuristic** | Keyword match or proxy signal, not ground truth |
| **LLM-dependent** | Requires LLM to follow SKILL.md instructions |

---

## mitigation_enforcer.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| File exists | Existence | Yes | Hard prerequisite |
| Valid Python | AST | Yes | `ast.parse()` - no exec |
| Non-stub code | AST | Yes | Rejects pure comments/pass/ellipsis bodies |
| Symbol exists | Symbol | Yes | Only when `mitigation_symbol:` set in PITFALLS.md |
| Import present | Import | Yes | Only when `mitigation_import:` set in PITFALLS.md |

**Depth: AST-level for Python files. Existence-only for non-.py files (e.g. package.json).**
**Weakness: symbol/import checks only fire if the author writes `mitigation_symbol:` in PITFALLS.md.
If omitted, only non-stub check runs.**

---

## drift_detector.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| Directory layout | Structural | Partial | Parsed from ADR bullet list - fragile to ADR format |
| ADR parsing (code block) | Regex | Partial | `r"^[├└│\s]+(\w[\w.-]*)/"` - tree diagrams only |
| ADR parsing (bullet list) | Regex | Partial | `r"^\s*[-*]\s+` - bullets only, not tables |
| Import boundary | AST + Heuristic | Partial | AST is reliable; rule derivation from arch_rationale text is heuristic |
| Forbidden import detection | AST | Yes | Walks all .py files, checks top-level module name |

**Depth: AST for import detection. Heuristic for rule derivation (rationale text parsing).
Structural for directory layout.**
**Weakness: `forbidden_imports` derived from arch_rationale prose ("no database", "no server")
is keyword-based. A rationale that says "avoid relational storage" would not trigger sqlite3 blocking.
Explicit `architecture_rules` in evidence.json bypasses this.**

---

## evidence_pack.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| File presence | Existence | Yes | RESEARCH.md, PITFALLS.md, ROADMAP.md must exist |
| Template detection | Regex | Partial | Checks for placeholder strings like `[project name]` |
| Repo count | Heuristic | Partial | Counts markdown table rows - not verified live |
| Issue URL presence | Regex | Partial | Detects GitHub issue URL pattern, not HTTP-verified here |
| Pitfall mapping | Existence | Yes | Counts pitfalls with `mitigation_file_path:` set |
| Confidence score | Heuristic | Partial | Weighted average of proxy signals, not ground truth quality |
| evidence_signed | State file | Yes | Reads `.genesis/phase-5-confirmed.json` - binary |

**Depth: Heuristic for quality signals. Existence-level for file and mapping checks.
Confidence score is a useful proxy, not a verified measure.**
**Weakness: A RESEARCH.md with fabricated repo rows but correct markdown format
would pass with a high confidence score.**

---

## pitfall_coverage_check.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| Mitigation keyword search | Regex/Heuristic | Weak | Greps source for 1-3 keywords from mitigation text |
| Platform risk fields | Regex | Partial | Checks `platform_risks:` YAML block exists |

**Depth: Heuristic keyword grep. Advisory only - does not gate CI hard.**
**This is the weakest enforcement script. It is correctly labeled advisory in SKILL.md.**

---

## research_validator.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| Section presence | Regex | Partial | Checks required section headers exist |
| Issue URL format | Regex | Yes | Validates GitHub issue URL pattern |
| Issue URL liveness | HTTP | Yes | `--verify-issues` makes real HTTP requests |
| Pitfall URL presence | Regex | Yes | Every pitfall must have a URL |

**Depth: HTTP-verified for URLs when `--verify-issues` is used. Regex for structure.
This is the most trustworthy validation script - it checks real external state.**

---

## genesis_state.py

| Check | Level | Reliable? | Notes |
|-------|-------|-----------|-------|
| State file write | Filesystem | Yes | Writes JSON with timestamp and params |
| State file read | Filesystem | Yes | Reads and validates required fields |
| Require gates | Existence + Schema | Yes | Exits 1 if file missing or fields absent |
| Write time | LLM-dependent | Weak | LLM must call `write-phase2` etc. - no automation |

**Depth: Mechanically reliable for read/require. LLM-dependent for write.**
**Weakness: If the LLM skips calling `write-phase5`, the gate file never exists
and `require-phase5` will correctly block - but only if someone calls it.
The CI smoke test proves the mechanism works; it does not prove it is called in practice.**

---

## CI Enforcement Summary

| What CI actually blocks | How |
|------------------------|-----|
| Broken unit tests | pytest exit code |
| Missing/stub mitigation files | mitigation_enforcer.py exit 1 |
| Template-only evidence pack | evidence_pack.py exit 1 |
| Structural directory drift | drift_detector.py exit 1 |
| Forbidden imports (AST) | drift_detector.py Level 2 exit 1 |
| Dead issue URLs (example) | research_validator.py --verify-issues exit 1 |
| Exposed secrets | Gitleaks exit 1 |
| SKILL.md over 400 lines | wc -l check exit 1 |
| Em dashes anywhere | grep check exit 1 |
| genesis_state mechanism broken | state machine smoke test exit 1 |

| What CI does NOT block | Why |
|-----------------------|-----|
| LLM skipping write-phase2 | No hook can intercept LLM behavior |
| Fabricated repo URLs in RESEARCH.md | evidence_pack counts rows, does not fetch |
| Low-quality mitigations (correct file, poor code) | AST checks non-stub, not logic quality |
| TypeScript mitigation files | No .ts source in examples to enforce against |

---

## Honest Verdict

**Most trustworthy:** `research_validator.py --verify-issues` (real HTTP), `mitigation_enforcer.py` (real AST)
**Least trustworthy:** `pitfall_coverage_check.py` (keyword grep), `evidence_pack.py` confidence score (proxy)
**Correctly labeled:** pitfall_coverage_check is marked advisory in SKILL.md
**Biggest gap:** LLM-dependent write phase for genesis_state.py - unavoidable for a skill-based tool
