# Completion Guardian (optional final verification)

Completion Guardian is an optional, external completeness auditor:
https://github.com/maioio/completion-guardian

Genesis does not bundle, install or require it. When it is present, it adds one
independent FINAL audit between "Genesis verification passed" and "work is complete".
When it is absent, Genesis finishes through its existing gates, unchanged.

## What Guardian adds

- Independent audit of the whole project against what was claimed (README, CLI, docs, tests).
- A fingerprint of the project state, so "audited" always means "this exact state".
- `status` (deterministic JSON) and `mark` (record the audited state), owned by Guardian.

## Skill vs plugin

| | Standalone skill `project-completeness-audit` | Plugin `project-completion-guardian` |
|---|---|---|
| Audit, probe, status, mark | yes | yes |
| Automatic Stop hook | no (a skill cannot register hooks) | yes |

Genesis uses only what the skill provides. Genesis never copies or registers the Stop hook.

## Flow

research, architecture, build/recover/harden, Genesis verification, **optional Guardian
FINAL audit**, fix findings, re-audit, mark final, completion.

Run it only at the end of substantial work (before you say COMPLETE, READY TO SHIP,
READY TO RELEASE, final or finished). Not after small edits. MILESTONE mode is optional.

## Procedure (agent)

Helper: `python scripts/completion_guardian.py <cmd> --project <dir>` (JSON on stdout).

1. `detect`. `available: false` means continue with the existing gates. Install nothing.
2. `begin`. It records the project state about to be audited. Then run the
   `project-completeness-audit` skill in FINAL mode yourself.
3. Findings are verification failures. Run `record --verdict findings`, return to the
   relevant Genesis workflow (build, recover or harden), fix, then go back to step 2.
4. Only after the audit really ran and came back clear: `record --verdict clear`, then
   `finalize`. It marks only if the project is unchanged since `begin`, then asks Guardian
   to confirm the final audited state.
5. Report completion only after `finalize` returns `final_marked`.

Never run `record --verdict clear` or `finalize` because Genesis tests are green. The
audit must have been performed. The helper cannot prove that, so this rule is yours.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | proceed (also: Guardian not installed) | continue |
| 3 | blocked: findings, no clear audit, or state changed | fix or re-audit |
| 4 | degraded: Guardian unusable or the mark did not take effect | report it, rely on Genesis gates, do not claim "audited" |

## Discovery

Documented locations only, in this order. Plugin caches are never searched.

1. `GENESIS_COMPLETION_GUARDIAN_DIR` (explicit override)
2. `<project>/.claude/skills/project-completeness-audit/`
3. `~/.claude/skills/project-completeness-audit/` (or `$CLAUDE_CONFIG_DIR/skills/...`)

A location counts only if it contains `scripts/guardian.py`. The helper calls Guardian with
`python -I`, with a timeout, and treats any non-zero exit or non-JSON output as degraded.

Audit bookkeeping lives outside the project (`~/.genesis/completion-audit/`, or
`GENESIS_COMPLETION_STATE_DIR`), so it cannot alter Guardian's project fingerprint.
