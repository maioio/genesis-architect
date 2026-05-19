# Genesis Architect v2.4.0 - Hard Gate Reinforcement

## The Failure Case: PSR.ai Phase 5

PSR.ai is a Python CLI project: a Windows Problem Steps Recorder wrapper for AI agents.
It was scaffolded using Genesis Architect and reached Phase 5 with the following state:

| Dimension | Expected | Actual |
|---|---|---|
| Research Quality Signal | FULL | PARTIAL |
| Repos analyzed | 12+ with Issue URLs | 6 (GitHub MCP unavailable) |
| Pitfall citation quality | All with verified Issue URLs | 5 pitfalls, 1 general ecosystem knowledge with no URL |
| Phase 5 doc previews | Inline RESEARCH.md, PITFALLS.md, ROADMAP.md | None (promised for later) |
| Architecture tree | All production defaults visible | No utils/security.py, .pre-commit-config.yaml, sonar-project.properties, docs/adr/001 |
| CI yml | 4 jobs expanded | Mentioned as one line |
| Phase 6 smoke gate | Defined in Phase 5 | Not defined until after scaffold built |
| Companion Mode handoff | At end of Phase 5 message | Absent |
| Windows risk mapping | In platform_risks: block | Listed as prose notes, no enforcement |

The skill continued past all of these gaps and asked the user to pick A/B/C/D anyway.
That is the core bug: the gates were advisory text, not enforced checks.

---

## Fix Mapping

### Fix 1 - Phase 2 hard gate

**Gap**: Skill reported PARTIAL and continued to Phase 5 with only 6 repos.

**Root cause**: The failure handling table said "5+ repos: continue normally" - the floor was defined too low and as advisory text.

**Prevention**: `genesis_state.py write-phase2` records `repo_count`, `deep_count`, and `phase2_passed`. The new floor is 12 repos verified + 5-8 deep. `require-phase2` is called at Phase 5 entry and aborts with an error if `phase2_passed` is false and `user_override` is false. The user must explicitly invoke `--accept-thin-research` (recorded in state) to continue with thin research.

**Files changed**: `scripts/genesis_state.py`, `SKILL.md` Phase 2 section.

---

### Fix 2 - Pitfall URL and mitigation_file_path enforcement

**Gap**: "General ecosystem knowledge" pitfall had no Issue URL and no scaffold file mapping.

**Root cause**: `research_validator.py` only ran on RESEARCH.md structure checks. PITFALLS.md had no per-pitfall URL enforcement.

**Prevention**: `research_validator.py --validate-pitfalls` runs at end of Phase 4 before Phase 5. It rejects any pitfall that lacks a verified GitHub issue URL or a `mitigation_file_path` that exists in the scaffold tree. The validator exits non-zero and blocks Phase 5 until all pitfalls are fixed or dropped.

**Files changed**: `scripts/research_validator.py`, `SKILL.md` Phase 4 section.

---

### Fix 3 - Inline doc previews in Phase 5

**Gap**: Phase 5 promised to generate RESEARCH.md, PITFALLS.md, ROADMAP.md "later". The user chose architecture blind.

**Root cause**: Phase 5 template had no requirement for inline content.

**Prevention**: Phase 5 now has a required Section 4 with real content previews for all three docs before the A/B/C/D prompt. Placeholder or TBD content fails the `write-phase5-previews` gate. Gate is recorded in `.genesis/phase-5-previews.json`.

**Files changed**: `scripts/genesis_state.py`, `SKILL.md` Phase 5 section.

---

### Fix 4 - Production defaults in architecture tree

**Gap**: Options A and B omitted `utils/security.py`, `.env.example`, `.pre-commit-config.yaml`, `sonar-project.properties`, `docs/adr/001-initial-architecture.md`.

**Root cause**: `folder-structures.toml` did not include these files in any archetype. The Phase 5 template drew from the TOML.

**Prevention**: Every language/tier in `references/folder-structures.toml` now includes all mandatory production-defaults files. `test_scaffold_generator.py` has parametrized tests asserting each required file appears in every archetype tree - CI fails if any is removed.

