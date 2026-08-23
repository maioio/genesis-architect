"""Analysis and advisory commands — deps, advise, fetch, sync, telemetry.

Split out of gde_cli.py verbatim. Each of these reaches outside the project
for something: a CVE lookup, a tool recommendation, a trusted skill pack, a
sync cycle, or the telemetry consent record.

All of them are read-only unless explicitly told otherwise, and every import
is deferred into its handler so an install without the optional subsystem
still runs the rest of the CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from genesis_architect.pro.commands.formatting import (
    _hr,
)


def cmd_deps(args: argparse.Namespace) -> int:
    """`genesis deps [PATH]` — dependency and package-health door.

    Wraps two engines that previously had no command of their own: the
    dependency scanner (third-party imports per module, plus their CVEs) and
    the package registry (release recency and advisories from PyPI, npm,
    crates.io, Maven, NuGet and OSV).
    """
    from genesis_architect.pro.dependency_scanner import (
        find_python_dependencies, scan_dependency_cves,
    )

    project_dir = Path(getattr(args, "path", ".")).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    # --- single-package lookup: registry only, no project scan needed ---
    requested = getattr(args, "package", None)
    if requested:
        from genesis_architect.pro.package_registry import query_package

        ecosystem = getattr(args, "ecosystem", None) or "pypi"
        signal = query_package(requested, ecosystem)
        if getattr(args, "json_output", False):
            import json as _json
            print(_json.dumps(signal.__dict__, indent=2, default=str))
            return 0
        print()
        print(f"  {requested} ({ecosystem})")
        print(_hr())
        for key, value in signal.__dict__.items():
            print(f"  {key:18} {value}")
        print(_hr())
        print()
        return 0

    deps = find_python_dependencies(project_dir)
    cves = scan_dependency_cves(project_dir) if deps and not getattr(args, "no_cve", False) else []

    packages: dict[str, list[str]] = {}
    for module, names in deps.items():
        for name in names:
            packages.setdefault(name, []).append(module)

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "project": str(project_dir),
            "packages": {name: sorted(mods) for name, mods in sorted(packages.items())},
            "modules_scanned": len(deps),
            "cves": cves,
            "cve_scan_ran": bool(deps) and not getattr(args, "no_cve", False),
        }, indent=2, default=str))
        return 0

    print()
    if not deps:
        # Say which case this is. "0 dependencies" and "this scanner only
        # speaks Python" look identical in the output otherwise.
        print(f"  No third-party Python imports found under {project_dir}.")
        print("  (This scanner covers Python projects; other ecosystems are not "
              "scanned yet.)")
        print()
        return 0

    print(f"  Dependencies — {project_dir}")
    print(_hr())
    print(f"  {len(packages)} third-party package(s) across {len(deps)} module(s)")
    print()
    for name, mods in sorted(packages.items()):
        print(f"  {name:<28} {len(mods)} module(s)")
    print()

    if cves:
        print(f"  {len(cves)} advisory/ies found")
        print()
        for cve in cves:
            print(f"  {cve['id']:<22} {cve['package']}")
            print(f"  {'':22} in {', '.join(cve['modules'][:3])}")
        print()
    elif not getattr(args, "no_cve", False):
        print("  No advisories found for the scanned packages.")
        print()
    print(_hr())
    print()
    return 0 if not cves else 1
def cmd_sync(args: argparse.Namespace) -> int:
    """Run the autonomous sync manager (genesis sync)."""
    from genesis_architect.pro.genesis_sync import cli_sync
    return cli_sync(args)
def cmd_advise(args: argparse.Namespace) -> int:
    """`genesis advise` — dual-level MCP & skill recommendations.

    Read-only and non-installing by design: it explains what each tool would
    buy and how Genesis would drive it, then stops. Acting on that is the
    user's decision, not the advisor's.
    """
    from genesis_architect.pro.mcp_advisor import advise, format_report

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    include_global = not getattr(args, "local_only", False)
    include_local = not getattr(args, "global_only", False)

    report = advise(
        project_dir,
        include_global=include_global,
        include_local=include_local,
    )

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "signals": {
                "languages": sorted(report.signals.languages),
                "frameworks": sorted(report.signals.frameworks),
                "evidence": report.signals.evidence,
            },
            "local": [r.to_dict() for r in report.local],
            "global": [r.to_dict() for r in report.global_],
            "notes": report.notes,
        }, indent=2))
    else:
        print(format_report(report))
    return 0
def cmd_fetch(args: argparse.Namespace) -> int:
    """`genesis fetch` — fetch a trusted skill pack into the project sandbox.

    Whitelist-only and read-only: it clones a registered source, marks the
    sandbox ephemeral so Auto-Purge owns its cleanup, reads the skill
    definitions as text, and never executes anything it downloaded.
    """
    from genesis_architect.pro.skill_fetcher import (
        FetchRefused, discard, fetch, format_result, format_sources,
    )

    if getattr(args, "list_sources", False) or not getattr(args, "source_id", None):
        print(format_sources())
        return 0

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    try:
        if getattr(args, "discard", False):
            removed = discard(args.source_id, project_dir)
            print(f"\n  {'Removed' if removed else 'Nothing to remove for'} "
                  f"{args.source_id}\n")
            return 0
        result = fetch(
            args.source_id, project_dir,
            ttl_hours=getattr(args, "ttl", None) or 2.0,
            force=bool(getattr(args, "force", False)),
        )
    except FetchRefused as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        return 2

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result(result))
    return 0 if result.ok else 1
def cmd_telemetry(args: argparse.Namespace) -> int:
    """Manage anonymous, opt-in product telemetry (default OFF, local-first).

    See product_intelligence.py for the full privacy contract: an allow-list
    sanitizer enforced in code (not trust) means code/paths/secrets/prompts
    can never be recorded even if a future call site tried to send them.
    """
    from genesis_architect.pro.product_intelligence import (
        CONSENT_PROMPT, clear_events, describe_payload, needs_consent_prompt,
        revoke_consent, set_consent,
    )

    project_dir = Path(args.dir).expanduser().resolve()
    action = getattr(args, "telemetry_action", None)

    if action == "enable":
        set_consent(True, project_dir)
        print("\n  Telemetry enabled — anonymous, local-first. "
              "Run `genesis telemetry status` any time to see what's stored.\n")
        return 0
    if action == "disable":
        revoke_consent(project_dir)
        print("\n  Telemetry disabled. This stops new collection; existing local "
              "events are kept — run `genesis telemetry clear` to delete them too.\n")
        return 0
    if action == "clear":
        n = clear_events(project_dir)
        print(f"\n  Cleared {n} locally-stored event(s).\n")
        return 0

    # "status" or bare `genesis telemetry`.
    print()
    if needs_consent_prompt(project_dir):
        print(CONSENT_PROMPT)
        print()
        print("  Decide with: genesis telemetry enable   |   genesis telemetry disable")
    else:
        print(describe_payload(project_dir))
    print()
    return 0
