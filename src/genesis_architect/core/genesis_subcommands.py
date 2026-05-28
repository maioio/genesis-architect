"""Genesis Architect subcommands. Usage: python scripts/genesis_subcommands.py check [project_dir]"""
import sys
import json
import re
import urllib.request
import urllib.error
import os
import glob

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
    print(f"\n[genesis check] Summary:", file=sys.stderr)
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


def cmd_research(topic: str) -> int:
    """Stub: genesis research [topic] - planned for v2.5.0."""
    print(
        f"genesis research '{topic}': not yet implemented in this version.\n"
        "Planned for v2.5.0. Workaround: use `genesis resolve [topic]` for cached lookups\n"
        "or run a manual Exa/GitHub search from the Companion Mode session.",
        file=sys.stderr,
    )
    return 1


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
            "  research <topic>        [planned v2.6.0] ecosystem research for a topic\n"
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