**Files changed**: `references/folder-structures.toml`, `tests/test_scaffold_generator.py`.

---

### Fix 5 - CI workflow expanded in Phase 5

**Gap**: `.github/workflows/ci.yml` was mentioned as a one-liner in the Phase 5 tree.

**Root cause**: Phase 5 template had no requirement to expand the CI job list.

**Prevention**: Every architecture option tree must include a comment block listing all 4 CI jobs with their activation conditions: `quality-gates` (always on), `secrets-scan` (always on), `sonarcloud` (activate with `SONAR_TOKEN`), `security-scan` (activate with `SNYK_TOKEN`).

**Files changed**: `SKILL.md` Phase 5 Section 3.

---

### Fix 6 - Phase 6 smoke gate defined in Phase 5

**Gap**: The smoke test command was not defined until after the scaffold was built, meaning the user could not audit it.

**Root cause**: Phase 5 template had no smoke gate section.

**Prevention**: Phase 5 Section 5 requires `scaffold_smoke_test.py --print-only` to be run and shown to the user before they pick A/B/C/D. Phase 6 records the result in `.genesis/phase-6-smoke.json` via `write-phase6-smoke`. `git commit` is blocked until `phase6_smoke_passed` is true.

**Files changed**: `scripts/genesis_state.py`, `scripts/scaffold_smoke_test.py`, `SKILL.md` Phase 5 and Phase 6.

---

### Fix 7 - Companion Mode handoff explicit at end of Phase 5

**Gap**: Phase 5 produced the scaffold and then stopped talking about ongoing collaboration. The `.genesis/vault/` directory was not created.

**Root cause**: Phase 5 template had no required Companion Mode section. Phase 6 Step 1 had no vault creation instruction.

**Prevention**: Phase 5 Section 6 (required at end of the message) explicitly announces Companion Mode is active and lists all post-scaffold commands. Phase 6 Step 1 always creates `.genesis/vault/README.md` explaining the Smart Resolution Engine cache.

**Files changed**: `SKILL.md` Phase 5 Section 6, Phase 6 Step 1.

---

### Fix 8 - Archetype-specific risk lists mapped to scaffold files

**Gap**: Windows risks (console encoding, path separators) were listed as prose notes in Phase 3 with no enforcement.

**Root cause**: `pitfall_coverage_check.py` only checked pitfall mitigations in source files. Platform risks had no schema.

**Prevention**: PITFALLS.md now has a required `platform_risks:` block schema. Each risk must have `mitigation_path` (verified to exist in the scaffold tree) or `acknowledged: true`. `pitfall_coverage_check.py --check-platform-risks` validates this at Phase 4 and Phase 6 Step 6.5. Risks without either field cause a non-zero exit.

**Files changed**: `scripts/pitfall_coverage_check.py`, `SKILL.md` Phase 4.

---

## How to verify all 8 fixes are working

```bash
# Phase 2 gate
python scripts/genesis_state.py write-phase2 /tmp/test --repo-count 6 --deep-count 3
# Expected: exit 1, "floor not met"

python scripts/genesis_state.py write-phase2 /tmp/test --repo-count 12 --deep-count 5
# Expected: exit 0, "PASSED"

# Phase 5 previews gate
python scripts/genesis_state.py write-phase5-previews /tmp/test --research --pitfalls
# Expected: exit 1, "ROADMAP.md" missing

# Phase 6 smoke gate
python scripts/genesis_state.py write-phase6-smoke /tmp/test --archetype cli --smoke-command "echo 1.0.0" --exit-code 0
# Expected: exit 0

# Pitfall validator
python scripts/research_validator.py examples/python-cli/PITFALLS.md --validate-pitfalls
# Expected: exit 0 (example has valid pitfalls)

# Platform risks
python scripts/pitfall_coverage_check.py examples/python-cli/PITFALLS.md examples/python-cli/src/ --check-platform-risks

# TOML production defaults (run test suite)
python -m pytest tests/test_scaffold_generator.py -k "production_defaults or security_file" -v
```
