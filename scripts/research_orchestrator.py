"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/research_orchestrator.py instead."""
import sys
import json
from pathlib import Path
from genesis_architect.core.research_orchestrator import (
    build_summary_from_raw,
    load_from_vault,
    format_summary,
    check_floor,
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: research_orchestrator.py summarize <json_file> [--project-root DIR]")
        print("       research_orchestrator.py vault-check <vision> [--project-root DIR]")
        sys.exit(1)

    cmd = args[0]
    project_root = Path(".")
    if "--project-root" in args:
        idx = args.index("--project-root")
        project_root = Path(args[idx + 1])

    if cmd == "summarize" and len(args) >= 2:
        data = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        summary = build_summary_from_raw(
            vision=data["vision"],
            repos=data.get("repos", []),
            github_issues=data.get("github_issues", []),
            exa_results=data.get("exa_results", []),
            video_exa_results=data.get("video_exa_results", []),
            project_root=project_root,
        )
        print(format_summary(summary))
    elif cmd == "vault-check" and len(args) >= 2:
        vision = " ".join(args[1:]).replace("--project-root", "").strip()
        cached = load_from_vault(vision, project_root)
        if cached:
            print(f"Cache hit (from vault): {cached.research_quality}")
            print(format_summary(cached))
        else:
            print("No cached research found.")
            sys.exit(1)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
