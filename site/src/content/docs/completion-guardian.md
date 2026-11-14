---
title: Completion Guardian
description: An optional, separate completeness check the agent-skill workflow can run before it calls substantial work done.
---

[Completion Guardian](https://github.com/maioio/completion-guardian) is a separate tool. The Genesis agent-skill workflow can use it as a final check before it reports substantial work as complete, ready to ship or ready to release.

- **Optional.** Genesis does not bundle, install or require it. Without it, Genesis finishes through its own checks, unchanged.
- **Separate install.** You install it yourself, as the `project-completeness-audit` skill (or the `project-completion-guardian` plugin, which adds an automatic Stop hook). Genesis does not search plugin caches, so a plugin-only install is not found unless `GENESIS_COMPLETION_GUARDIAN_DIR` points at the skill folder or the skill is also installed in one of the locations below.
- **The agent does the audit.** The agent runs the skill in FINAL mode: it looks for what the project is missing or states falsely across code, tests, runtime behaviour, packaging, docs and public surface.
- **Fingerprint-aware.** Guardian fingerprints the project state. A clear verdict covers that exact state; any later change invalidates it.
- **Not a capability.** It is an integration, so it is not counted in the [capability catalog](/genesis-architect/capabilities/).
- **Not a proof.** It is a structured check run by the same agent that did the work, not an independent verification.

It is meant for the end of substantial work, not after small edits.

## The flow

The bridge is `python -m genesis_architect.core.completion_guardian`. In the skill it is `scripts/completion_guardian.py`. Each subcommand takes `--project <dir>` and prints JSON.

1. `detect`. If Guardian is not installed it prints `proceed_without_guardian` and the workflow continues as before. Nothing is installed.
2. `begin`. Records the project state about to be audited. The agent then runs the `project-completeness-audit` skill in FINAL mode.
3. Findings are failures. The agent runs `record --verdict findings`, fixes them in the relevant workflow (build, recover or harden) and goes back to step 2.
4. Only after an audit that really ran and came back clear: `record --verdict clear`, then `finalize`. It asks Guardian to mark the state as final only if the project is unchanged since `begin`, then asks Guardian to confirm the mark.
5. Completion is reported only after `finalize` returns `final_marked`.

Passing Genesis tests is not a reason to record a clear verdict. The bridge cannot tell whether the audit ran, so that rule is the agent's to keep.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Proceed. Also returned when Guardian is not installed | Continue |
| 3 | Blocked: findings, no clear audit, or the project changed after the audit | Fix, or run the audit again |
| 4 | Degraded: Guardian could not run, or the mark did not take effect | Report it, rely on the Genesis checks, do not claim the project was audited |

Without Guardian, exit 0 does not mean an audit ran. `finalize` reports `proceed_without_guardian` with `available` false, and any claim that the work is complete rests on the existing Genesis checks alone.

## Where Genesis looks

Only these locations, in this order. Plugin caches are never searched.

1. `GENESIS_COMPLETION_GUARDIAN_DIR`
2. `<project>/.claude/skills/project-completeness-audit/`
3. `~/.claude/skills/project-completeness-audit/`, or `$CLAUDE_CONFIG_DIR/skills/project-completeness-audit/` when that variable is set

A location counts only if it contains `scripts/guardian.py`. Genesis calls it with `python -I` and a 60-second timeout, and treats a non-zero exit or output that is not JSON as degraded.

The bridge keeps its bookkeeping outside the project, in `~/.genesis/completion-audit/` or `GENESIS_COMPLETION_STATE_DIR`, so it cannot change the project fingerprint.
