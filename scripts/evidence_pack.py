#!/usr/bin/env python3
"""
evidence_pack.py - Genesis Architect v2.5.0

Generates ARCHITECTURE_EVIDENCE.md from Phase 2-4 research outputs.
This file is the signed commitment to what was researched and decided.
Phase 6 cannot begin without it.

Usage:
    python scripts/evidence_pack.py generate --project-dir .
    python scripts/evidence_pack.py verify   --project-dir .
    python scripts/evidence_pack.py show     --project-dir .

The generator reads:
    RESEARCH.md      - repos analyzed, architecture rationale
    PITFALLS.md      - pitfalls, mitigations, mitigation_file_paths
    ROADMAP.md       - planned phases
    .genesis/phase-2-research.json  - research quality signal
    .genesis/phase-5-confirmed.json - user architecture choice

And produces:
    ARCHITECTURE_EVIDENCE.md  - human-readable, git-committable evidence pack
    .genesis/evidence.json    - machine-readable backing store for genesis validate
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_repos(research_text: str) -> list[dict]:
    """Extract repo table rows from RESEARCH.md Analyzed Repositories section."""
    repos: list[dict] = []
    in_table = False
    for line in research_text.splitlines():
        if "Analyzed Repositories" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("##"):
            break
        if not line.startswith("|"):
            continue
        # Skip separator rows (|---|---|) and header rows that contain no links
        if re.match(r"\|\s*[-:]+\s*\|", line):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        # Require a markdown link in column 0 to distinguish data rows from header text
        link_m = re.search(r"\[([^\]]+)\]\((https://[^)]+)\)", cols[0])
        if not link_m:
            continue
        name = link_m.group(1)
        url = link_m.group(2)
        repos.append({"name": name, "url": url, "stars": cols[1] if len(cols) > 1 else ""})
    return repos


def _parse_exec_summary(research_text: str) -> str:
    """Extract text under ## Executive Summary."""
    m = re.search(
        r"## Executive Summary\s*\n(.*?)(?=\n##|\Z)", research_text, re.DOTALL
    )
    return m.group(1).strip() if m else ""


def _parse_arch_rationale(research_text: str) -> str:
    """Extract text under ## Architecture Decision Rationale."""
    m = re.search(
        r"## Architecture Decision Rationale\s*\n(.*?)(?=\n##|\Z)", research_text, re.DOTALL
    )
    return m.group(1).strip() if m else ""


def _parse_pitfalls(pitfalls_text: str) -> list[dict]:
    """
    Parse all pitfalls from PITFALLS.md.

    Each returned dict:
        id, name, issue_url, frequency, root_cause, mitigation, mitigation_file_path
    """
    pitfalls: list[dict] = []
    sections = re.split(r"(?m)^## (Pitfall \d+[^\n]*)\n", pitfalls_text)
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        num_m = re.search(r"Pitfall\s+(\d+)", header, re.IGNORECASE)
        pid = f"pitfall_{num_m.group(1)}" if num_m else f"pitfall_{(i+1)//2}"
        name = re.sub(r"^Pitfall\s+\d+[:\s]*", "", header, flags=re.IGNORECASE).strip()

        url_m = re.search(r"https://github\.com/[^\s,)\]>\"']+/issues/\d+", body)
        freq_m = re.search(r"\*\*Frequency\*\*\s*:([^\n]+)", body)
        cause_m = re.search(r"\*\*(?:Root\s+)?[Cc]ause\*\*\s*:([^\n]+(?:\n(?!\*\*)[^\n]+)*)", body)
        mit_m = re.search(
            r"\*\*(?:Our\s+)?[Mm]itigation\*\*\s*:([^\n]+(?:\n(?!##|\*\*|mitigation_file_path)[^\n]+)*)",
            body,
        )
        path_m = re.search(r"mitigation_file_path\s*:\s*([^\n]+)", body)

        pitfalls.append({
            "id": pid,
            "name": name,
            "issue_url": url_m.group(0) if url_m else "",
            "frequency": freq_m.group(1).strip() if freq_m else "",
            "root_cause": cause_m.group(1).strip() if cause_m else "",
            "mitigation": mit_m.group(1).strip() if mit_m else "",
            "mitigation_file_path": path_m.group(1).strip() if path_m else "",
        })
    return pitfalls


def _parse_roadmap_phases(roadmap_text: str) -> list[dict]:
    """Extract phase names and first-line descriptions from ROADMAP.md."""
    phases: list[dict] = []
    sections = re.split(r"(?m)^## (Phase [^\n]+)\n", roadmap_text)
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
        phases.append({"name": header, "summary": first_line})
    return phases


