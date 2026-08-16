"""Dynamic Skill Fetcher — whitelist-only, fetch-and-read, never execute.

Brings external skill packs into a project sandbox so Genesis can read what
they contain, then lets Auto-Purge take them away again.

The security posture is deliberately narrow, and the narrowness is the point:

  * **Whitelist only.** A fetch is addressed by `source_id` against a static
    registry — never by a caller-supplied URL. There is no code path that
    turns arbitrary input into a network target, so "fetch this URL" is not a
    capability this module has to defend; it simply doesn't exist.
  * **Never executes.** Fetched content is parsed as text and nothing else.
    No `subprocess` on downloaded files, no `import`, no `eval`. The only
    process ever spawned is the local `git` binary doing the clone, and it
    runs with `--no-recurse-submodules` so a submodule URL in the repo can't
    redirect the fetch somewhere unvetted.
    This is not a limitation to be worked around later: a skill pack is
    markdown and YAML — instructions for an agent, not a program — so reading
    is the whole job. Anything that genuinely needed execution would be a
    different feature with a different threat model (a container), not a flag
    on this one.
  * **Ephemeral by construction.** Every fetch writes an `.ephemeral.json`
    manifest via `mark_ephemeral()` before returning, with a short TTL. The
    sandbox is therefore already known to `ephemeral_purge.purge()` the
    instant it exists — cleanup is not a step a caller can forget.
  * **Sandbox-contained.** Everything lands under `.genesis/sandbox/` inside
    the project. Source ids are validated against a strict pattern, so a
    crafted id cannot traverse out of it.
  * **Read stays inside.** Files are resolved before reading and skipped if
    they land outside the sandbox, so a symlink committed into a repo cannot
    be used to read arbitrary host files.

Network access is injected (`cloner=`), matching the pattern used by the
Committee and Red-Team engines, so the whole module is testable offline.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from genesis_architect_pro.ephemeral_purge import mark_ephemeral, remove_tree

# A fetched sandbox is short-lived by policy. Callers may shorten this, never
# extend it past the ceiling.
DEFAULT_TTL_HOURS = 2.0
MAX_TTL_HOURS = 2.0

SANDBOX_DIRNAME = "sandbox"

# Read limits — a fetched repo is untrusted input, so it gets bounded.
MAX_SKILL_BYTES = 256 * 1024
MAX_SKILL_FILES = 200

# Source ids are used to build a path; keep them boring on purpose.
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class FetchRefused(RuntimeError):
    """Raised when a fetch is rejected before any network access happens."""


# ---------------------------------------------------------------------------
# Trusted registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustedSource:
    source_id: str
    host: str
    owner: str
    repo: str
    description: str
    kind: str = "skill_pack"
    license: str = ""

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}.git"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


REGISTRY: dict[str, TrustedSource] = {
    "software-architecture-skills": TrustedSource(
        source_id="software-architecture-skills",
        host="github.com", owner="45ck", repo="software-architecture-skills",
        description="Platform-neutral architecture skill pack: ADR writing, tradeoff "
                    "analysis, quality-attribute scenarios, deployment views.",
        license="MIT",
    ),
    "deep-research-skills": TrustedSource(
        source_id="deep-research-skills",
        host="github.com", owner="Weizhena", repo="Deep-Research-skills",
        description="Two-phase research workflow: outline generation, then deep "
                    "investigation with human oversight.",
        license="MIT",
    ),
}


def list_sources() -> list[TrustedSource]:
    """Every source this module is willing to fetch."""
    return [REGISTRY[key] for key in sorted(REGISTRY)]


def validate_source(source_id: str) -> TrustedSource:
    """Resolve a source id to a trusted entry, or refuse.

    This is the only way to obtain a fetch target. It refuses before any
    network call, so an untrusted id never reaches the wire.
    """
    if not isinstance(source_id, str) or not source_id:
        raise FetchRefused("Source id must be a non-empty string.")
    if not _SOURCE_ID_RE.match(source_id):
        raise FetchRefused(
            f"Refused: {source_id!r} is not a valid source id. Ids are lowercase "
            "alphanumerics with . _ - only, so they can never traverse a path."
        )
    source = REGISTRY.get(source_id)
    if source is None:
        known = ", ".join(sorted(REGISTRY)) or "(registry is empty)"
        raise FetchRefused(
            f"Refused: {source_id!r} is not in the trusted registry. "
            f"Known sources: {known}. Arbitrary URLs are never fetched."
        )
    if source.host != "github.com":
        raise FetchRefused(
            f"Refused: registry entry {source_id!r} points at unsupported host "
            f"{source.host!r}."
        )
    return source


def is_trusted_url(url: str) -> bool:
    """True only if `url` is exactly a registered source's clone URL."""
    return any(url == source.url for source in REGISTRY.values())


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


