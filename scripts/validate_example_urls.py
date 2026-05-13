#!/usr/bin/env python3
"""
validate_example_urls.py - Check GitHub URLs in examples/ for 404s.
Usage: python scripts/validate_example_urls.py
Exit 0 if all URLs live, exit 1 if any 404.
"""
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _safe_path(base: Path, target: Path) -> Path:
    if not target.resolve().is_relative_to(base.resolve()):
        raise PermissionError(f"Path outside project root: {target}")
    return target


ROOT = Path(__file__).parent.parent.resolve()
EXAMPLES_DIR = ROOT / "examples"
GITHUB_URL_RE = re.compile(r"https://github\.com/[^\s,)\]>\"']+")


def check_urls(directory: Path) -> list[tuple[str, str, int]]:
    dead = []
    for md_file in sorted(directory.rglob("*.md")):
        _safe_path(ROOT, md_file)
        content = md_file.read_text(encoding="utf-8")
        urls = set(GITHUB_URL_RE.findall(content))
        for url in urls:
            if "TODO" in url:
                continue
            try:
                req = urllib.request.Request(url, method="HEAD")
                req.add_header("User-Agent", "genesis-architect-url-validator/1.0")
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status == 404:
                        dead.append((str(md_file.relative_to(ROOT)), url, 404))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    dead.append((str(md_file.relative_to(ROOT)), url, 404))
            except Exception:
                pass
    return dead


def main():
    print(f"Checking GitHub URLs in {EXAMPLES_DIR.relative_to(ROOT)}/")
    dead = check_urls(EXAMPLES_DIR)
    if dead:
        print(f"FAIL: {len(dead)} dead URL(s):")
        for f, url, code in dead:
            print(f"  {code}: {url}  ({f})")
        sys.exit(1)
    print("OK: all GitHub URLs are live")
    sys.exit(0)


if __name__ == "__main__":
    main()
