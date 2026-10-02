"""
secrets_scanner.py - Genesis Architect PRO

Offline, regex-based secrets detection — the third leg of `genesis harden`
alongside STRIDE and OWASP (security_templates.py). No network calls, no LLM;
same "pure graph/pattern analysis, deterministic" promise as the rest of the
Security engine.

Detects common credential shapes (AWS keys, private key blocks, GitHub/Slack/
Stripe tokens, generic API-key assignments) via well-known patterns, similar
in spirit to gitleaks/truffleHog's default regex rules. Findings are always
redacted before they're written anywhere — the report must never reproduce a
live secret in full, since docs/security/ is meant to be safe to commit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".genesis", ".tox", ".mypy_cache", ".pytest_cache")

# Files that are almost certainly not source (binary/lockfile/media) — skip by
# extension to keep the scan fast and avoid decoding binary as text.
SKIP_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
             ".tar", ".woff", ".woff2", ".ttf", ".eot", ".lock", ".min.js",
             ".map", ".pyc", ".so", ".dll", ".exe")

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB — skip anything larger (unlikely to be source)

# Substrings that mark an obvious placeholder — suppress matches around these
# to cut the most common false positives (docs, .env.example, templates).
_PLACEHOLDER_RE = re.compile(
    r"(your[_-]?key|xxxx|placeholder|changeme|example|dummy|<[^>]+>|\$\{)",
    re.IGNORECASE,
)


@dataclass
class SecretFinding:
    file: str
    line: int
    rule: str
    severity: str  # "high" | "medium"
    redacted: str


# (rule name, severity, compiled pattern). Patterns capture the credential in
# group 1 where possible so redaction only masks the credential, not the
# surrounding context.
_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("AWS Access Key ID", "high", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("GitHub Token", "high", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,})\b")),
    ("Slack Token", "high", re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,72})\b")),
    ("Stripe Live Key", "high", re.compile(r"\b(sk_live_[0-9a-zA-Z]{16,})\b")),
    ("Google API Key", "high", re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b")),
    ("Private Key Block", "high",
     re.compile(r"-----BEGIN\s+(?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("Generic API Key/Secret Assignment", "medium", re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
        r"client[_-]?secret|password)\s*[:=]\s*['\"]([A-Za-z0-9_\-/+=]{16,})['\"]"
    )),
]


def _redact(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"


def _iter_source_files(project_root: Path):
    for f in project_root.rglob("*"):
        if not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        if f.suffix.lower() in SKIP_EXTS:
            continue
        try:
            if f.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield f


def scan_secrets(project_path: str | Path) -> list[SecretFinding]:
    """Walk the project tree and return every credential-shaped match found.
    Pure, read-only, offline. Never raises on unreadable files — they're
    skipped, not fatal."""
    root = Path(project_path).resolve()
    findings: list[SecretFinding] = []

    for f in _iter_source_files(root):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        rel = str(f.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _PLACEHOLDER_RE.search(line):
                continue
            for rule, severity, pattern in _RULES:
                m = pattern.search(line)
                if not m:
                    continue
                secret = m.group(1) if m.groups() else m.group(0)
                findings.append(SecretFinding(
                    file=rel, line=lineno, rule=rule,
                    severity=severity, redacted=_redact(secret),
                ))
    return findings


def _generate_secrets_doc(project_path: str | Path) -> str:
    root = Path(project_path).resolve()
    findings = scan_secrets(root)

    lines = [
        "# Secrets Scan",
        "",
        "_Offline, regex-based detection — no network calls, nothing sent "
        "anywhere. Values below are redacted; this file is safe to commit._",
        "",
    ]

    if not findings:
        lines.append("No likely secrets detected in the scanned files.")
        return "\n".join(lines) + "\n"

    high = [f for f in findings if f.severity == "high"]
    medium = [f for f in findings if f.severity == "medium"]

    lines.append(f"**{len(findings)} finding(s)** — {len(high)} high confidence, "
                 f"{len(medium)} to review (generic pattern, higher false-positive rate).")
    lines.append("")

    for label, group in (("High confidence", high), ("Review", medium)):
        if not group:
            continue
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| File | Line | Rule | Value |")
        lines.append("|---|---|---|---|")
        for finding in group:
            lines.append(f"| `{finding.file}` | {finding.line} | {finding.rule} | `{finding.redacted}` |")
        lines.append("")

    lines.append(
        "**Next step:** rotate any confirmed live credential, move it to an "
        "env var or secrets manager, and add the file to `.gitignore` if it "
        "isn't already tracked-and-scrubbed."
    )
    return "\n".join(lines) + "\n"
