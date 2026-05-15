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


def main():
    if len(sys.argv) < 2:
        print("Usage: genesis_subcommands.py check [project_dir]", file=sys.stderr)
        sys.exit(1)
    subcmd = sys.argv[1]
    if subcmd == "check":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_check(project_dir))
    else:
        print(f"Unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
