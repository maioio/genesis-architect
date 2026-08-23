# Genesis Architect - Development Journal

This file documents lessons learned from real project runs. It drove the v1.2.0 - v1.9.0
improvements: Phase 0 environment probe, smoke test gate, Windows pitfall detection, and the
single-confirmation flow. Keeping it public so contributors understand why the skill works the
way it does.

**Runs documented:** `batch-rename` (Python CLI) and `dev-log` (Python CLI), May 2026.

---

## What worked well

- **Research phase produced genuinely useful data.** Finding `gitpulse`'s issue history was
  valuable - real architecture regrets documented in production, not hypothetical ones.
- **Pitfall-to-mitigation mapping translated directly into code.** Early-exit in
  `commit_reader.py`, the module split, and no GitHub API dependency all came from real issues.
- **A/B architectural choice was well-framed.** Concrete folder trees made the tradeoff legible.

---

## What was missing

### 1. No environment probe before the build
The skill picked `hatchling` from ecosystem research but never checked what Python version or
pip version the user has. This caused two preventable failures:
- hatchling editable install issue
- Windows console encoding crash (cp1252 vs UTF-8)

**Fix**: Add a Phase 0 environment probe before research. Detect OS, Python version,
and package manager. Use this context in Phase 3 (flag OS pitfalls) and Phase 6 (choose
correct build backend and install commands).

### 2. No smoke test before "complete"
The skill declared success without confirming the scaffold actually runs.
Two bugs only surfaced when the user ran `devlog` manually after the build.

**Fix**: Add a mandatory smoke test in Phase 6 Step 5.5:
run `[entrypoint] --help` or the test command, confirm exit 0, then declare complete.

### 3. Windows treated as afterthought
Rich's spinner uses Unicode characters that crash on Windows legacy console.
A local CLI tool is inherently Windows-relevant - this should be a first-class concern.

**Fix**: In Phase 3, if OS is Windows, automatically add Unicode/encoding risks
to the pitfall watchlist before research even starts.

---

## Phases that felt awkward

### Double confirmation (Phase 2 + Phase 5)
User confirmed the research at the Phase 2 checkpoint, then had to confirm again at Phase 5.
Two separate "yes" prompts for what felt like one decision.

**Fix**: Present the research summary and the two architecture options in a single message.
One confirmation, one decision.

### `genesis init` skips Phase 1 but has no environment fallback
When Phase 1 is skipped, the skill has no idea about the user's OS or constraints.
Scale and language are guessed from the description - usually fine, but no recovery path
if the guess is wrong.

**Fix**: Phase 0 (environment probe) runs even when Phase 1 is skipped.

---

## Suggested SKILL.md changes (implemented in v1.2.0)

1. Add Phase 0: Environment probe (OS, Python version, package manager)
2. Add Phase 6 Step 5.5: Mandatory smoke test before declaring complete
3. Add Windows auto-pitfall check in Phase 3
4. Merge Phase 2 approval checkpoint with Phase 5 A/B choice (single confirmation)
5. Phase 0 runs even when `genesis init` skips Phase 1

---

## Overall verdict

The research-first philosophy is the right instinct and produces genuinely better scaffolds
than jumping straight to code. The main gap is that "building" and "running" are treated as
the same thing - they are not, especially on Windows.
