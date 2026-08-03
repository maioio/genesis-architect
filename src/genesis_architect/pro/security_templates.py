#!/usr/bin/env python3
"""
security_templates.py - Genesis Architect PRO

Generates security documentation customised to the project stack:
  1. STRIDE threat model  -> docs/security/STRIDE_ANALYSIS.md
  2. OWASP Top 10 checklist -> docs/security/OWASP_CHECKLIST.md

Both documents are filled with stack-aware content derived from
.genesis/evidence.json (archetype, language, tech stack).
No external calls required.

Usage:
  python scripts/security_templates.py [project_path]
  python scripts/security_templates.py [project_path] --stride-only
  python scripts/security_templates.py [project_path] --owasp-only
"""

import argparse
import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

def _load_evidence(project_path: Path) -> dict:
    ev_path = project_path / ".genesis" / "evidence.json"
    if ev_path.exists():
        try:
            return json.loads(ev_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _detect_stack(project_path: Path, evidence: dict) -> dict:
    """Detect tech stack from evidence + project files."""
    lang = evidence.get("language", "").lower()
    archetype = evidence.get("archetype", "service").lower()
    rationale = (evidence.get("arch_rationale", "") + " " +
                 evidence.get("exec_summary", "")).lower()

    stack = {
        "language": lang or "python",
        "archetype": archetype,
        "has_auth": any(kw in rationale for kw in ["auth", "login", "jwt", "oauth", "session"]),
        "has_db": any(kw in rationale for kw in ["database", "postgres", "sqlite", "mysql", "mongodb", "redis"]),
        "has_api": archetype in ("service", "api", "web"),
        "has_file_upload": any(kw in rationale for kw in ["upload", "file", "storage", "s3"]),
        "has_payments": any(kw in rationale for kw in ["payment", "stripe", "billing", "checkout"]),
        "has_cli": archetype == "cli",
        "is_library": archetype == "library",
        "framework": _detect_framework(project_path, rationale),
    }
    return stack


def _detect_framework(project_path: Path, rationale: str) -> str:
    frameworks = {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "express": "Express.js",
        "nextjs": "Next.js",
        "gin": "Gin",
        "actix": "Actix-web",
        "axum": "Axum",
    }
    for kw, name in frameworks.items():
        if kw in rationale:
            return name
    # Check pyproject.toml / package.json
    for f in ["pyproject.toml", "requirements.txt", "package.json", "Cargo.toml"]:
        fp = project_path / f
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8").lower()
                for kw, name in frameworks.items():
                    if kw in content:
                        return name
            except OSError:
                pass
    return ""


# ---------------------------------------------------------------------------
# STRIDE Threat Model
# ---------------------------------------------------------------------------

STRIDE_TEMPLATES: dict[str, dict] = {
    "S": {
        "name": "Spoofing",
        "description": "Attacker impersonates a legitimate user or system",
        "default_threats": ["Stolen credentials", "Token forgery", "Session hijacking"],
        "default_mitigations": {
            "api":     "Use short-lived JWT (RS256, 15min expiry). Validate iss/aud claims. Implement refresh token rotation.",
            "cli":     "Use per-user API keys stored in OS keychain, not plaintext config files.",
            "library": "Provide clear documentation on authentication patterns. Never cache credentials in-memory.",
            "default": "Enforce strong authentication at all entry points.",
        },
    },
    "T": {
        "name": "Tampering",
        "description": "Attacker modifies data in transit or at rest",
        "default_threats": ["Man-in-the-middle", "Database record tampering", "Config file modification"],
        "default_mitigations": {
            "api":     "Enforce TLS 1.2+ on all endpoints. Use signed payloads (HMAC) for webhooks. Enable DB checksums.",
            "cli":     "Hash config files and verify integrity on load. Use HTTPS-only for all network requests.",
            "library": "Validate all inputs. Sign outputs where consumers rely on data integrity.",
            "default": "Use HTTPS for all communication. Validate data integrity at boundaries.",
        },
    },
    "R": {
        "name": "Repudiation",
        "description": "User denies performing an action - no evidence to prove otherwise",
        "default_threats": ["No audit trail", "Log tampering", "Anonymous actions"],
        "default_mitigations": {
            "api":     "Structured audit logs per request: user_id, timestamp, action, ip. Append-only log store. Correlate with request IDs.",
            "cli":     "Log all destructive operations to a local audit file with timestamps.",
            "library": "Document which operations are auditable. Expose audit hooks for callers.",
            "default": "Maintain audit logs for all state-changing operations.",
        },
    },
    "I": {
        "name": "Information Disclosure",
        "description": "Sensitive data exposed to unauthorised parties",
        "default_threats": ["Error messages leaking internals", "Logging PII", "Exposed debug endpoints"],
        "default_mitigations": {
            "api":     "Generic error responses (no stack traces in prod). Scrub PII from logs. Disable debug mode in production. Validate CORS allowlist.",
            "cli":     "Mask secrets in CLI output. Never log full exception tracebacks to shared logs.",
            "library": "Never log caller data. Sanitise exceptions before re-raising.",
            "default": "Minimise data in error messages. Separate debug and production logging.",
        },
    },
    "D": {
        "name": "Denial of Service",
        "description": "Attacker degrades or prevents service availability",
        "default_threats": ["Unbounded resource consumption", "Slowloris attacks", "ReDoS via regex"],
        "default_mitigations": {
            "api":     "Rate limiting per IP and per user. Request timeout (30s). Pagination on all list endpoints. Avoid catastrophic regex.",
            "cli":     "Cap memory usage for large file operations. Implement progress timeouts for external calls.",
            "library": "Document resource requirements. Provide configurable limits for all operations.",
            "default": "Implement rate limiting and resource caps at all entry points.",
        },
    },
    "E": {
        "name": "Elevation of Privilege",
        "description": "User gains access beyond their authorised role",
        "default_threats": ["Broken access control", "IDOR", "Role escalation"],
        "default_mitigations": {
            "api":     "RBAC enforced at service layer (not just API gateway). Check ownership on every object access. Deny by default.",
            "cli":     "Run with minimum required OS permissions. Never require sudo for normal operations.",
            "library": "Never assume caller is authorised. Document privilege requirements.",
            "default": "Enforce principle of least privilege. Deny by default.",
        },
    },
}


def _first_sentence(text: str) -> str:
    """The first sentence of `text`, for the threat-matrix summary column.

    Splitting on the first "." alone breaks on any decimal/abbreviation in
    the sentence (e.g. "Enforce TLS 1.2+ on all endpoints." was truncating to
    "Enforce TLS 1" — the "1." in "1.2+" looked like a sentence end). A real
    sentence boundary is a period followed by whitespace (or end of string).
    """
    match = re.search(r"\.(?:\s|$)", text)
    return text[:match.start() + 1] if match else text.rstrip(".") + "."


def _generate_stride_doc(project_path: Path, stack: dict) -> str:
    archetype = stack["archetype"]
    framework = stack["framework"]
    lang = stack["language"]
    project_name = project_path.name.replace("-", " ").replace("_", " ").title()

    header = [
        "# STRIDE Threat Analysis",
        "<!-- Generated by Genesis Architect PRO security_templates.py -->",
        f"<!-- Project: {project_name} | Archetype: {archetype} | Language: {lang} -->",
        "",
        f"## Project: {project_name}",
        f"**Archetype:** {archetype}  |  **Language:** {lang}"
        + (f"  |  **Framework:** {framework}" if framework else ""),
        "",
        "> STRIDE = Spoofing, Tampering, Repudiation, Information Disclosure, "
        "Denial of Service, Elevation of Privilege.",
        "> Review this document and adapt to your specific deployment context.",
        "",
        "## Threat Matrix",
        "",
        "| ID | Category | Threat | Likelihood | Impact | Mitigation |",
        "|----|----------|--------|------------|--------|------------|",
    ]

    # Detect key for mitigation
    mit_key = "api" if stack["has_api"] else ("cli" if stack["has_cli"] else
               "library" if stack["is_library"] else "default")

    rows = []
    for stride_id, data in STRIDE_TEMPLATES.items():
        mitigation = data["default_mitigations"].get(mit_key,
                     data["default_mitigations"]["default"])
        summary = _first_sentence(mitigation)
        for threat in data["default_threats"]:
            rows.append(
                f"| {stride_id} | {data['name']} | {threat} | Medium | High | {summary} |"
            )

    details = []
    for stride_id, data in STRIDE_TEMPLATES.items():
        mitigation = data["default_mitigations"].get(mit_key,
                     data["default_mitigations"]["default"])
        details += [
            f"## {stride_id}: {data['name']}",
            "",
            f"**Definition:** {data['description']}",
            "",
            "**Threats for this project:**",
        ]
        for t in data["default_threats"]:
            details.append(f"- {t}")
        details += [
            "",
            "**Mitigation:**",
            f"{mitigation}",
            "",
        ]

        # Stack-specific additions
        if stride_id == "S" and stack["has_auth"]:
            details.append(
                "_Auth detected in this project: ensure refresh token rotation and "
                "device fingerprinting._"
            )
            details.append("")
        if stride_id == "I" and stack["has_db"]:
            details.append(
                "_Database detected: ensure column-level encryption for PII fields "
                "and parameterised queries only._"
            )
            details.append("")
        if stride_id == "T" and stack["has_file_upload"]:
            details.append(
                "_File upload detected: validate MIME type server-side (not Content-Type header), "
                "scan with ClamAV or equivalent, store outside webroot._"
            )
            details.append("")
        if stride_id == "E" and stack["has_payments"]:
            details.append(
                "_Payments detected: never store raw card data. Use tokenisation. "
                "Validate webhook signatures (e.g. Stripe-Signature header)._"
            )
            details.append("")

    sections = (
        header + rows + ["", "---", ""] + details +
        [
            "---",
            "",
            "_Review this analysis with a security engineer before production deployment._",
            "_Generated by Genesis Architect PRO. Refresh with: `genesis harden [path]`_",
        ]
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# OWASP Top 10 Checklist
# ---------------------------------------------------------------------------

OWASP_ITEMS: list[dict] = [
    {
        "id": "A01",
        "name": "Broken Access Control",
        "description": "Restrictions on what authenticated users are allowed to do are not properly enforced.",
        "checks": {
            "api": [
                "RBAC enforced at service layer, not just gateway",
                "Object-level ownership checks on every resource endpoint",
                "Deny-by-default: unauthenticated requests rejected before any logic runs",
                "CORS allowlist set (not wildcard *)",
            ],
            "cli": [
                "File operations respect OS permissions",
                "No privilege escalation without explicit sudo/admin request",
            ],
            "default": [
                "Principle of least privilege applied",
                "Access control decisions logged",
            ],
        },
        "skip_for": ["library"],
    },
    {
        "id": "A02",
        "name": "Cryptographic Failures",
        "description": "Sensitive data exposed due to weak or absent encryption.",
        "checks": {
            "api": [
                "TLS 1.2+ enforced on all endpoints",
                "Passwords hashed with bcrypt/argon2 (min cost 12)",
                "Secrets in environment variables (not code)",
                "AES-256-GCM for data at rest where required",
            ],
            "cli": [
                "API keys stored in OS keychain or encrypted vault",
                "HTTPS enforced for all outbound requests",
            ],
            "default": [
                "No hardcoded secrets in source code",
                "Use of well-reviewed cryptographic libraries only",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A03",
        "name": "Injection",
        "description": "User-supplied data sent to an interpreter as part of a command or query.",
        "checks": {
            "api": [
                "ORM or parameterised queries for all DB access",
                "Input validation at API boundary (schema validation)",
                "HTML output escaped (no raw f-strings in templates)",
                "Shell commands use subprocess with args list (no shell=True)",
            ],
            "cli": [
                "No shell=True in subprocess calls",
                "File paths validated before use",
            ],
            "default": [
                "All external inputs validated and sanitised",
                "No dynamic query construction from user input",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A04",
        "name": "Insecure Design",
        "description": "Missing or ineffective control design that cannot be fixed by correct implementation.",
        "checks": {
            "api": [
                "Threat model (STRIDE) reviewed before implementation",
                "Security requirements in acceptance criteria",
                "Rate limiting designed in (not added later)",
            ],
            "default": [
                "STRIDE analysis completed (see STRIDE_ANALYSIS.md)",
                "Security reviewed as part of architecture decisions",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A05",
        "name": "Security Misconfiguration",
        "description": "Missing appropriate security hardening across the application stack.",
        "checks": {
            "api": [
                "Debug mode disabled in production",
                "Security headers set (CSP, HSTS, X-Frame-Options)",
                "No default credentials or sample data in production",
                "Dependency versions pinned and audited",
            ],
            "cli": [
                "Config files have restrictive permissions (600)",
                "No sensitive data in environment variable names that appear in logs",
            ],
            "default": [
                ".gitignore includes .env and secrets files",
                "Dependency audit in CI (npm audit, safety, cargo audit)",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A06",
        "name": "Vulnerable and Outdated Components",
        "description": "Using components with known vulnerabilities.",
        "checks": {
            "default": [
                "Dependency CVE scan in CI (`genesis check` or npm audit / safety / cargo audit)",
                "Dependabot or Renovate configured for automatic dependency updates",
                "No EOL runtime versions (check python.org/node.js schedule)",
                "Third-party components reviewed before adoption",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A07",
        "name": "Identification and Authentication Failures",
        "description": "Weaknesses in authentication that allow attackers to compromise passwords or session tokens.",
        "checks": {
            "api": [
                "JWT: short expiry (15min access, 7d refresh), RS256 algorithm",
                "Brute-force protection on login endpoint",
                "Secure, HttpOnly, SameSite cookies for sessions",
                "MFA available for admin accounts",
            ],
            "default": [
                "No hardcoded test credentials in production code",
                "Session invalidated on logout",
            ],
        },
        "skip_for": ["cli", "library"],
    },
    {
        "id": "A08",
        "name": "Software and Data Integrity Failures",
        "description": "Code and infrastructure not protected against integrity violations.",
        "checks": {
            "default": [
                "CI/CD pipeline requires PR review before merge to main",
                "Git tags signed for releases",
                "Dependency integrity verified (lock files committed)",
                "No `curl | bash` patterns in installation docs",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A09",
        "name": "Security Logging and Monitoring Failures",
        "description": "Insufficient logging, detection, or monitoring of security events.",
        "checks": {
            "api": [
                "Structured logs with: timestamp, user_id, action, ip, status_code",
                "Failed authentication attempts logged with rate-limiting",
                "PII removed from logs before storage",
                "Alerts on anomalous error rates",
            ],
            "cli": [
                "Errors logged to stderr with timestamps",
                "Destructive operations logged before execution",
            ],
            "default": [
                "Logs are append-only and rotated",
                "Log level configurable without code changes",
            ],
        },
        "skip_for": [],
    },
    {
        "id": "A10",
        "name": "Server-Side Request Forgery (SSRF)",
        "description": "Attacker can make the server fetch arbitrary URLs.",
        "checks": {
            "api": [
                "URL inputs validated against allowlist before fetch",
                "Block requests to 169.254.0.0/16 (metadata service)",
                "Block requests to 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16",
                "HTTP client timeout set (max 30s)",
            ],
            "default": [
                "User-supplied URLs validated before use",
                "Internal network access from user input not permitted",
            ],
        },
        "skip_for": ["cli", "library"],
    },
]


def _generate_owasp_doc(project_path: Path, stack: dict) -> str:
    archetype = stack["archetype"]
    lang = stack["language"]
    framework = stack["framework"]
    project_name = project_path.name.replace("-", " ").replace("_", " ").title()

    mit_key = "api" if stack["has_api"] else ("cli" if stack["has_cli"] else "default")

    lines = [
        "# OWASP Top 10 Checklist",
        "<!-- Generated by Genesis Architect PRO security_templates.py -->",
        f"<!-- Project: {project_name} | Archetype: {archetype} | Language: {lang} -->",
        "",
        f"## Project: {project_name}",
        f"**Archetype:** {archetype}  |  **Language:** {lang}"
        + (f"  |  **Framework:** {framework}" if framework else ""),
        "",
        "> Based on OWASP Top 10 2021. Items marked N/A are not applicable to this archetype.",
        "> Check each item before production deployment. Update status as work completes.",
        "",
        "| ID | Category | Status | Notes |",
        "|----|----------|--------|-------|",
    ]

    for item in OWASP_ITEMS:
        skip = archetype in item.get("skip_for", [])
        status = "N/A" if skip else "[ ] TODO"
        lines.append(f"| {item['id']} | {item['name']} | {status} | |")

    lines += ["", "---", ""]

    for item in OWASP_ITEMS:
        skip = archetype in item.get("skip_for", [])
        status = " (N/A for this archetype)" if skip else ""
        lines += [
            f"## {item['id']}: {item['name']}{status}",
            "",
            f"_{item['description']}_",
            "",
        ]

        if skip:
            lines += [
                f"> Skipped: {archetype} archetype does not have an applicable surface for this risk.",
                "",
            ]
            continue

        # Get checks: prefer archetype-specific, fallback to default
        checks = item["checks"].get(mit_key, item["checks"].get("default", []))
        if not checks:
            checks = item["checks"].get("default", [])

        lines.append("**Checklist:**")
        lines.append("")
        for check in checks:
            lines.append(f"- [ ] {check}")
        lines.append("")

    lines += [
        "---",
        "",
        "_Review this checklist with a security engineer before production deployment._",
        "_Generated by Genesis Architect PRO. Refresh with: `genesis harden [path]`_",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_security_docs(project_path: str | Path,
                            stride: bool = True,
                            owasp: bool = True,
                            secrets: bool = True,
                            write: bool = True) -> dict[str, str]:
    """
    Generate STRIDE, OWASP, and secrets-scan documents.

    If write=True (default, CLI/standalone behavior), writes files to
    disk immediately and returns {filename: written_path}.

    If write=False (used by the GDE adapter so the write can be deferred
    until the user APPROVEs it), no disk I/O happens here — returns
    {filename: content} instead, for the caller to turn into a
    WriteOperation.
    """
    root = Path(project_path).resolve()
    evidence = _load_evidence(root)
    stack = _detect_stack(root, evidence)

    docs: dict[str, str] = {}
    sec_dir = root / "docs" / "security"

    if stride:
        content = _generate_stride_doc(root, stack)
        if write:
            out_path = sec_dir / "STRIDE_ANALYSIS.md"
            sec_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            docs["STRIDE_ANALYSIS.md"] = str(out_path)
        else:
            docs["STRIDE_ANALYSIS.md"] = content

    if owasp:
        content = _generate_owasp_doc(root, stack)
        if write:
            out_path = sec_dir / "OWASP_CHECKLIST.md"
            sec_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            docs["OWASP_CHECKLIST.md"] = str(out_path)
        else:
            docs["OWASP_CHECKLIST.md"] = content

    if secrets:
        from genesis_architect.pro.secrets_scanner import _generate_secrets_doc
        content = _generate_secrets_doc(root)
        if write:
            out_path = sec_dir / "SECRETS_SCAN.md"
            sec_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            docs["SECRETS_SCAN.md"] = str(out_path)
        else:
            docs["SECRETS_SCAN.md"] = content

    return docs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Security Template Generator"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--stride-only", action="store_true")
    parser.add_argument("--owasp-only", action="store_true")
    parser.add_argument("--secrets-only", action="store_true")
    args = parser.parse_args()

    only_flags = (args.stride_only, args.owasp_only, args.secrets_only)
    if any(only_flags):
        stride, owasp, secrets = args.stride_only, args.owasp_only, args.secrets_only
    else:
        stride = owasp = secrets = True

    docs = generate_security_docs(args.project_path, stride=stride, owasp=owasp, secrets=secrets)
    for name, path in docs.items():
        print(f"Written: {path}")


if __name__ == "__main__":
    main()