def _load_phase5(genesis_dir: Path) -> dict:
    """Load phase-5-confirmed.json if present."""
    p = genesis_dir / "phase-5-confirmed.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_phase2(genesis_dir: Path) -> dict:
    """Load phase-2-research.json if present."""
    p = genesis_dir / "phase-2-research.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate(project_dir: str) -> int:
    """
    Read RESEARCH.md, PITFALLS.md, ROADMAP.md and .genesis/ state files.
    Write ARCHITECTURE_EVIDENCE.md and .genesis/evidence.json.
    Returns 0 on success, 1 on failure.
    """
    base = Path(project_dir).resolve()
    gdir = base / ".genesis"

    research_path = base / "RESEARCH.md"
    pitfalls_path = base / "PITFALLS.md"
    roadmap_path = base / "ROADMAP.md"

    missing = [p.name for p in [research_path, pitfalls_path, roadmap_path] if not p.exists()]
    if missing:
        print(
            f"ERROR: Cannot generate evidence pack - missing files: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    research_text = research_path.read_text(encoding="utf-8")
    pitfalls_text = pitfalls_path.read_text(encoding="utf-8")
    roadmap_text = roadmap_path.read_text(encoding="utf-8")

    repos = _parse_repos(research_text)
    exec_summary = _parse_exec_summary(research_text)
    arch_rationale = _parse_arch_rationale(research_text)
    pitfalls = _parse_pitfalls(pitfalls_text)
    roadmap_phases = _parse_roadmap_phases(roadmap_text)

    phase2 = _load_phase2(gdir)
    phase5 = _load_phase5(gdir)

    quality_label = "PARTIAL" if phase2.get("user_override") else (
        "FULL" if phase2.get("phase2_passed") else "THIN"
    )

    now = datetime.now(timezone.utc).isoformat()

    # Machine-readable backing store
    evidence: dict = {
        "generated_at": now,
        "project_dir": str(base),
        "research_quality": quality_label,
        "repo_count": phase2.get("repo_count", len(repos)),
        "deep_count": phase2.get("deep_count", 0),
        "repos": repos,
        "pitfalls": pitfalls,
        "roadmap_phases": roadmap_phases,
        "architecture_choice": phase5.get("user_choice", ""),
        "archetype": phase5.get("archetype", ""),
        "tier": phase5.get("tier", ""),
        "language": phase5.get("language", ""),
        "exec_summary": exec_summary,
        "arch_rationale": arch_rationale,
        "evidence_signed": False,  # set to True when user confirms in Phase 5
    }

    # Human-readable ARCHITECTURE_EVIDENCE.md
    md_lines: list[str] = [
        "# Architecture Evidence Pack",
        "<!-- Generated by Genesis Architect evidence_pack.py -->",
        f"<!-- Generated: {now} -->",
        "",
        "## Research Summary",
        "",
        f"**Research quality:** {quality_label}",
        f"**Repos scanned:** {evidence['repo_count']}",
        f"**Deep analyzed:** {evidence['deep_count']}",
        "",
    ]

    if exec_summary:
        md_lines += ["**Executive Summary:**", "", exec_summary, ""]

    # Repos table
    if repos:
        md_lines += [
            "## Repos Analyzed",
            "",
            "| Project | Stars | URL |",
            "|---|---|---|",
        ]
        for r in repos:
            link = f"[{r['name']}]({r['url']})" if r["url"] else r["name"]
            md_lines.append(f"| {link} | {r['stars']} | {r['url']} |")
        md_lines.append("")

    # Issues mined
    issue_urls = [p["issue_url"] for p in pitfalls if p["issue_url"]]
    if issue_urls:
        md_lines += ["## Issues Mined", ""]
        for url in issue_urls:
            md_lines.append(f"- {url}")
        md_lines.append("")

    # Recurring failure patterns (from pitfall names)
    if pitfalls:
        md_lines += ["## Recurring Failure Patterns", ""]
        for p in pitfalls:
            md_lines.append(f"- **{p['name']}**: {p['root_cause']}")
        md_lines.append("")

    # Architecture decision
    md_lines += ["## Selected Architecture Decision", ""]
    if phase5:
        md_lines += [
            f"**User choice:** {phase5.get('user_choice', 'not recorded')}",
            f"**Archetype:** {phase5.get('archetype', '')}",
            f"**Tier:** {phase5.get('tier', '')}",
            f"**Language:** {phase5.get('language', '')}",
            "",
        ]
    if arch_rationale:
        md_lines += [arch_rationale, ""]

    # Rejected alternatives - extracted from ADR rationale "Alternatives considered" pattern
    alt_m = re.search(
        r"(?:Alternatives considered|Rejected alternatives)[^\n]*\n(.*?)(?=\n##|\Z)",
        arch_rationale + "\n" + research_text,
        re.DOTALL | re.IGNORECASE,
    )
    if alt_m:
        md_lines += ["## Rejected Alternatives", "", alt_m.group(1).strip(), ""]

    # Risks and mitigations
    if pitfalls:
        md_lines += [
            "## Risks Found and Mitigations Added",
            "",
            "| # | Risk | Issue | Mitigation File | Status |",
            "|---|---|---|---|---|",
        ]
        for p in pitfalls:
            issue_link = f"[link]({p['issue_url']})" if p["issue_url"] else "none"
            mit_path = p["mitigation_file_path"] or "NOT MAPPED"
            status = "MAPPED" if p["mitigation_file_path"] else "MISSING"
            md_lines.append(
                f"| {p['id']} | {p['name']} | {issue_link} | `{mit_path}` | {status} |"
            )
        md_lines.append("")

    # Validations required
    md_lines += [
        "## Validations Required",
        "",
        "Run before every commit:",
        "",
        "```bash",
        "python scripts/genesis_subcommands.py validate .",
        "```",
        "",
        "This checks that every `mitigation_file_path` still exists in the project tree.",
        "Exit 1 blocks the commit. Fix the mitigation before proceeding.",
        "",
    ]

    # Roadmap
    if roadmap_phases:
        md_lines += ["## Roadmap Phases", ""]
        for ph in roadmap_phases:
            md_lines.append(f"- **{ph['name']}**: {ph['summary']}")
        md_lines.append("")

    md_lines += [
        "---",
        "",
        "_This file is generated by Genesis Architect. Do not edit manually._",
        "_Re-generate with: `python scripts/evidence_pack.py generate --project-dir .`_",
    ]

    # Write outputs
    gdir.mkdir(parents=True, exist_ok=True)

    evidence_md = base / "ARCHITECTURE_EVIDENCE.md"
    evidence_md.write_text("\n".join(md_lines), encoding="utf-8")

    evidence_json = gdir / "evidence.json"
    evidence_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"Evidence pack written: {evidence_md}")
    print(f"Machine store: {evidence_json}")
    print(
        f"Pitfalls: {len(pitfalls)} | "
        f"Mapped: {sum(1 for p in pitfalls if p['mitigation_file_path'])} | "
        f"Unmapped: {sum(1 for p in pitfalls if not p['mitigation_file_path'])}"
    )
    return 0


