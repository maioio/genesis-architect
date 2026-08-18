"""Genesis Architect subcommands. Usage: python scripts/genesis_subcommands.py check [project_dir]"""
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Known-latest GitHub Actions major versions - update when actions release new majors
# Last verified: 2026-05-14
KNOWN_LATEST_ACTIONS = {
    "actions/checkout": "v6",
    "actions/setup-python": "v6",
    "actions/setup-node": "v4",
    "actions/setup-go": "v5",
    "actions/setup-java": "v4",
    "actions/upload-artifact": "v4",
    "actions/download-artifact": "v4",
    "actions/cache": "v4",
    "actions/github-script": "v7",
    "actions/stale": "v9",
    "docker/login-action": "v3",
    "docker/build-push-action": "v6",
}

# Dependency version patterns
DEP_PATTERN = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_\-\.]*)\s*(?:==|>=|~=|<=|!=|>|<)\s*(\d[\d\.]*)'
)

# GitHub Actions version pins: e.g. actions/checkout@v3
ACTION_PATTERN = re.compile(r'([\w\-]+/[\w\-]+)@(v\d+)')


def detect_ecosystem(project_dir):
    if os.path.exists(os.path.join(project_dir, "requirements.txt")) or \
       os.path.exists(os.path.join(project_dir, "setup.py")) or \
       os.path.exists(os.path.join(project_dir, "pyproject.toml")):
        return "PyPI"
    if os.path.exists(os.path.join(project_dir, "package.json")):
        return "npm"
    if os.path.exists(os.path.join(project_dir, "go.mod")):
        return "Go"
    if os.path.exists(os.path.join(project_dir, "Cargo.toml")):
        return "crates.io"
    return "PyPI"  # default


