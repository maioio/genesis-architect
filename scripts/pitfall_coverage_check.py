"""
pitfall_coverage_check.py - Phase 6 Step 6.5 mitigation coverage check.

Usage:
    python scripts/pitfall_coverage_check.py PITFALLS.md src/

Exit 0 if all mitigations found, 1 if any missing.
"""

import json
import re
import sys
from pathlib import Path

STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of",
    "and", "or", "is", "it", "use", "using", "with", "all",
    "be", "are", "by", "this", "that", "from", "as", "so",
    "only", "not", "no", "any",
}

EXTENSIONS = {".py", ".ts", ".go", ".rs", ".js"}


def parse_pitfalls(pitfalls_path: Path) -> dict[str, str]:
    """Return {pitfall_id: mitigation_text} parsed from PITFALLS.md."""
    text = pitfalls_path.read_text(encoding="utf-8")
    pitfalls: dict[str, str] = {}

    # Split on '## Pitfall N:' headers
    sections = re.split(r"(?m)^## (Pitfall \d+[^#]*)", text)
    # sections[0] = preamble, then alternating [header, body]
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        # Extract pitfall number
        m = re.search(r"Pitfall\s+(\d+)", header, re.IGNORECASE)
        pitfall_id = f"pitfall_{m.group(1)}" if m else f"pitfall_{(i+1)//2}"

        # Extract mitigation text from '**Our mitigation**:' or '**Mitigation**:'
        mit_m = re.search(
            r"\*\*(?:Our )?[Mm]itigation\*\*\s*:([^\n]+(?:\n(?!##|\*\*)[^\n]*)*)",
            body,
        )
        if mit_m:
            pitfalls[pitfall_id] = mit_m.group(1).strip()

    return pitfalls


def extract_keywords(text: str) -> list[str]:
    """Extract up to 3 meaningful keywords from mitigation text."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    seen: list[str] = []
    for w in words:
        if w not in STOP_WORDS and len(w) > 2 and w not in seen:
            seen.append(w)
        if len(seen) == 3:
            break
    return seen


def collect_source_files(src_dir: Path) -> list[Path]:
    return [p for p in src_dir.rglob("*") if p.suffix in EXTENSIONS and p.is_file()]


def search_keyword_in_files(keyword: str, files: list[Path]) -> list[str]:
    """Return 'filepath:lineno' strings where keyword appears (case-insensitive)."""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    matches: list[str] = []
    for f in files:
        try:
            for lineno, line in enumerate(
                f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    matches.append(f"{f}:{lineno}")
                    break  # one match per file is enough
        except OSError:
            pass
    return matches


def main() -> None:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} PITFALLS.md src/",
            file=sys.stderr,
        )
        sys.exit(2)

    pitfalls_path = Path(sys.argv[1])
    src_dir = Path(sys.argv[2])

    if not pitfalls_path.exists():
        print(f"ERROR: {pitfalls_path} not found", file=sys.stderr)
        sys.exit(2)
    if not src_dir.is_dir():
        print(f"ERROR: {src_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    pitfalls = parse_pitfalls(pitfalls_path)
    if not pitfalls:
        print("WARNING: no pitfalls parsed from PITFALLS.md", file=sys.stderr)

    source_files = collect_source_files(src_dir)

    results: dict[str, dict] = {}
    missing: list[str] = []

    for pid, mitigation_text in pitfalls.items():
        keywords = extract_keywords(mitigation_text)
        all_matches: list[str] = []
        for kw in keywords:
            all_matches.extend(search_keyword_in_files(kw, source_files))
        # Deduplicate
        seen_files: set[str] = set()
        deduped: list[str] = []
        for m in all_matches:
            if m not in seen_files:
                seen_files.add(m)
                deduped.append(m)

        found = bool(deduped)
        results[pid] = {
            "mitigation": " ".join(keywords),
            "found": found,
            "matches": deduped,
        }
        if not found:
            missing.append(pid)

    # JSON to stdout
    print(json.dumps(results, indent=2))

    # Human-readable summary to stderr
    total = len(results)
    covered = total - len(missing)
    print(f"\nCoverage: {covered}/{total} mitigations found in source", file=sys.stderr)
    for pid, info in results.items():
        status = "OK" if info["found"] else "MISSING"
        print(f"  [{status}] {pid}: {info['mitigation']}", file=sys.stderr)
        for m in info["matches"]:
            print(f"           {m}", file=sys.stderr)

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
