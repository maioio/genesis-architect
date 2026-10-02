"""Shim: delegates to src/genesis_architect/core/video_to_pitfall.py"""
import sys
from pathlib import Path
from genesis_architect.core.video_to_pitfall import (
    extract_from_watch_output,
    append_to_pitfalls_md,
    summarize_extraction,
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "extract":
        print("Usage: video_to_pitfall.py extract <source_url> <vision> [--watch-output FILE] [--pitfalls PITFALLS.md]")
        sys.exit(1)

    source_url = args[1]
    vision = args[2] if len(args) > 2 else "the project"
    watch_file = None
    pitfalls_path = Path("PITFALLS.md")

    i = 3
    while i < len(args):
        if args[i] == "--watch-output" and i + 1 < len(args):
            watch_file = Path(args[i + 1]); i += 2
        elif args[i] == "--pitfalls" and i + 1 < len(args):
            pitfalls_path = Path(args[i + 1]); i += 2
        else:
            i += 1

    if watch_file and watch_file.exists():
        watch_text = watch_file.read_text(encoding="utf-8")
    else:
        watch_text = sys.stdin.read()

    entries = extract_from_watch_output(watch_text, source_url, vision)
    count = append_to_pitfalls_md(entries, pitfalls_path)
    print(summarize_extraction(entries, source_url))
    print(f"Appended {count} entries to {pitfalls_path}")
