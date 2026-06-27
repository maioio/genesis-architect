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


def cmd_research(topic: str) -> int:
    """Stub: genesis research [topic] - planned for v2.5.0."""
    print(
        f"genesis research '{topic}': not yet implemented in this version.\n"
        "Planned for v2.5.0. Workaround: use `genesis resolve [topic]` for cached lookups\n"
        "or run a manual Exa/GitHub search from the Companion Mode session.",
        file=sys.stderr,
    )
    return 1


def cmd_score(project_dir: str, profile: str | None = None,
              json_output: bool = False, rebuild: bool = False) -> int:
    """
    genesis score [project_dir]

    Compute 0-100 architecture score across modularity, coupling, cohesion, layering.
    Appends result to .genesis/score_history.jsonl.
    """
    from genesis_architect.core.architecture_scorer import (
        score_project, append_score_history, print_score_report, score_label
    )

    project_dir = os.path.abspath(project_dir)
    print(f"[genesis score] analysing: {project_dir}", file=sys.stderr)

    try:
        result = score_project(project_dir, profile=profile, rebuild_graph=rebuild)
    except Exception as exc:
        print(f"[genesis score] ERROR: {exc}", file=sys.stderr)
        return 1

    append_score_history(project_dir, result)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print_score_report(result, project_dir)

    return 0 if result["total"] >= 50 else 1


