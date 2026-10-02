"""Phase 5 — symlink containment in the fetched skill sandbox (audit finding D-2).

A skill pack is fetched from a whitelisted repository and its SKILL.md files
are read. A malicious pack can commit a *symlink* pointing out of the sandbox,
so the whitelist vouches for the repository while the bytes actually read come
from somewhere else entirely.

`read_skills()` defends against this by resolving every candidate path and
skipping any that lands outside the sandbox root.

D-2 recorded that this property was "argued, not observed": the test proving
it is skipped on Windows, which is the primary dev platform here. Creating a
symlink there fails with `WinError 1314` unless Developer Mode is on, so the
defence cannot be exercised at all on the machine where the code is written.

This container is Linux, where symlinks always work. Running the check here on
every invocation is what converts D-2 from argued to observed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from genesis_architect_pro.skill_fetcher import read_skills

OUTSIDE = "---\nname: EXFILTRATED\ndescription: outside the sandbox\n---\n"
INSIDE = "---\nname: legit-skill\ndescription: genuinely inside the sandbox\n---\n"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" -- {detail}" if detail else ""))
        failures.append(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        outside = root / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text(OUTSIDE, encoding="utf-8")

        sandbox = root / "sandbox"
        (sandbox / "legit").mkdir(parents=True)
        (sandbox / "legit" / "SKILL.md").write_text(INSIDE, encoding="utf-8")

        # Three escape routes a malicious pack could commit.
        planted = []
        try:
            (sandbox / "escape-dir").symlink_to(outside, target_is_directory=True)
            planted.append("escape-dir -> ../outside")
            (sandbox / "SKILL.md").symlink_to(outside / "SKILL.md")
            planted.append("SKILL.md -> ../outside/SKILL.md")
            (sandbox / "escape-system").symlink_to(Path("/etc"), target_is_directory=True)
            planted.append("escape-system -> /etc")
        except OSError as exc:
            # Not a pass. If symlinks cannot be created the property was never
            # tested, which is the exact D-2 failure mode this phase exists to
            # end. In a Linux container this should be impossible.
            print(f"  [FAIL] could not plant symlinks: {exc}")
            print("         containment was NOT exercised — D-2 is not closed by this run")
            return 2

        for p in planted:
            print(f"  planted: {p}")

        reachable = sorted(sandbox.rglob("SKILL.md"))
        escaping = [
            p for p in reachable
            if sandbox.resolve() not in p.resolve().parents
        ]
        check("rglob can reach at least one escaping path (the attack is real)",
              bool(escaping), "nothing escaped; the fixture proves nothing")

        skills = read_skills(sandbox)
        names = sorted(s.name for s in skills)
        print(f"  read_skills() -> {names}")

        check("the file outside the sandbox was NOT read",
              "EXFILTRATED" not in names, "containment breached")
        check("the file inside the sandbox WAS read (not over-blocking)",
              "legit-skill" in names)
        check("exactly one skill returned", len(skills) == 1, f"got {len(skills)}")

    if failures:
        print(f"\n  SYMLINK CONTAINMENT: {len(failures)} check(s) FAILED")
        return 1
    print("\n  SYMLINK CONTAINMENT: HELD (D-2 observed, not argued)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
