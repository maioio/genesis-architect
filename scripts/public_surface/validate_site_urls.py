"""Validate links to the project's own website against the BUILT site.

Why this exists: the external link checker (lychee) cannot tell a typo from a
page that is merely not deployed yet, so it must not check our own site URLs.
This script checks them instead, against site/dist, so a new page can be linked
in the same pull request that adds it, while a link to a page that does not
exist in the build still fails.

Scanned: every Markdown source that lychee scans, plus absolute links to our
site inside the built HTML. Exit 1 on any URL that has no built page.

    python scripts/public_surface/validate_site_urls.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "site" / "dist"
SITE = "https://maioio.github.io/genesis-architect"
BASE = "/genesis-architect"

MD_SOURCES = [
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "demo", "docs/architecture",
    "docs/evaluations", "docs/security", "docs/reference", "site/src/content",
]
URL_RE = re.compile(r"(?:https://maioio\.github\.io/genesis-architect|(?<![\w/.:-])/genesis-architect)(/[^\s)\]>\"'`]*)?")


def built_target(url_path: str) -> Path:
    rel = unquote(url_path).lstrip("/")
    target = DIST / rel
    return target / "index.html" if target.is_dir() or not target.suffix else target


def check_url(raw: str) -> str | None:
    """Return an error message, or None when the URL maps to a built file."""
    path = urlparse(raw).path
    path = path[len(BASE):] if path.startswith(BASE) else path
    if built_target(path).exists() or (DIST / (unquote(path).strip("/") + ".html")).exists():
        return None  # the .html form covers the 404 page, which is 404.html
    return f"no built page for {raw}"


def markdown_files() -> list[Path]:
    out: list[Path] = []
    for entry in MD_SOURCES:
        p = ROOT / entry
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += [f for f in p.rglob("*") if f.suffix in {".md", ".mdx"}]
    return sorted(out)


def find_urls(text: str) -> list[str]:
    urls = []
    for m in URL_RE.finditer(text):
        full = m.group(0).rstrip(".,;:")
        full = full.split("#")[0].split("?")[0]
        if full.startswith("/genesis-architect"):
            full = SITE + full[len(BASE):]
        urls.append(full)
    return urls


def main() -> int:
    if not DIST.is_dir():
        print("site/dist missing: run `npm run build` in site/")
        return 1
    errors: list[str] = []
    count = 0
    for f in markdown_files():
        for url in find_urls(f.read_text(encoding="utf-8", errors="replace")):
            count += 1
            err = check_url(url)
            if err:
                errors.append(f"{f.relative_to(ROOT).as_posix()}: {err}")
    for page in sorted(DIST.rglob("*.html")):
        for url in find_urls(page.read_text(encoding="utf-8", errors="replace")):
            count += 1
            err = check_url(url)
            if err:
                errors.append(f"{page.relative_to(DIST).as_posix()}: {err}")
    print(f"checked {count} links to our own site against site/dist")
    for e in errors:
        print("FAIL", e)
    if errors:
        print("Fix the link, or add the page. Do not exclude it in .lychee.toml.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