def cmd_antipattern(project_dir: str, json_output: bool = False,
                    rebuild: bool = False) -> int:
    """
    genesis antipattern [project_dir]

    Detect structural anti-patterns: god class, hub file, circular deps,
    dead code, feature envy, leaky abstractions, shotgun surgery.
    """
    from genesis_architect.core.antipattern_detector import detect_all, print_report

    project_dir = os.path.abspath(project_dir)
    print(f"[genesis antipattern] analysing: {project_dir}", file=sys.stderr)

    try:
        report = detect_all(project_dir, rebuild_graph=rebuild)
    except Exception as exc:
        print(f"[genesis antipattern] ERROR: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    return 1 if report.critical_count > 0 else 0


def cmd_recover(project_dir: str, json_output: bool = False) -> int:
    """
    genesis recover [project_dir]

    Full project intelligence engine. Read-only analysis producing:
      - Architecture score (0-100)
      - Anti-pattern report
      - Fragility map (STABLE/FRAGILE/VOLATILE per module)
      - Refactoring plan (executable steps)
      - PROJECT_RECOVERY_REPORT.md
      - FRAGILITY_MAP.md
      - REFACTORING_PLAN.md

    Strictly read-only: no code changes, no files modified except outputs.
    """
    import subprocess
    from genesis_architect.core.architecture_scorer import score_project, append_score_history, score_label
    from genesis_architect.core.antipattern_detector import detect_all
    from genesis_architect.core.fragility_classifier import classify_all, write_fragility_map
    from genesis_architect.core.refactoring_planner import generate_plan, write_refactoring_plan_md
    from genesis_architect.core.import_graph import build_graph

    project_dir = os.path.abspath(project_dir)
    root_path = __import__("pathlib").Path(project_dir)

    print(f"[genesis recover] Phase 1: scanning {project_dir}", file=sys.stderr)

    errors: list[str] = []

    # Phase 1: Build import graph (foundation for everything)
    print("[genesis recover] Building import graph...", file=sys.stderr)
    try:
        graph = build_graph(project_dir, save=True)
        module_count = graph.get("module_count", 0)
        cycle_count = graph.get("cycle_count", 0)
        dark_count = len(graph.get("dark_modules", []))
        print(f"  Modules: {module_count}  Cycles: {cycle_count}  Dark: {dark_count}",
              file=sys.stderr)
    except Exception as exc:
        errors.append(f"Import graph failed: {exc}")
        graph = {}

    # Architecture score
    print("[genesis recover] Computing architecture score...", file=sys.stderr)
    score_result: dict = {}
    try:
        score_result = score_project(project_dir)
        append_score_history(project_dir, score_result)
        total = score_result["total"]
        label = score_label(total)
        print(f"  Score: {total}/100  [{label}]", file=sys.stderr)
    except Exception as exc:
        errors.append(f"Scoring failed: {exc}")

    # Anti-pattern detection
    print("[genesis recover] Detecting anti-patterns...", file=sys.stderr)
    ap_report = None
    try:
        ap_report = detect_all(project_dir)
        print(f"  CRITICAL: {ap_report.critical_count}  HIGH: {ap_report.high_count}  "
              f"MEDIUM: {ap_report.medium_count}  LOW: {ap_report.low_count}",
              file=sys.stderr)
    except Exception as exc:
        errors.append(f"Anti-pattern detection failed: {exc}")

    # Fragility classification
    print("[genesis recover] Classifying module fragility...", file=sys.stderr)
    frag_report = None
    try:
        frag_report = classify_all(project_dir)
        print(f"  VOLATILE: {frag_report.volatile_count}  FRAGILE: {frag_report.fragile_count}  "
              f"STABLE: {frag_report.stable_count}", file=sys.stderr)
    except Exception as exc:
        errors.append(f"Fragility classification failed: {exc}")

    # Refactoring plan
    print("[genesis recover] Generating refactoring plan...", file=sys.stderr)
    refactor_plan = None
    try:
        refactor_plan = generate_plan(project_dir)
        print(f"  Steps: {len(refactor_plan.steps)}  Score impact: +{refactor_plan.total_score_impact} pts",
              file=sys.stderr)
    except Exception as exc:
        errors.append(f"Refactoring plan failed: {exc}")

    # Phase 3: Write output files
    print("[genesis recover] Phase 3: writing output files...", file=sys.stderr)

    # Write FRAGILITY_MAP.md
    if frag_report:
        try:
            fragility_path = root_path / "FRAGILITY_MAP.md"
            write_fragility_map(frag_report, fragility_path)
            print(f"  Written: FRAGILITY_MAP.md", file=sys.stderr)
        except Exception as exc:
            errors.append(f"FRAGILITY_MAP.md write failed: {exc}")

    # Write REFACTORING_PLAN.md
    if refactor_plan:
        try:
            plan_path = root_path / "REFACTORING_PLAN.md"
            write_refactoring_plan_md(refactor_plan, plan_path)
            print(f"  Written: REFACTORING_PLAN.md", file=sys.stderr)
        except Exception as exc:
            errors.append(f"REFACTORING_PLAN.md write failed: {exc}")

    # Write PROJECT_RECOVERY_REPORT.md
    try:
        _write_recovery_report(
            root_path, score_result, ap_report, frag_report, refactor_plan,
            graph, errors,
        )
        print("  Written: PROJECT_RECOVERY_REPORT.md", file=sys.stderr)
    except Exception as exc:
        errors.append(f"PROJECT_RECOVERY_REPORT.md write failed: {exc}")

    if json_output:
        output = {
            "score": score_result,
            "anti_patterns": ap_report.to_dict() if ap_report else {},
            "fragility": frag_report.to_dict() if frag_report else {},
            "refactoring_plan": refactor_plan.to_dict() if refactor_plan else {},
            "errors": errors,
        }
        print(json.dumps(output, indent=2))
    else:
        _print_recovery_summary(score_result, ap_report, frag_report, refactor_plan, errors)

    return 1 if errors else 0


def _write_recovery_report(
    root: "__import__('pathlib').Path",
    score: dict,
    ap_report,
    frag_report,
    refactor_plan,
    graph: dict,
    errors: list[str],
) -> None:
    """Write PROJECT_RECOVERY_REPORT.md."""
    from genesis_architect.core.architecture_scorer import score_label
    from pathlib import Path

    root = Path(str(root))
    total = score.get("total", 0)
    label = score_label(total)
    project_name = root.name.replace("-", " ").replace("_", " ").title()

    lines = [
        "# Project Recovery Report",
        f"<!-- Generated by Genesis Architect PRO genesis_subcommands.py -->",
        f"<!-- Project: {project_name} -->",
        "",
        f"## Architecture Health Score: {total}/100 [{label}]",
        "",
        f"| Dimension | Score |",
        f"|-----------|-------|",
        f"| Modularity | {score.get('modularity', 0):.1f}/100 |",
        f"| Coupling | {score.get('coupling', 0):.1f}/100 |",
        f"| Cohesion | {score.get('cohesion', 0):.1f}/100 |",
        f"| Layering | {score.get('layering', 0):.1f}/100 |",
        f"| Cycle penalty | -{score.get('cycle_penalty', 0):.1f} pts |",
        "",
        f"**Profile:** {score.get('profile', 'default')}  |  "
        f"**Language:** {score.get('language', 'unknown')}  |  "
        f"**Modules:** {score.get('module_count', graph.get('module_count', 0))}  |  "
        f"**Cycles:** {score.get('cycle_count', graph.get('cycle_count', 0))}",
        "",
    ]

    # Anti-pattern summary
    if ap_report:
        lines += [
            "## Anti-Pattern Summary",
            "",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| CRITICAL | {ap_report.critical_count} |",
            f"| HIGH | {ap_report.high_count} |",
            f"| MEDIUM | {ap_report.medium_count} |",
            f"| LOW | {ap_report.low_count} |",
            f"| Total | {len(ap_report.patterns)} |",
            "",
        ]
        if ap_report.patterns:
            lines += ["**Top issues:**", ""]
            for p in ap_report.patterns[:8]:
                lines.append(f"- [{p.severity}] `{p.file}`: {p.description[:80]}")
            lines.append("")

    # Fragility summary
    if frag_report:
        volatile = [c for c in frag_report.classifications if c.status == "VOLATILE"]
        lines += [
            "## Module Risk Classification",
            "",
            f"| Status | Count | Action |",
            f"|--------|-------|--------|",
            f"| VOLATILE | {frag_report.volatile_count} | Do not modify without full test coverage |",
            f"| FRAGILE | {frag_report.fragile_count} | Add tests before modifying |",
            f"| STABLE | {frag_report.stable_count} | Safe to change |",
            "",
            "See `FRAGILITY_MAP.md` for full module breakdown.",
            "",
        ]
        if volatile:
            lines += ["**VOLATILE modules (highest risk):**", ""]
            for c in volatile[:6]:
                reasons = "; ".join(c.reasons[:1])
                lines.append(f"- `{c.module}` [{c.go_hold_rewrite}]: {reasons}")
            lines.append("")

    # Recovery sequence
    if refactor_plan and refactor_plan.steps:
        lines += [
            "## Recommended Recovery Sequence",
            "",
            f"Estimated score improvement: +{refactor_plan.total_score_impact} pts",
            "",
            "| Priority | Step | Rule | Impact |",
            "|----------|------|------|--------|",
        ]
        for step in refactor_plan.steps[:10]:
            tier_str = "**CRITICAL**" if step.tier == 1 else "important"
            lines.append(
                f"| {tier_str} | {step.title[:50]} | {step.rule} | +{step.score_impact} pts |"
            )
        lines += ["", "See `REFACTORING_PLAN.md` for full execution steps.", ""]

    # Quick wins
    dark = graph.get("dark_modules", [])
    if dark:
        lines += [
            "## Quick Wins",
            "",
            f"**Dead code candidates** (fan_in=0, not entry points): {len(dark)} files",
        ]
        for d in dark[:5]:
            lines.append(f"- `{d}` - verify unused then delete")
        lines += ["", ""]

    # Do-not-touch zones
    if frag_report:
        volatile_mods = [c.module for c in frag_report.classifications
                        if c.status == "VOLATILE" and c.go_hold_rewrite == "REWRITE"]
        if volatile_mods:
            lines += [
                "## Do-Not-Touch-Yet Risk Zones",
                "",
                "These modules require a full rewrite plan before any changes:",
                "",
            ]
            for m in volatile_mods[:5]:
                lines.append(f"- `{m}` - REWRITE candidate")
            lines.append("")

    # Errors
    if errors:
        lines += ["## Warnings During Analysis", ""]
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    lines += [
        "---",
        "",
        "_Generated by Genesis Architect PRO. Refresh with: `genesis recover [path]`_",
        "_Review FRAGILITY_MAP.md and REFACTORING_PLAN.md for detailed guidance._",
    ]

    (root / "PROJECT_RECOVERY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _print_recovery_summary(score, ap_report, frag_report, refactor_plan, errors) -> None:
    from genesis_architect.core.architecture_scorer import score_label
    total = score.get("total", 0) if score else 0
    label = score_label(total) if score else "UNKNOWN"
    print(f"\nGenesis Recover Complete")
    print(f"  Architecture Score: {total}/100 [{label}]")
    if ap_report:
        print(f"  Anti-patterns: CRITICAL={ap_report.critical_count} HIGH={ap_report.high_count}")
    if frag_report:
        print(f"  Fragility: VOLATILE={frag_report.volatile_count} FRAGILE={frag_report.fragile_count} STABLE={frag_report.stable_count}")
    if refactor_plan:
        print(f"  Refactoring steps: {len(refactor_plan.steps)} (+{refactor_plan.total_score_impact} pts potential)")
    print("\nOutput files written:")
    print("  PROJECT_RECOVERY_REPORT.md")
    print("  FRAGILITY_MAP.md")
    print("  REFACTORING_PLAN.md")
    if errors:
        print(f"\nWarnings ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")


def cmd_harden(project_dir: str) -> int:
    """
    genesis harden [project_dir]

    Security and quality upgrade:
      1. Inject secrets-scanning workflow if missing
      2. Inject SAST workflow if missing
      3. Harden .gitignore
      4. Scan src/ for hardcoded secret patterns
      5. Generate STRIDE_ANALYSIS.md
      6. Generate OWASP_CHECKLIST.md
    """
    from genesis_architect.core.security_templates import generate_security_docs
    from pathlib import Path as _Path

    project_dir = os.path.abspath(project_dir)
    root = _Path(project_dir)
    print(f"[genesis harden] hardening: {project_dir}", file=sys.stderr)

    results: list[str] = []
    warnings: list[str] = []

    # 1. Generate STRIDE + OWASP
    try:
        docs = generate_security_docs(project_dir)
        for name, path in docs.items():
            results.append(f"Generated: {path}")
    except Exception as exc:
        warnings.append(f"Security docs failed: {exc}")

    # 2. Harden .gitignore
    gitignore_path = root / ".gitignore"
    REQUIRED_GITIGNORE = [
        ".env", ".env.*", "!.env.example",
        "*.pem", "*.key", "*.p12",
        "venv/", "node_modules/", "__pycache__/",
        ".secrets", "secrets/",
    ]
    try:
        existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
        additions = [line for line in REQUIRED_GITIGNORE if line not in existing]
        if additions:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n# Genesis Architect security additions\n")
                for line in additions:
                    f.write(line + "\n")
            results.append(f"Hardened .gitignore (+{len(additions)} entries)")
        else:
            results.append(".gitignore already hardened")
    except Exception as exc:
        warnings.append(f".gitignore update failed: {exc}")

    # 3. Scan for hardcoded secret patterns
    SECRET_PATTERN = re.compile(
        r'(?:password|secret|api_key|apikey|token|passwd)\s*=\s*["\'][A-Za-z0-9+/=_\-]{8,}["\']',
        re.IGNORECASE,
    )
    secret_hits: list[str] = []
    src_root = root / "src"
    if src_root.exists():
        for py_file in src_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for lineno, line in enumerate(content.splitlines(), 1):
                    if SECRET_PATTERN.search(line) and "example" not in str(py_file).lower():
                        rel = str(py_file.relative_to(root)).replace("\\", "/")
                        secret_hits.append(f"{rel}:{lineno}: {line.strip()[:60]}")
            except OSError:
                pass

    # 4. Inject CI workflows if missing
    workflow_dir = root / ".github" / "workflows"
    injected_workflows: list[str] = []

    # Secrets scan workflow
    secrets_wf = workflow_dir / "secrets-scan.yml"
    if not secrets_wf.exists():
        workflow_dir.mkdir(parents=True, exist_ok=True)
        secrets_wf.write_text(_SECRETS_SCAN_WORKFLOW, encoding="utf-8")
        injected_workflows.append("secrets-scan.yml")

    # SAST workflow
    sast_wf = workflow_dir / "sast.yml"
    if not sast_wf.exists():
        sast_wf.write_text(_SAST_WORKFLOW, encoding="utf-8")
        injected_workflows.append("sast.yml")

    if injected_workflows:
        results.extend([f"Injected workflow: {w}" for w in injected_workflows])

    # Report
    print(f"\n[genesis harden] Complete")
    print(f"\nInjected / Updated:")
    for r in results:
        print(f"  + {r}")
    if secret_hits:
        print(f"\nHardcoded secret candidates found ({len(secret_hits)}):")
        for h in secret_hits[:8]:
            print(f"  ! {h}")
        print("  Action: move these values to .env and read via os.getenv()")
    else:
        print("\nNo hardcoded secret patterns found.")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")

    return 1 if secret_hits else 0


_SECRETS_SCAN_WORKFLOW = """\
name: secrets-scan
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
"""

_SAST_WORKFLOW = """\
name: sast
on: [push, pull_request]
jobs:
  codeql:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: python
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
"""


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: genesis_subcommands.py <subcommand> [args]\n"
            "Subcommands:\n"
            "  check       [project_dir]           CVE scan + CI action version audit\n"
            "  validate    [project_dir]            Hard enforcement: evidence pack + mitigation files\n"
            "  score       [project_dir]            Architecture score 0-100 (4 dimensions)\n"
            "  antipattern [project_dir]            Detect structural anti-patterns\n"
            "  recover     [project_dir]            Full project intelligence + recovery plan\n"
            "  harden      [project_dir]            Security hardening: STRIDE, OWASP, workflows\n"
            "  research    <topic>                  [planned] ecosystem research\n"
            "\nFlags:\n"
            "  --json       Output as JSON\n"
            "  --profile    Scoring profile (default/frontend-spa/backend-monolith/microservices/...)\n"
            "  --rebuild    Force rebuild of import graph cache",
            file=sys.stderr,
        )
        sys.exit(1)
    subcmd = sys.argv[1]
    json_out = "--json" in sys.argv
    rebuild = "--rebuild" in sys.argv
    profile = None
    for arg in sys.argv:
        if arg.startswith("--profile="):
            profile = arg.split("=", 1)[1]

    if subcmd == "check":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_check(project_dir))
    elif subcmd == "validate":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_validate(project_dir, json_output=json_out))
    elif subcmd == "score":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_score(project_dir, profile=profile, json_output=json_out, rebuild=rebuild))
    elif subcmd == "antipattern":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_antipattern(project_dir, json_output=json_out, rebuild=rebuild))
    elif subcmd == "recover":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_recover(project_dir, json_output=json_out))
    elif subcmd == "harden":
        project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys.exit(cmd_harden(project_dir))
    elif subcmd == "research":
        topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not topic:
            print("Usage: genesis_subcommands.py research <topic>", file=sys.stderr)
            sys.exit(1)
        sys.exit(cmd_research(topic))
    else:
        print(f"Unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