def verify(project_dir: str) -> int:
    """
    Verify that ARCHITECTURE_EVIDENCE.md and .genesis/evidence.json both exist
    and that no pitfall is unmapped.
    Returns 0 if valid, 1 if not.
    """
    base = Path(project_dir).resolve()
    evidence_md = base / "ARCHITECTURE_EVIDENCE.md"
    evidence_json = base / ".genesis" / "evidence.json"

    errors: list[str] = []

    if not evidence_md.exists():
        errors.append("ARCHITECTURE_EVIDENCE.md not found - run: python scripts/evidence_pack.py generate --project-dir .")
    if not evidence_json.exists():
        errors.append(".genesis/evidence.json not found - run: python scripts/evidence_pack.py generate --project-dir .")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        evidence = json.loads(evidence_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot read .genesis/evidence.json: {exc}", file=sys.stderr)
        return 1

    pitfalls = evidence.get("pitfalls", [])
    unmapped = [p for p in pitfalls if not p.get("mitigation_file_path")]
    if unmapped:
        print(
            f"ERROR: {len(unmapped)} pitfall(s) have no mitigation_file_path:",
            file=sys.stderr,
        )
        for p in unmapped:
            print(f"  - {p['id']}: {p['name']}", file=sys.stderr)
        print(
            "Fix: add 'mitigation_file_path: src/...' to each pitfall in PITFALLS.md, "
            "then re-run generate.",
            file=sys.stderr,
        )
        return 1

    print(f"Evidence pack valid: {len(pitfalls)} pitfall(s), all mapped.")
    return 0


def show(project_dir: str) -> int:
    """Print the evidence JSON to stdout."""
    evidence_json = Path(project_dir).resolve() / ".genesis" / "evidence.json"
    if not evidence_json.exists():
        print("ERROR: .genesis/evidence.json not found", file=sys.stderr)
        return 1
    print(evidence_json.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect - Architecture Evidence Pack generator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate ARCHITECTURE_EVIDENCE.md from research outputs")
    gen.add_argument("--project-dir", default=".", help="Project root directory")

    ver = sub.add_parser("verify", help="Verify evidence pack is present and complete")
    ver.add_argument("--project-dir", default=".", help="Project root directory")

    shw = sub.add_parser("show", help="Print evidence.json to stdout")
    shw.add_argument("--project-dir", default=".", help="Project root directory")

    args = parser.parse_args()

    if args.command == "generate":
        sys.exit(generate(args.project_dir))
    elif args.command == "verify":
        sys.exit(verify(args.project_dir))
    elif args.command == "show":
        sys.exit(show(args.project_dir))


if __name__ == "__main__":
    main()
