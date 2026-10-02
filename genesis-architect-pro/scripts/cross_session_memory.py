"""Shim: delegates to src/genesis_architect/core/cross_session_memory.py"""
import sys
import json
from pathlib import Path
from genesis_architect.core.cross_session_memory import (
    restore_session,
    save_phase2,
    save_phase4,
    save_phase6,
    save_video_pitfalls,
    list_analyzed_videos,
    no_session_message,
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: cross_session_memory.py restore [--project-root DIR]")
        print("       cross_session_memory.py save-phase2 <vision> <repos> <deep> <quality>")
        print("       cross_session_memory.py save-video <url> <count>")
        print("       cross_session_memory.py list-videos")
        sys.exit(1)

    project_root = Path(".")
    if "--project-root" in args:
        idx = args.index("--project-root")
        project_root = Path(args[idx + 1])

    cmd = args[0]

    if cmd == "restore":
        ctx = restore_session(project_root)
        if ctx.restored:
            print(ctx.announce())
            sys.exit(0)
        else:
            print(no_session_message())
            sys.exit(1)

    elif cmd == "save-phase2" and len(args) >= 5:
        save_phase2(project_root, args[1], int(args[2]), int(args[3]), args[4])
        print(f"Saved phase2: {args[2]} repos, {args[3]} deep, quality={args[4]}")

    elif cmd == "save-video" and len(args) >= 3:
        save_video_pitfalls(project_root, args[1], int(args[2]))
        print(f"Recorded video: {args[1]} (+{args[2]} pitfalls)")

    elif cmd == "list-videos":
        videos = list_analyzed_videos(project_root)
        if videos:
            print("\n".join(videos))
        else:
            print("No videos analyzed yet.")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
