"""Supply-chain audit — CI workflow references must name an immutable revision.

A CI workflow that says `uses: actions/checkout@v4` delegates trust to a
*mutable pointer*. Whoever controls that repository can move `v4` to new code,
and every consumer executes it on the next run with no diff appearing anywhere
in the consuming repo. A 40-character commit SHA names an immutable object, so
what ran yesterday is what runs today.

Genesis already applies exactly this rule to its own supply chain: a
`TrustedSource` in `skill_fetcher` carries a pinned commit, and a fetch whose
HEAD has moved is refused rather than read. This module applies the same rule
outward, to the CI of the project under analysis.

Deliberately not a YAML parser. This reads untrusted input, and a full YAML
loader is a much larger attack surface than a line-oriented reader — the same
reasoning as `skill_fetcher._parse_frontmatter`. Everything needed here lives
on a single line (`uses: <ref>`), so a scanner that understands one line is
both sufficient and smaller.

Honesty contract, matching the rest of the codebase:

  * A project with no CI files produces **no finding**, not a passing one.
    Absence of a workflow is not evidence of a pinned workflow.
  * `unpinned` and `unpinnable` are reported separately. A container step with
    no digest available is "cannot be verified", not "verified and failed" —
    the same distinction as `coverage=None` versus `0.0`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Where CI definitions live. Ordered, and each entry is (label, glob).
WORKFLOW_GLOBS: tuple[tuple[str, str], ...] = (
    ("github", ".github/workflows/*.yml"),
    ("github", ".github/workflows/*.yaml"),
)

# A pinned reference is a full-length commit SHA. Not 7, not 12: an
# abbreviated SHA is a prefix match, and git will happily resolve a longer
# object that starts with it.
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# `uses:` as a mapping key, optionally introduced by a list dash. Trailing
# comments are stripped separately — `@sha # v4` is the documented idiom and
# the comment must not become part of the ref.
_USES = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(?P<ref>\S+)")

# A tag that looks like a release, for reporting only. Distinguishing a tag
# from a branch matters to the reader ("v4" reads safe, "main" reads obviously
# unsafe) but not to the verdict: both are mutable.
_VERSION_TAG = re.compile(r"^v?\d")

MAX_FILE_BYTES = 512 * 1024


@dataclass
class ActionRef:
    """One `uses:` reference and what it resolves to."""

    file: str                # project-relative
    line: int                # 1-indexed
    raw: str                 # the ref exactly as written
    owner_repo: str          # "actions/checkout", or "" when not applicable
    ref: str                 # what follows '@', or "" when absent
    kind: str                # sha | tag | branch | local | digest | unpinnable

    @property
    def is_pinned(self) -> bool:
        return self.kind in ("sha", "digest")

    @property
    def is_exempt(self) -> bool:
        """Local actions carry no external trust — they are this repository."""
        return self.kind == "local"


@dataclass
class SupplyChainReport:
    workflow_files: list[str] = field(default_factory=list)
    refs: list[ActionRef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def scanned(self) -> bool:
        """True only if there was CI to look at.

        A project with no workflows must not render as compliant, so callers
        check this before reporting anything at all.
        """
        return bool(self.workflow_files)

    @property
    def unpinned(self) -> list[ActionRef]:
        """External references naming a mutable pointer — the actual finding."""
        return [r for r in self.refs
                if not r.is_pinned and not r.is_exempt and r.kind != "unpinnable"]

    @property
    def unpinnable(self) -> list[ActionRef]:
        """References that cannot be pinned from here. Reported, never counted
        as failures: an unverifiable thing is not a thing verified and failed."""
        return [r for r in self.refs if r.kind == "unpinnable"]

    @property
    def pinned(self) -> list[ActionRef]:
        return [r for r in self.refs if r.is_pinned]

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "workflow_files": self.workflow_files,
            "pinned_count": len(self.pinned),
            "unpinned_count": len(self.unpinned),
            "unpinnable_count": len(self.unpinnable),
            "unpinned": [
                {"file": r.file, "line": r.line, "ref": r.raw, "kind": r.kind}
                for r in self.unpinned
            ],
            "unpinnable": [
                {"file": r.file, "line": r.line, "ref": r.raw} for r in self.unpinnable
            ],
            "errors": self.errors,
        }


def _strip_comment(ref: str) -> str:
    """Drop a trailing `# v4` annotation.

    Pinning is conventionally written `@<sha> # v4`, where the comment records
    what the SHA meant. `_USES` captures only up to the first whitespace, so
    this handles the rarer no-space form and quoted refs.
    """
    return ref.split("#", 1)[0].strip().strip('"').strip("'")


def classify_ref(raw: str) -> tuple[str, str, str]:
    """Return (owner_repo, ref, kind) for one `uses:` value."""
    value = _strip_comment(raw)
    if not value:
        return "", "", "unpinnable"

    # A path reference is this repository — no external trust is delegated.
    if value.startswith("./") or value.startswith("../"):
        return value, "", "local"

    # Container steps pin by digest rather than by commit.
    if value.startswith("docker://"):
        body = value[len("docker://"):]
        if "@sha256:" in body:
            image, _, digest = body.partition("@")
            return image, digest, "digest"
        return body, "", "unpinnable"

    if "@" not in value:
        # No ref at all resolves to the action's default branch.
        return value, "", "branch"

    owner_repo, _, ref = value.partition("@")
    if _FULL_SHA.match(ref):
        return owner_repo, ref, "sha"
    if _VERSION_TAG.match(ref):
        return owner_repo, ref, "tag"
    return owner_repo, ref, "branch"


def scan_workflows(project_path: str | Path) -> SupplyChainReport:
    """Find every external action reference in the project's CI and classify it.

    Read-only. Never raises: an unreadable workflow is recorded as an error and
    the scan continues, because one malformed file must not hide the findings
    in the others.
    """
    root = Path(project_path)
    report = SupplyChainReport()

    seen: set[Path] = set()
    for _label, pattern in WORKFLOW_GLOBS:
        try:
            candidates = sorted(root.glob(pattern))
        except (OSError, RuntimeError) as exc:
            report.errors.append(f"could not list {pattern}: {exc}")
            continue

        for path in candidates:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    report.errors.append(f"{path.name}: too large to scan")
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                report.errors.append(f"{path.name}: {exc}")
                continue

            rel = path.relative_to(root).as_posix()
            report.workflow_files.append(rel)

            for lineno, line in enumerate(text.splitlines(), start=1):
                if line.lstrip().startswith("#"):
                    continue
                match = _USES.match(line)
                if not match:
                    continue
                raw = _strip_comment(match.group("ref"))
                if not raw:
                    continue
                owner_repo, ref, kind = classify_ref(raw)
                report.refs.append(ActionRef(
                    file=rel, line=lineno, raw=raw,
                    owner_repo=owner_repo, ref=ref, kind=kind,
                ))

    return report


def format_report(report: SupplyChainReport) -> str:
    """Human-readable summary."""
    if not report.scanned:
        return ("  Supply chain: no CI workflows found — nothing to verify.\n"
                "  (This is not a pass: absence of CI is not a pinned CI.)")

    lines = [f"  Supply chain: {len(report.workflow_files)} workflow file(s), "
             f"{len(report.refs)} action reference(s)"]
    lines.append(f"    pinned      : {len(report.pinned)}")
    lines.append(f"    unpinned    : {len(report.unpinned)}")
    if report.unpinnable:
        lines.append(f"    unpinnable  : {len(report.unpinnable)} (reported, not counted)")

    for r in report.unpinned:
        lines.append(f"      {r.file}:{r.line}  {r.raw}  ({r.kind} — mutable)")
    for r in report.unpinnable:
        lines.append(f"      {r.file}:{r.line}  {r.raw}  (cannot be verified from here)")
    for err in report.errors:
        lines.append(f"      ! {err}")

    if not report.unpinned:
        lines.append("    every external action names an immutable revision.")
    return "\n".join(lines)