def extract_deps_from_research(research_path):
    """Extract pinned dependency versions from RESEARCH.md."""
    deps = {}
    try:
        with open(research_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return deps
    for m in DEP_PATTERN.finditer(content):
        name, version = m.group(1), m.group(2)
        deps[name] = version
    return deps


def query_osv(package_name, ecosystem):
    """Query OSV.dev for known vulnerabilities. Returns list of vuln dicts."""
    url = "https://api.osv.dev/v1/query"
    payload = json.dumps({"package": {"name": package_name, "ecosystem": ecosystem}}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("vulns", [])
    except (urllib.error.URLError, Exception):
        return []


def extract_fix_version(vuln):
    """Try to extract a fix version from OSV vuln record."""
    for affected in vuln.get("affected", []):
        for rng in affected.get("ranges", []):
            for evt in rng.get("events", []):
                if "fixed" in evt:
                    return evt["fixed"]
    return None


def check_actions(project_dir):
    """Scan .github/workflows/*.yml for outdated action pins."""
    warnings = []
    pattern = os.path.join(project_dir, ".github", "workflows", "*.yml")
    for wf_file in glob.glob(pattern):
        try:
            with open(wf_file, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        for m in ACTION_PATTERN.finditer(content):
            action, current = m.group(1), m.group(2)
            latest = KNOWN_LATEST_ACTIONS.get(action)
            if latest and current != latest:
                # Compare major version numbers
                try:
                    cur_major = int(current.lstrip("v").split(".")[0])
                    lat_major = int(latest.lstrip("v").split(".")[0])
                    if lat_major > cur_major:
                        warnings.append({
                            "type": "action_version",
                            "action": action,
                            "current": current,
                            "latest": latest,
                            "file": os.path.relpath(wf_file, project_dir),
                        })
                except ValueError:
                    pass
    return warnings


def cmd_check(project_dir):
    project_dir = os.path.abspath(project_dir)
    research_path = os.path.join(project_dir, "RESEARCH.md")
    ecosystem = detect_ecosystem(project_dir)

    print(f"[genesis check] project: {project_dir}", file=sys.stderr)
    print(f"[genesis check] ecosystem: {ecosystem}", file=sys.stderr)

    deps = extract_deps_from_research(research_path)
    if not deps:
        print("[genesis check] No pinned dependencies found in RESEARCH.md", file=sys.stderr)
    else:
        print(f"[genesis check] Found {len(deps)} pinned deps: {', '.join(deps)}", file=sys.stderr)

    critical = []
    info = []

    for pkg, version in deps.items():
        vulns = query_osv(pkg, ecosystem)
        for v in vulns:
            cve_ids = [a for a in v.get("aliases", []) if a.startswith("CVE-")]
            cve = cve_ids[0] if cve_ids else v.get("id", "UNKNOWN")
            fix = extract_fix_version(v)
            critical.append({
                "type": "cve",
                "package": pkg,
                "pinned_version": version,
                "cve": cve,
                "fix": fix,
            })

    if not critical:
        info.append({"type": "info", "message": f"No CVEs found for {len(deps)} deps via OSV.dev"})

    warnings = check_actions(project_dir)

    result = {"critical": critical, "warnings": warnings, "info": info}
    print(json.dumps(result, indent=2))

    # Human-readable stderr summary
    print("\n[genesis check] Summary:", file=sys.stderr)
    print(f"  Critical (CVEs): {len(critical)}", file=sys.stderr)
    print(f"  Warnings (actions): {len(warnings)}", file=sys.stderr)
    for w in warnings:
        print(f"    {w['action']}@{w['current']} -> {w['latest']} ({w['file']})", file=sys.stderr)
    for c in critical:
        print(f"    {c['package']} {c['cve']} fix={c['fix']}", file=sys.stderr)

    return 1 if critical else 0


def cmd_validate(project_dir: str, json_output: bool = False) -> int:
    """
    genesis validate [project_dir]

    Hard enforcement of mitigation_file_path rules from PITFALLS.md.
    Exits 1 if any required mitigation file is missing.
    Also verifies ARCHITECTURE_EVIDENCE.md is present.

    This replaces the advisory pitfall_coverage_check.py (Step 6.5) with a
    blocking check. Both still run in CI - this one gates the commit.
    """
    import subprocess

    project_dir = os.path.abspath(project_dir)
    pitfalls_md = os.path.join(project_dir, "PITFALLS.md")
    enforcer = os.path.join(os.path.dirname(__file__), "mitigation_enforcer.py")
    evidence_verify = os.path.join(os.path.dirname(__file__), "evidence_pack.py")

    errors: list[str] = []

    # Step 1: verify evidence pack exists
    if not os.path.exists(os.path.join(project_dir, "ARCHITECTURE_EVIDENCE.md")):
        errors.append(
            "ARCHITECTURE_EVIDENCE.md missing - run: "
            "python -m genesis_architect.core.evidence_pack generate --project-dir ."
        )

    # Step 2: run evidence_pack verify
    try:
        ev_result = subprocess.run(
            [sys.executable, evidence_verify, "verify", "--project-dir", project_dir],
            capture_output=True, text=True,
        )
        if ev_result.returncode != 0:
            errors.append(f"Evidence pack verify failed:\n{ev_result.stderr.strip()}")
    except Exception as exc:
        errors.append(f"Could not run evidence_pack.py verify: {exc}")

    # Step 3: run mitigation_enforcer (hard check - file existence, not keyword grep)
    if os.path.exists(pitfalls_md):
        flags = ["--json"] if json_output else []
        try:
            me_result = subprocess.run(
                [sys.executable, enforcer, pitfalls_md,
                 "--src-root", project_dir] + flags,
                capture_output=True, text=True,
            )
            if json_output and me_result.stdout:
                print(me_result.stdout)
            if me_result.stderr:
                print(me_result.stderr, file=sys.stderr, end="")
            if me_result.returncode != 0:
                errors.append("Mitigation enforcement failed - see details above.")
        except Exception as exc:
            errors.append(f"Could not run mitigation_enforcer.py: {exc}")
    else:
        errors.append(f"PITFALLS.md not found at {pitfalls_md}")

    if errors:
        print(f"\ngenesis validate: FAILED ({len(errors)} issue(s))", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("genesis validate: PASSED", file=sys.stderr)
    return 0


# The collection guide has to be a complete contract, not a list of topics.
# A caller that cannot read research_orchestrator.py has no other way to learn
# the field names, and a caller that guesses them fails silently: unknown keys
# are ignored, so a wrong shape looks like "no results found". Every field the
# orchestrator reads appears here, with one filled example per stream.
RESEARCH_SCHEMA = {
    "repos": [
        {
            "slug": "encode/httpx",
            "stars": 14200,
            "url": "https://github.com/encode/httpx",
            "description": "A next-generation HTTP client for Python.",
            "deep_analyzed": True,
        }
    ],
    "github_issues": [
        {
            "title": "Connection pool exhausted under sustained load",
            "url": "https://github.com/encode/httpx/issues/1234",
            "body": "After ~500 concurrent requests the pool stops handing out "
                    "connections and every call times out at 5s.",
            "comments": 23,
            "reactions": 8,
            "category": "pitfall",
            "created_at": "2026-02-11",
        }
    ],
    "web_results": [
        {
            "title": "What we learned running httpx in production for two years",
            "url": "https://community.example.org/t/httpx-in-production/812",
            "text": "The default 5s timeout is too low once you add retries; "
                    "we measured p99 at 7400ms under load.",
            "provider": "tavily",
            "published_date": "2026-01-30",
            "relevance": 0.87,
            "comments": 41,
        }
    ],
    "media_results": [
        {
            "title": "Scaling Python HTTP clients - lessons learned",
            "url": "https://www.youtube.com/watch?v=EXAMPLE",
            "text": "Conference talk on connection pooling mistakes.",
            "channel": "PyCon",
            "provider": "exa",
            "published_date": "2025-10-04",
        }
    ],
}

# Only these keys are read. Anything else in the file is ignored silently, so
# the guide states the whole set rather than leaving it to be discovered.
RESEARCH_STREAM_DOCS = (
    ("repos", "A", "GitHub repos matching the vision",
     "slug, stars, url, description, deep_analyzed"),
    ("github_issues", "C", "issues mined from the top repos",
     "title, url, body, comments, reactions, category, created_at"),
    ("web_results", "B", "web/ecosystem signals (any provider)",
     "title, url, text, provider, published_date, relevance, comments"),
    ("media_results", "D", "conference talks / video / social lessons-learned",
     "title, url, text, channel, provider, published_date"),
)

# Field-level notes for the fields where a wrong guess is silently costly.
RESEARCH_FIELD_NOTES = (
    "stars           omit entirely if the source did not report a count. "
    "0 means 'zero stars', not 'unknown'.",
    "deep_analyzed   true only if you actually read the repo (README + source), "
    "not if it merely appeared in search results. The research floor counts these.",
    "relevance       the provider's own 0.0-1.0 query-match score. Never put it in "
    "`comments` - relevance is not human attention and is not scored as such.",
    "comments        real human counts only (comments, replies, upvotes). "
    "Omit when the source reports none.",
    "published_date  any ISO-8601 form (2026-01-30 or 2026-01-30T12:00:00Z). "
    "Without it a result earns no recency points at all.",
    "provider        which tool actually fetched this item (exa, tavily, "
    "firecrawl, ...). The stream is provider-neutral; the item records its own.",
)


def _research_guide(topic: str) -> str:
    """The full collection contract: schema, per-field notes, and the next command."""
    import json

    lines = [
        f"\n:: Genesis Research: {topic}\n",
        "No cached research found. The orchestrator needs raw data from four",
        "streams. Collect them in a Claude/Codex session, save as JSON, then:\n",
        f'    genesis research "{topic}" --json-data research_data.json\n',
        "Streams (JSON keys):",
    ]
    for key, letter, purpose, fields in RESEARCH_STREAM_DOCS:
        lines.append(f"  {letter}. {key:<14} - {purpose}")
        lines.append(f"     {'':14}   fields: {fields}")
    lines.append("")
    lines.append("Exact shape expected in research_data.json (one filled example each):")
    lines.append("")
    lines.append(json.dumps(RESEARCH_SCHEMA, indent=2))
    lines.append("")
    lines.append("Field notes:")
    for note in RESEARCH_FIELD_NOTES:
        lines.append(f"  {note}")
    lines.append("")
    lines.append("Legacy keys `exa_results` and `video_exa_results` are still accepted")
    lines.append("and map to `web_results` and `media_results`.")
    lines.append("")
    lines.append("Closing the video loop: after running /watch on a talk the summary")
    lines.append("recommends, feed the analysis back in with")
    lines.append(f'    genesis research "{topic}" --absorb watch-output.txt')
    lines.append("which extracts pitfalls from it and appends them to PITFALLS.md.")
    lines.append("")
    lines.append("Add --json to any of the above to get the summary as JSON instead")
    lines.append("of formatted text.")
    lines.append("")
    return "\n".join(lines)


def _emit_summary(orchestrator, summary, json_output: bool) -> None:
    """Print a ResearchSummary as JSON or as the formatted human summary."""
    import json

    if json_output:
        print(json.dumps(summary.to_dict(), indent=2, default=str))
    else:
        print(orchestrator.format_summary(summary))


def _sniff_source_url(text: str) -> str:
    """First http(s) URL in the /watch output, used when --source-url is omitted."""
    match = re.search(r"https?://[^\s\"'<>)\]]+", text)
    return match.group(0) if match else ""


def cmd_research(
    topic: str,
    json_data: str | None = None,
    absorb: str | None = None,
    source_url: str | None = None,
    json_output: bool = False,
    domain: str | None = None,
) -> int:
    """Multi-source research via the Pro orchestrator.

    1. ``--absorb FILE`` closes the video loop: extract pitfalls from a /watch
       analysis and append them to PITFALLS.md.
    2. Look up the vault cache (returns immediately on a hit).
    3. If ``json_data`` points at a JSON file with pre-collected streams,
       merge/rank/summarise it through the orchestrator.
    4. Otherwise, print the data-collection guide - schema included - so the
       caller can gather the four streams and re-run with --json-data.
    """
    import json
    from pathlib import Path

    from genesis_architect.core import pro_bridge

    try:
        orchestrator = pro_bridge.get_pro_module("research_orchestrator")
    except pro_bridge.ProUnavailable as exc:
        # Not a paywall - the engines ship in this package, so this only fires
        # on a broken or partial install.
        print(f"genesis research '{topic}': {exc}", file=sys.stderr)
        return 2

    cwd = Path.cwd()

    # --- absorb /watch output back into PITFALLS.md ---
    if absorb:
        return _cmd_research_absorb(
            topic, absorb, source_url, json_output, cwd, pro_bridge
        )

    # --- vault cache lookup ---
    cached = orchestrator.load_from_vault(topic, cwd)
    if cached is not None:
        _emit_summary(orchestrator, cached, json_output)
        return 0

    # --- process pre-collected data ---
    if json_data:
        data_path = Path(json_data)
        if not data_path.exists():
            print(f"File not found: {json_data}", file=sys.stderr)
            return 1
        try:
            # utf-8-sig tolerates a BOM, which Windows editors (and
            # PowerShell's Out-File -Encoding utf8) prepend.
            raw = json.loads(data_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in {json_data}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(raw, dict):
            print(
                f"{json_data} must contain a JSON object with the four stream keys "
                f"({', '.join(k for k, *_ in RESEARCH_STREAM_DOCS)}), "
                f"not a {type(raw).__name__}.",
                file=sys.stderr,
            )
            return 1

        streams = orchestrator.normalize_streams(raw)
        unknown = sorted(set(streams) - {k for k, *_ in RESEARCH_STREAM_DOCS})
        if unknown and not json_output:
            # Unknown keys are ignored by the orchestrator. Saying so out loud
            # is the difference between a typo and an afternoon of confusion.
            print(
                f"Note: ignoring unrecognised key(s): {', '.join(unknown)}. "
                f'Run `genesis research "{topic}"` with no arguments to see the '
                f"expected schema.",
                file=sys.stderr,
            )

        summary = orchestrator.build_summary_from_raw(
            vision=topic,
            repos=streams.get("repos", []),
            github_issues=streams.get("github_issues", []),
            web_results=streams.get("web_results", []),
            media_results=streams.get("media_results", []),
            project_root=cwd,
            domain=(domain or "").replace("-", "_"),
        )
        _emit_summary(orchestrator, summary, json_output)
        return 0

    # --- no cache, no data: print the collection guide ---
    if json_output:
        print(json.dumps({
            "topic": topic,
            "status": "no_data",
            "next_command": f'genesis research "{topic}" --json-data research_data.json',
            "absorb_command": f'genesis research "{topic}" --absorb watch-output.txt',
            "schema": RESEARCH_SCHEMA,
            "streams": [
                {"key": key, "stream": letter, "purpose": purpose,
                 "fields": fields.split(", ")}
                for key, letter, purpose, fields in RESEARCH_STREAM_DOCS
            ],
            "field_notes": list(RESEARCH_FIELD_NOTES),
            "legacy_key_aliases": {"exa_results": "web_results",
                                   "video_exa_results": "media_results"},
        }, indent=2))
        return 0

    print(_research_guide(topic))
    return 0


def _cmd_research_absorb(topic, absorb, source_url, json_output, cwd, pro_bridge) -> int:
    """`genesis research <topic> --absorb FILE` - the return leg of the video loop.

    Stream D hands back /watch commands, and without this there was no way to
    feed a watched talk's findings back in: the engine existed, but the CLI
    never named the command that closes the circle.
    """
    import json
    from pathlib import Path

    try:
        pipeline = pro_bridge.get_pro_module("video_to_pitfall")
    except pro_bridge.ProUnavailable as exc:
        print(f"genesis research --absorb: {exc}", file=sys.stderr)
        return 2

    watch_path = Path(absorb)
    if not watch_path.exists():
        print(f"File not found: {absorb}", file=sys.stderr)
        return 1
    watch_text = watch_path.read_text(encoding="utf-8-sig", errors="replace")

    resolved_url = source_url or _sniff_source_url(watch_text)
    if not resolved_url:
        print(
            f"Could not find a source URL in {absorb} and --source-url was not given. "
            f"Every extracted pitfall must cite where it came from, so this stops "
            f"rather than writing uncited entries.",
            file=sys.stderr,
        )
        return 1

    entries = pipeline.extract_from_watch_output(watch_text, resolved_url, topic)
    pitfalls_path = cwd / "PITFALLS.md"
    appended = pipeline.append_to_pitfalls_md(entries, pitfalls_path)

    if json_output:
        print(json.dumps({
            "topic": topic,
            "source_url": resolved_url,
            "absorbed_from": str(watch_path),
            "pitfalls_appended": appended,
            "pitfalls_file": str(pitfalls_path),
            "entries": [e.__dict__ for e in entries],
        }, indent=2, default=str))
        return 0

    print(f"\n:: Absorbed /watch analysis of {resolved_url}\n")
    print(pipeline.summarize_extraction(entries, resolved_url))
    if appended:
        print(f"\nAppended {appended} pitfall(s) to {pitfalls_path}")
    print()
    return 0


def cmd_harden(project_dir: str) -> int:
    """Stub: genesis harden [path] - planned for v2.5.0."""
    print(
        f"genesis harden '{project_dir}': not yet implemented as a standalone subcommand.\n"
        "Planned for v2.5.0. Workaround: invoke the `genesis harden` skill directly\n"
        "in a Claude session with the target directory as context.",
        file=sys.stderr,
    )
    return 1


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: genesis_subcommands.py <subcommand> [args]\n"
            "Subcommands:\n"
            "  check    [project_dir]  CVE scan + CI action version audit\n"
            "  validate [project_dir]  Hard enforcement: evidence pack + mitigation files\n"
            "  research <topic>        multi-source research (Pro) or vault lookup\n"
            "  harden   [project_dir]  [planned v2.6.0] security and quality upgrade",
            file=sys.stderr,
        )
        sys.exit(1)
    subcmd = sys.argv[1]
    if subcmd == "check":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_check(project_dir))
    elif subcmd == "validate":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        json_out = "--json" in sys.argv
        sys.exit(cmd_validate(project_dir, json_output=json_out))
    elif subcmd == "research":
        topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not topic:
            print("Usage: genesis_subcommands.py research <topic>", file=sys.stderr)
            sys.exit(1)
        sys.exit(cmd_research(topic))
    elif subcmd == "harden":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_harden(project_dir))
    else:
        print(f"Unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
