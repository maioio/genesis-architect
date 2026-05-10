# Security Templates

Reference for Phase 6 Step 7b and the `genesis harden` command. Genesis Architect
injects these files automatically based on detected language and project structure.

The section headings below describe capabilities. Tool names appear only inside YAML
where they are required for GitHub Actions to locate the correct action.

---

## Secret Scanning Workflow

Scans the full Git history on every push and pull request. Fails the build if any
credential, API key, or token pattern is detected in any commit - including old ones.

```yaml
name: Secret Scanning

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  gitleaks:
    name: Secret Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Run secret scanner
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}
```

---

## SAST Workflow (Python / JavaScript / C++)

Static analysis on every push and weekly schedule. Detects injection vulnerabilities,
path traversal, unsafe deserialization, and other code-level security issues.
Results are uploaded to GitHub Code Scanning automatically.

```yaml
name: Static Analysis

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 8 * * 1'

jobs:
  sast:
    name: SAST
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    strategy:
      matrix:
        language: [python]  # Replace with: javascript, cpp as needed

    steps:
      - uses: actions/checkout@v4
      - name: Initialize static analysis
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-and-quality
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform static analysis
        uses: github/codeql-action/analyze@v3
```

---

## Code Quality Gate Workflow

Measures maintainability, reliability, and security hotspots on every push.
The quality gate blocks merges when the score drops below the configured threshold.
Activates after `SONAR_TOKEN` is added to GitHub Secrets.

```yaml
name: Code Quality Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality-gate:
    name: Quality Gate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Run quality gate scan
        uses: SonarSource/sonarqube-scan-action@v5
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

---

## sonar-project.properties template

```properties
sonar.projectKey=[github-username]_[project-name]
sonar.organization=[github-username]
sonar.projectName=[Project Name]
sonar.projectVersion=0.1.0
sonar.sources=src
sonar.exclusions=**/__pycache__/**,**/*.pyc,**/node_modules/**,**/venv/**
sonar.qualitygate.wait=true
```

---

## Pre-commit Hook (local secret prevention)

Blocks secrets locally before they are committed - catches mistakes before they
reach GitHub at all.

```yaml
# .pre-commit-config.yaml - place in project root
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

Install with: `pip install pre-commit && pre-commit install`

---

## Language Selection Guide

| Language | SAST matrix.language | sonar.language |
|----------|----------------------|----------------|
| Python | python | py |
| JavaScript / TypeScript | javascript | js |
| C++ | cpp | cpp |
| Go | go | go |
| Rust | (not supported) | (community plugin) |

Genesis Architect selects the correct language automatically from Phase 1 Q4 or from
auto-detection in Phase 3.

---

## genesis harden Status Table Format

When `genesis harden` runs, output this table format:

| File | Status | Action needed |
|------|--------|---------------|
| `.github/workflows/genesis_quality.yml` | Injected | None |
| `sonar-project.properties` | Injected | Add SONAR_TOKEN to GitHub Secrets |
| `.gitignore` hardening | Updated | None |
| `SNYK_TOKEN` secret | Missing | Add at dependency scanning platform, then GitHub Settings > Secrets |
| `sast` job language | python (auto-detected) | None |
