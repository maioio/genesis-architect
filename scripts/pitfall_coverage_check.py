"""
pitfall_coverage_check.py - Phase 6 Step 6.5 mitigation coverage check.

Usage:
    python scripts/pitfall_coverage_check.py PITFALLS.md src/
    python scripts/pitfall_coverage_check.py PITFALLS.md src/ --check-platform-risks

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


def _check_args() -> tuple[Path, Path, bool]:
    """Validate CLI args and return (pitfalls_path, src_dir, check_platform_risks). Exits on error."""
    check_platform = "--check-platform-risks" in sys.argv
    plain_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(plain_args) != 2:
        print(
            f"Usage: {sys.argv[0]} PITFALLS.md src/ [--check-platform-risks]",
            file=sys.stderr,
        )
        sys.exit(2)
    pitfalls_path = Path(plain_args[0])
    src_dir = Path(plain_args[1])
    if not pitfalls_path.exists():
        print(f"ERROR: {pitfalls_path} not found", file=sys.stderr)
        sys.exit(2)
    if not src_dir.is_dir():
        print(f"ERROR: {src_dir} is not a directory", file=sys.stderr)
        sys.exit(2)
    return pitfalls_path, src_dir, check_platform


def _deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _check_pitfall(pid: str, mitigation_text: str, source_files: list[Path]) -> dict:
    keywords = extract_keywords(mitigation_text)
    raw_matches: list[str] = []
    for kw in keywords:
        raw_matches.extend(search_keyword_in_files(kw, source_files))
    deduped = _deduplicate(raw_matches)
    return {"mitigation": " ".join(keywords), "found": bool(deduped), "matches": deduped}


def _print_summary(results: dict[str, dict]) -> list[str]:
    missing = [pid for pid, info in results.items() if not info["found"]]
    total = len(results)
    covered = total - len(missing)
    print(f"\nCoverage: {covered}/{total} mitigations found in source", file=sys.stderr)
    for pid, info in results.items():
        status = "OK" if info["found"] else "MISSING"
        print(f"  [{status}] {pid}: {info['mitigation']}", file=sys.stderr)
        for m in info["matches"]:
            print(f"           {m}", file=sys.stderr)
    return missing


def parse_platform_risks(pitfalls_path: Path) -> list[dict]:
    """
    Parse the optional 'platform_risks:' YAML-like block from PITFALLS.md.

    Expected format (anywhere in the file):
        platform_risks:
          - name: Unicode encoding
            platform: windows
            mitigation_path: src/myapp/utils/security.py
          - name: Path separator
            platform: windows
            acknowledged: true

    Returns list of dicts. Empty list if section absent.
    """
    text = pitfalls_path.read_text(encoding="utf-8")
    block_match = re.search(
        r"(?m)^platform_risks:\s*\n((?:[ \t]+-[^\n]*\n(?:[ \t]+[^\n]+\n)*)*)",
        text,
    )
    if not block_match:
        return []

    block = block_match.group(1)
    risks: list[dict] = []
    # Each entry starts with '  - name:'
    entries = re.split(r"(?m)^[ \t]+-[ \t]+", block)
    for entry in entries:
        if not entry.strip():
            continue
        risk: dict = {}
        for line in entry.splitlines():
            m = re.match(r"[ \t]*(\w[\w_-]*)[ \t]*:[ \t]*(.+)", line)
            if m:
                risk[m.group(1).strip()] = m.group(2).strip()
        if risk:
            risks.append(risk)
    return risks


def check_platform_risks(risks: list[dict], src_dir: Path) -> list[str]:
    """
    Validate platform_risks entries from PITFALLS.md.

    Each risk must have either:
      - mitigation_path that exists under src_dir, OR
      - acknowledged: true

    Returns list of error strings.
    """
    errors: list[str] = []
    for risk in risks:
        name = risk.get("name", "<unnamed>")
        platform = risk.get("platform", "unknown")
        mit_path = risk.get("mitigation_path", "").strip()
        acknowledged = str(risk.get("acknowledged", "false")).lower() == "true"

        if not mit_path and not acknowledged:
            errors.append(
                f"platform_risk '{name}' ({platform}): "
                "must have mitigation_path or acknowledged: true"
            )
            continue

        if mit_path and not acknowledged:
            # Check that mitigation_path exists in src_dir or project root
            candidates = list(src_dir.parent.rglob(mit_path.replace("/", "/")))
            if not candidates:
                errors.append(
                    f"platform_risk '{name}' ({platform}): "
                    f"mitigation_path '{mit_path}' not found in project tree"
                )

    return errors


def main() -> None:
    pitfalls_path, src_dir, check_platform = _check_args()

    pitfalls = parse_pitfalls(pitfalls_path)
    if not pitfalls:
        print("WARNING: no pitfalls parsed from PITFALLS.md", file=sys.stderr)

    source_files = collect_source_files(src_dir)

    results: dict[str, dict] = {
        pid: _check_pitfall(pid, text, source_files)
        for pid, text in pitfalls.items()
    }

    print(json.dumps(results, indent=2))
    missing = _print_summary(results)

    platform_errors: list[str] = []
    if check_platform:
        risks = parse_platform_risks(pitfalls_path)
        if not risks:
            print(
                "INFO: --check-platform-risks: no platform_risks section found in PITFALLS.md",
                file=sys.stderr,
            )
        else:
            platform_errors = check_platform_risks(risks, src_dir)
            if platform_errors:
                print(
                    f"\nPlatform risks: {len(platform_errors)} issue(s):",
                    file=sys.stderr,
                )
                for err in platform_errors:
                    print(f"  - {err}", file=sys.stderr)
            else:
                print(
                    f"\nPlatform risks: all {len(risks)} risk(s) accounted for",
                    file=sys.stderr,
                )

    sys.exit(1 if (missing or platform_errors) else 0)


if __name__ == "__main__":
    main()