def sandbox_root(project_dir: Path) -> Path:
    return Path(project_dir) / ".genesis" / SANDBOX_DIRNAME


def sandbox_for(project_dir: Path, source_id: str) -> Path:
    """Where a given source lands. Validated, so it cannot escape the sandbox."""
    validate_source(source_id)
    return sandbox_root(project_dir) / source_id


# ---------------------------------------------------------------------------
# Clone (injectable)
# ---------------------------------------------------------------------------

Cloner = Callable[[str, Path], "tuple[bool, str]"]


def _default_cloner(url: str, dest: Path) -> tuple[bool, str]:
    """Shallow-clone `url` into `dest` using the local git binary.

    `--no-recurse-submodules` matters: a submodule entry in an otherwise
    trusted repo would otherwise pull from a URL nobody vetted.
    """
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", "--no-recurse-submodules",
             "--quiet", url, str(dest)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
    except FileNotFoundError:
        return False, "git is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return False, "git clone timed out after 180s"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git clone failed: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or "git clone failed").strip()
    return True, ""


# ---------------------------------------------------------------------------
# Skill definitions (read-only parsing)
# ---------------------------------------------------------------------------


@dataclass
class SkillDefinition:
    name: str
    description: str
    path: str          # relative to the sandbox dir
    body_chars: int = 0


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple `key: value` frontmatter between leading `---` fences.

    Deliberately not a YAML parser: this reads untrusted input, and a full
    YAML loader is a much larger attack surface than a line-oriented reader.
    Only flat string scalars are understood, which is all a SKILL.md header
    needs.
    """
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line.startswith((" ", "\t", "-", "#")):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            fields[key] = value
    return fields


def read_skills(sandbox_dir: Path) -> list[SkillDefinition]:
    """Parse every SKILL.md under a fetched sandbox. Reads only; never executes.

    Files that resolve outside the sandbox (a symlink committed into the repo)
    are skipped rather than followed.
    """
    root = Path(sandbox_dir)
    if not root.is_dir():
        return []
    try:
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return []

    found: list[SkillDefinition] = []
    try:
        paths = sorted(root.rglob("SKILL.md"))
    except (OSError, RuntimeError):
        return []

    for path in paths[:MAX_SKILL_FILES]:
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            continue
        # Containment: a symlink pointing out of the sandbox is not read.
        if root_resolved not in resolved.parents:
            continue
        try:
            if path.stat().st_size > MAX_SKILL_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fields = _parse_frontmatter(text)
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = path.name
        found.append(SkillDefinition(
            name=fields.get("name", path.parent.name),
            description=fields.get("description", ""),
            path=rel,
            body_chars=len(text),
        ))
    return found


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    source_id: str
    ok: bool
    sandbox_dir: str = ""
    manifest_path: str = ""
    ttl_hours: float = DEFAULT_TTL_HOURS
    skills: list[SkillDefinition] = field(default_factory=list)
    error: str = ""
    reused_existing: bool = False

    @property
    def skill_count(self) -> int:
        return len(self.skills)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id, "ok": self.ok,
            "sandbox_dir": self.sandbox_dir, "manifest_path": self.manifest_path,
            "ttl_hours": self.ttl_hours, "error": self.error,
            "reused_existing": self.reused_existing,
            "skills": [
                {"name": s.name, "description": s.description,
                 "path": s.path, "body_chars": s.body_chars}
                for s in self.skills
            ],
        }


def fetch(
    source_id: str,
    project_dir: Path,
    *,
    ttl_hours: float = DEFAULT_TTL_HOURS,
    cloner: Cloner = _default_cloner,
    force: bool = False,
) -> FetchResult:
    """Fetch a trusted skill pack into the project sandbox and read it.

    Refuses anything not in the registry, before touching the network. The
    sandbox is marked ephemeral before this returns, so Auto-Purge already
    owns its cleanup even if the caller crashes immediately afterwards.
    """
    source = validate_source(source_id)  # raises FetchRefused

    ttl = min(float(ttl_hours), MAX_TTL_HOURS)
    if ttl <= 0:
        raise FetchRefused("ttl_hours must be positive.")

    dest = sandbox_for(project_dir, source_id)

    if dest.exists() and not force:
        skills = read_skills(dest)
        manifest = mark_ephemeral(
            dest, ttl_hours=ttl,
            purpose=f"fetched skill pack {source.slug} (refreshed TTL)")
        return FetchResult(
            source_id=source_id, ok=True, sandbox_dir=str(dest),
            manifest_path=str(manifest), ttl_hours=ttl, skills=skills,
            reused_existing=True,
        )

    if dest.exists():
        try:
            remove_tree(dest)
        except OSError as exc:
            return FetchResult(source_id=source_id, ok=False,
                               error=f"could not clear existing sandbox: {exc}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    ok, err = cloner(source.url, dest)
    if not ok:
        # Leave nothing half-fetched behind.
        if dest.exists():
            try:
                remove_tree(dest)
            except OSError:
                shutil.rmtree(dest, ignore_errors=True)
        return FetchResult(source_id=source_id, ok=False,
                           error=err or "clone failed")

    # Mark ephemeral immediately — before reading, before returning — so the
    # sandbox can never exist in an untracked state.
    manifest = mark_ephemeral(
        dest, ttl_hours=ttl, purpose=f"fetched skill pack {source.slug}")

    skills = read_skills(dest)
    return FetchResult(
        source_id=source_id, ok=True, sandbox_dir=str(dest),
        manifest_path=str(manifest), ttl_hours=ttl, skills=skills,
    )


def discard(source_id: str, project_dir: Path) -> bool:
    """Remove a fetched sandbox now, rather than waiting for TTL expiry.

    Returns True if something was removed. Auto-Purge would collect it anyway;
    this is for callers who know they are done.
    """
    dest = sandbox_for(project_dir, source_id)  # validates the id
    if not dest.is_dir():
        return False
    try:
        remove_tree(dest)
    except OSError:
        return False
    return True


def execute(*_args, **_kwargs):
    """Explicitly unsupported.

    Present so the refusal is discoverable in the API rather than being an
    absence someone later "fixes" by adding a subprocess call. Executing
    fetched code needs real isolation (a container), which is a different
    feature with a different threat model — not a flag on this one.
    """
    raise NotImplementedError(
        "skill_fetcher never executes fetched content. Skill packs are markdown "
        "and YAML; use read_skills() to read them. Running untrusted code "
        "requires container isolation, which this module deliberately does not "
        "provide."
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_sources() -> str:
    lines = ["", "  Trusted skill sources", ""]
    for source in list_sources():
        lines.append(f"    {source.source_id}")
        lines.append(f"      {source.slug}  ({source.license or 'license unknown'})")
        lines.append(f"      {source.description}")
        lines.append("")
    lines.append("  Only these are fetchable. Arbitrary URLs are never fetched.")
    lines.append("")
    return "\n".join(lines)


def format_result(result: FetchResult) -> str:
    lines = ["", f"  Skill fetch — {result.source_id}", ""]
    if not result.ok:
        lines.append(f"  Failed: {result.error}")
        lines.append("")
        return "\n".join(lines)

    state = "reused existing sandbox" if result.reused_existing else "cloned"
    lines.append(f"  {state}: {result.sandbox_dir}")
    lines.append(f"  Ephemeral: expires in {result.ttl_hours:g}h "
                 f"(manifest: {Path(result.manifest_path).name})")
    lines.append("")
    if result.skills:
        # A pack often ships the same skill in several packaged formats
        # (skills/, .claude/skills/, .agents/skills/). Listing each copy reads
        # as duplication, so group by name and report the copy count instead.
        grouped: dict[str, list[SkillDefinition]] = {}
        for skill in result.skills:
            grouped.setdefault(skill.name, []).append(skill)

        lines.append(f"  Skills read: {len(grouped)} distinct "
                     f"({result.skill_count} file(s) on disk)")
        lines.append("")
        for name in sorted(grouped):
            copies = grouped[name]
            suffix = f"   [{len(copies)} packaged formats]" if len(copies) > 1 else ""
            lines.append(f"    {name}{suffix}")
            description = next((c.description for c in copies if c.description), "")
            if description:
                summary = description[:110]
                ellipsis = "…" if len(description) > 110 else ""
                lines.append(f"        {summary}{ellipsis}")
        lines.append("")
    else:
        lines.append("  No SKILL.md files found in this pack.")
        lines.append("")
    lines.append("  Nothing was executed — content was read as text only.")
    lines.append("  Auto-Purge will remove this sandbox when its TTL expires.")
    lines.append("")
    return "\n".join(lines)
