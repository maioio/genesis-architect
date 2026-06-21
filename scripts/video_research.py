"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/video_research.py instead."""
import sys
import json
from genesis_architect.core.video_research import (
    build_video_queries,
    check_watch_prerequisites,
    build_deep_research_command,
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: video_research.py queries <vision>")
        print("       video_research.py check")
        print("       video_research.py watch-cmd <url> <topic>")
        sys.exit(1)

    cmd = args[0]
    if cmd == "queries" and len(args) >= 2:
        vision = " ".join(args[1:])
        for q in build_video_queries(vision):
            print(q)
    elif cmd == "check":
        status = check_watch_prerequisites()
        print(json.dumps(status, indent=2))
        all_ok = status["yt_dlp"] and status["ffmpeg"] and (status["groq_key"] or status["openai_key"])
        sys.exit(0 if all_ok else 1)
    elif cmd == "watch-cmd" and len(args) >= 3:
        url = args[1]
        topic = " ".join(args[2:])
        print(build_deep_research_command(url, topic))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
