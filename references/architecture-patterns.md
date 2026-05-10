# Architecture Patterns and Boilerplate Templates

Reference for Phase 6 boilerplate generation. Use the pattern that matches the user's
chosen language and architecture tier (Minimalist or Scalable).

---

## JavaScript / TypeScript - Minimalist

```
project/
├── src/
│   ├── index.ts          # Entry point
│   ├── core.ts           # Core logic
│   ├── utils.ts          # Shared utilities
│   └── utils/
│       └── security.ts   # Path safety and input validation
├── tests/
│   └── core.test.ts      # Unit tests
├── .github/
│   └── workflows/
│       └── ci.yml
├── sonar-project.properties
├── package.json
├── tsconfig.json
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**Entry point template (index.ts):**
```typescript
// Genesis Architect scaffold
// Architecture: Minimalist single-process (see RESEARCH.md)

import { transform } from './core';

async function main(): Promise<void> {
  try {
    await transform(process.argv[2] ?? '');
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  }
}

main();
```

**Core template (core.ts):**
```typescript
// Core logic module
// Architecture note: all domain logic lives here, no framework coupling
// Inspired by [repo from research] - avoids the "fat entry point" pitfall (see PITFALLS.md #1)

export async function transform(input: string): Promise<string> {
  if (!input) throw new Error('Input required');
  // TODO: implement transformation
  return input;
}
```

**Test template (core.test.ts):**
```typescript
import { transform } from '../src/core';

describe('core', () => {
  it('returns a non-empty result for valid input', async () => {
    const result = await transform('test input');
    expect(result).toBeDefined();
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });

  it('throws on empty input', async () => {
    await expect(transform('')).rejects.toThrow();
  });
});
```

---

## JavaScript / TypeScript - Scalable

```
project/
├── src/
│   ├── index.ts
│   ├── domain/           # Business logic, no external dependencies
│   │   └── [entity].ts
│   ├── services/         # Use cases, orchestration
│   │   └── [entity]Service.ts
│   ├── infrastructure/   # External: DB, APIs, filesystem
│   │   └── [adapter].ts
│   ├── utils/
│   │   └── security.ts   # Path safety and input validation
│   └── config/
│       └── index.ts
├── tests/
│   ├── unit/
│   └── integration/
├── .github/workflows/ci.yml
├── sonar-project.properties
├── package.json
├── tsconfig.json
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

---

## Python - Minimalist

```
project/
├── src/
│   └── [project_name]/
│       ├── __init__.py
│       ├── main.py       # Entry point
│       ├── core.py       # Core logic
│       ├── utils.py
│       └── utils/
│           └── security.py  # Path safety and input validation
├── tests/
│   ├── __init__.py
│   └── test_core.py
├── .github/workflows/ci.yml
├── sonar-project.properties
├── pyproject.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**Core template (core.py):**
```python
"""
Core logic module.
Architecture note: pure functions only here, no side effects.
Inspired by [repo from research] - avoids tight coupling pitfall (see PITFALLS.md #1)
"""


def transform(input_data: str) -> str:
    """Transform input and return result."""
    if not input_data:
        raise ValueError("Input required")
    # TODO: implement transformation
    return input_data
```

**Test template (test_core.py):**
```python
"""Unit tests for core module."""
from src.[project_name].core import transform


def test_transform_returns_non_empty_string():
    result = transform('test input')
    assert isinstance(result, str)
    assert len(result) > 0


def test_transform_raises_on_empty_input():
    import pytest
    with pytest.raises((ValueError, TypeError)):
        transform('')
```

**pyproject.toml:**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "[project-name]"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7", "ruff>=0.4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

---

## Python - Scalable

```
project/
├── src/
│   └── [project_name]/
│       ├── __init__.py
│       ├── domain/       # Business entities and rules
│       ├── services/     # Use cases
│       ├── adapters/     # External integrations
│       ├── utils/
│       │   └── security.py  # Path safety and input validation
│       └── config.py
├── tests/
│   ├── unit/
│   └── integration/
├── .github/workflows/ci.yml
├── sonar-project.properties
├── pyproject.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

---

## GitHub Actions CI/CD Template

Use the language-specific template directly. Never use the generic template verbatim.

All templates include four parallel jobs: tests, secret scanning, SAST, and quality gate.
Secret scanning and SAST run without any secrets. Quality gate activates after SONAR_TOKEN is added.

### Node.js / TypeScript

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - name: Install dependencies
        run: npm ci
      - name: Run tests
        run: npm test
      - name: Lint
        run: npm run lint
        continue-on-error: true

  secrets-scan:
    name: Secret Scanning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Scan for exposed credentials
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  sast:
    name: Static Analysis
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - name: Initialize static analysis
        uses: github/codeql-action/init@v3
        with:
          languages: javascript
          queries: security-and-quality
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform static analysis
        uses: github/codeql-action/analyze@v3

  quality-gate:
    name: Code Quality Gate
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
        # Remove this line once SONAR_TOKEN is added to GitHub Secrets
        continue-on-error: true
```

### Python

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run tests
        run: pytest
      - name: Lint
        run: ruff check .
        continue-on-error: true

  secrets-scan:
    name: Secret Scanning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Scan for exposed credentials
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  sast:
    name: Static Analysis
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - name: Initialize static analysis
        uses: github/codeql-action/init@v3
        with:
          languages: python
          queries: security-and-quality
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform static analysis
        uses: github/codeql-action/analyze@v3

  quality-gate:
    name: Code Quality Gate
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
        # Remove this line once SONAR_TOKEN is added to GitHub Secrets
        continue-on-error: true
```

### Go

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Install dependencies
        run: go mod download
      - name: Run tests
        run: go test ./...
      - name: Lint
        run: go vet ./...
        continue-on-error: true

  secrets-scan:
    name: Secret Scanning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Scan for exposed credentials
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  sast:
    name: Static Analysis
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - name: Initialize static analysis
        uses: github/codeql-action/init@v3
        with:
          languages: go
          queries: security-and-quality
      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
      - name: Perform static analysis
        uses: github/codeql-action/analyze@v3

  quality-gate:
    name: Code Quality Gate
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
        # Remove this line once SONAR_TOKEN is added to GitHub Secrets
        continue-on-error: true
```

### Rust

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
      - name: Build
        run: cargo build
      - name: Run tests
        run: cargo test
      - name: Lint
        run: cargo clippy
        continue-on-error: true

  secrets-scan:
    name: Secret Scanning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Scan for exposed credentials
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  sast:
    name: Dependency Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
      - name: Install cargo-audit
        run: cargo install cargo-audit
      - name: Audit dependencies for known vulnerabilities
        run: cargo audit

  quality-gate:
    name: Code Quality Gate
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
        # Remove this line once SONAR_TOKEN is added to GitHub Secrets
        continue-on-error: true
```

---

## README.md Badge Block

Include at the top of every generated README.md, below the project title.
Replace `{user}`, `{repo}`, `{workflow}`, and `{package}` with real values.

```markdown
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/{user}/{repo}/{workflow}.yml?branch=main&label=CI)](.github/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/{user}/{repo})](https://github.com/{user}/{repo}/releases)
[![Secret Scanning](https://img.shields.io/badge/secrets-protected-red?logo=git)](.github/workflows/genesis_quality.yml)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project={user}_{repo}&metric=security_rating)](https://sonarcloud.io/summary/new_code?id={user}_{repo})
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project={user}_{repo}&metric=alert_status)](https://sonarcloud.io/summary/new_code?id={user}_{repo})
```

Note: the Security Rating and Quality Gate badges require `SONAR_TOKEN` in GitHub Settings > Secrets. They show "not found" until the first scan completes. Tell the user to add the secret and push - badges become live automatically.

For Python projects, add a PyPI downloads badge once published:
```markdown
[![PyPI Downloads](https://img.shields.io/pypi/dm/{package})](https://pypi.org/project/{package}/)
```

For Node.js projects, add an npm version badge:
```markdown
[![npm version](https://img.shields.io/npm/v/{package})](https://www.npmjs.com/package/{package})
```

Badge style: use `flat` (default) for consistency across all generated projects.

---

## .env.example Template

```bash
# Application settings
APP_ENV=development
APP_PORT=3000
LOG_LEVEL=info

# REQUIRED - generate with: openssl rand -hex 32
SECRET_KEY=change-me-generate-with-openssl-rand-hex-32

# Add project-specific variables here
# Never commit actual values to git
```

---

## Production-Readiness Defaults

Referenced by SKILL.md Phase 6 Step 3b. Add to every scaffold.

### Env validation at startup

**Python:**
```python
import os
_REQUIRED = ["SECRET_KEY", "DATABASE_URL"]
_missing = [k for k in _REQUIRED if not os.getenv(k)]
if _missing:
    raise RuntimeError(f"Missing required env vars: {_missing}")
```

**Node (TypeScript):**
```typescript
const REQUIRED = ["SECRET_KEY", "DATABASE_URL"] as const;
const missing = REQUIRED.filter((k) => !process.env[k]);
if (missing.length) throw new Error(`Missing env vars: ${missing.join(", ")}`);
```

### Health endpoint (Web Service archetype)

**Python (FastAPI):**
```python
@app.get("/health")
def health():
    return {"status": "ok", "version": os.getenv("APP_VERSION", "dev")}
```

**Node (Express):**
```typescript
app.get("/health", (_req, res) => {
  res.json({ status: "ok", version: process.env.npm_package_version });
});
```

### Structured logging

**Python:**
```python
import logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
```

**Node - add pino to dependencies:**
```typescript
import pino from "pino";
export const logger = pino({ level: process.env.LOG_LEVEL ?? "info" });
```

### ADR stub template (`docs/adr/001-initial-architecture.md`)

```markdown
# ADR 001: Initial Architecture

Date: [date]  Status: Accepted

## Context
[Project name] - scaffold generated by Genesis Architect.
Researched [N] repositories. See RESEARCH.md for full analysis.

## Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Language | [language] | Used by [N]/[M] repos in research |
| Architecture tier | [Minimalist/Scalable] | [scale/team reason] |
| Key dependency | [name] | See PITFALLS.md for alternatives rejected |

## Consequences
See PITFALLS.md for known risks and mitigations.
```

### Secure by Default: security module

Create `utils/security.py` (Python) or `src/utils/security.ts` (TypeScript) in every
scaffold that handles user-supplied input. Import and use `get_safe_path` for all file I/O.
Skip for pure API services or frontends with no filesystem access.

**Python: `src/[project_name]/utils/security.py`**
```python
"""
Security utilities: input validation and safe file access.
All file I/O that uses user-supplied paths must go through get_safe_path.
"""
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a path escapes the allowed base directory."""


def get_safe_path(base: Path, user_input: str) -> Path:
    """
    Resolve a user-supplied path and verify it stays inside base.

    Usage:
        safe = get_safe_path(Path("data"), request.filename)
        content = safe.read_text()
    """
    if not user_input:
        raise ValueError("Path must not be empty")
    if "\x00" in user_input:
        raise PathTraversalError("Null byte detected in path")
    resolved = (base / user_input).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise PathTraversalError(
            f"Path traversal blocked: {user_input!r} escapes {base}"
        )
    return resolved
```

**TypeScript: `src/utils/security.ts`**
```typescript
/**
 * Security utilities: input validation and safe file access.
 * All file I/O that uses user-supplied paths must go through getSafePath.
 */
import path from "path";

export class PathTraversalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PathTraversalError";
  }
}

/**
 * Resolve a user-supplied path and verify it stays inside base.
 *
 * Usage:
 *   const safe = getSafePath("data", req.query.filename);
 *   const content = fs.readFileSync(safe, "utf8");
 */
export function getSafePath(base: string, userInput: string): string {
  if (!userInput) throw new Error("Path must not be empty");
  if (userInput.includes("\0")) {
    throw new PathTraversalError("Null byte detected in path");
  }
  const resolvedBase = path.resolve(base);
  const resolved = path.resolve(base, userInput);
  if (!resolved.startsWith(resolvedBase + path.sep) && resolved !== resolvedBase) {
    throw new PathTraversalError(
      `Path traversal blocked: "${userInput}" escapes "${base}"`
    );
  }
  return resolved;
}
```

**Test coverage to include (`tests/test_security.py` or `security.test.ts`):**

Python:
```python
from pathlib import Path
import pytest
from src.[project_name].utils.security import get_safe_path, PathTraversalError

BASE = Path("data")

def test_safe_path_within_base():
    result = get_safe_path(BASE, "report.csv")
    assert result == (BASE / "report.csv").resolve()

def test_blocks_traversal():
    with pytest.raises(PathTraversalError):
        get_safe_path(BASE, "../etc/passwd")

def test_blocks_null_byte():
    with pytest.raises(PathTraversalError):
        get_safe_path(BASE, "file\x00.txt")
```

TypeScript:
```typescript
import { getSafePath, PathTraversalError } from "../src/utils/security";

describe("getSafePath", () => {
  it("returns a resolved path within base", () => {
    const result = getSafePath("data", "report.csv");
    expect(result).toContain("data");
  });

  it("blocks traversal", () => {
    expect(() => getSafePath("data", "../etc/passwd")).toThrow(PathTraversalError);
  });

  it("blocks null bytes", () => {
    expect(() => getSafePath("data", "file\x00.txt")).toThrow(PathTraversalError);
  });
});
```

---

### Dockerfile security (non-root user)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Never run as root in production
RUN adduser --disabled-password --gecos "" appuser
USER appuser
CMD ["python", "-m", "src.main"]
```

---

## Engineering Decision Comment Examples

Use these patterns when writing boilerplate comments:

```python
# Architecture note: Repository pattern used here (inspired by github.com/example/repo)
# This prevents the "fat service" anti-pattern found in 6/15 analyzed repos (see PITFALLS.md #2)

# Architecture note: Config loaded at startup, not on every request
# Avoids: repeated filesystem reads causing latency spikes (see PITFALLS.md #3)

# Architecture note: Async-first design throughout
# Reason: 8/15 analyzed repos reported blocking I/O as the main bottleneck at scale
```

---

## Frontend App - Minimalist (React/Vite)

```
project/
├── src/
│   ├── main.tsx          # Entry point
│   ├── App.tsx           # Root component
│   ├── components/       # Reusable UI components
│   └── hooks/            # Custom React hooks
├── public/
├── tests/
│   └── App.test.tsx
├── .github/workflows/ci.yml
├── package.json
├── tsconfig.json
├── vite.config.ts
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**vite.config.ts template:**
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', globals: true },
});
```

**package.json scripts (frontend):**
```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run",
    "lint": "eslint src --ext .ts,.tsx",
    "type-check": "tsc --noEmit",
    "preview": "vite preview"
  }
}
```

**.env.example (frontend):**
```bash
# VITE_ prefix required for Vite to expose vars to the browser
# Never put secrets in VITE_ vars - they are bundled into the client
VITE_API_URL=http://localhost:3000
VITE_APP_ENV=development
```

**Runtime env check in main.tsx:**
```typescript
const REQUIRED_ENV = ['VITE_API_URL'] as const;
REQUIRED_ENV.forEach(key => {
  if (!import.meta.env[key]) {
    throw new Error(`Missing env var: ${key}`);
  }
});
```

---

## Frontend App - Scalable (React/Vite + feature folders)

```
project/
├── src/
│   ├── main.tsx
│   ├── app/              # App-wide config (router, store, providers)
│   ├── features/         # Feature-sliced: each folder owns its UI + logic
│   │   └── [feature]/
│   │       ├── index.ts
│   │       ├── components/
│   │       └── hooks/
│   ├── shared/           # Cross-feature utilities and UI primitives
│   └── types/
├── public/
├── tests/
│   ├── unit/
│   └── e2e/
├── .github/workflows/ci.yml
├── package.json
├── tsconfig.json
├── vite.config.ts
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

---

## Go - Minimalist

```
project/
├── cmd/
│   └── main.go           # Entry point
├── internal/
│   ├── core/
│   │   └── core.go       # Core logic
│   └── utils/
│       └── utils.go
├── tests/
│   └── core_test.go  # or internal/core/core_test.go for larger projects
├── .github/workflows/ci.yml
├── sonar-project.properties
├── go.mod
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**Core template (core.go):**
```go
// Package core contains the main business logic.
// Architecture note: no external dependencies here - pure domain logic.
// Inspired by ecosystem research - avoids "fat main" pitfall (see PITFALLS.md #1)
package core

// Run executes the core logic.
func Run() error {
    // TODO: implement
    return nil
}
```

**go.mod template:**
```
module github.com/[user]/[project]

go 1.22

require ()
```

**Dockerfile (non-root, multi-stage):**
```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server ./cmd/main.go

FROM scratch
COPY --from=builder /app/server /server
USER 65534:65534
ENTRYPOINT ["/server"]
```

**Structured logging (Go 1.21+ slog):**
```go
import "log/slog"
logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
slog.SetDefault(logger)
```

**Env validation at startup:**
```go
func mustEnv(key string) string {
    v := os.Getenv(key)
    if v == "" {
        slog.Error("missing required env var", "key", key)
        os.Exit(1)
    }
    return v
}
```

---

## Go - Scalable

```
project/
├── cmd/
│   └── main.go
├── internal/
│   ├── domain/           # Business entities and rules
│   ├── service/          # Use cases
│   └── repository/       # External integrations
├── pkg/
│   └── config/
│       └── config.go
├── tests/
│   ├── unit/
│   └── integration/
├── .github/workflows/ci.yml
├── sonar-project.properties
├── go.mod
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

Use the same Dockerfile, structured logging, and env validation snippets as Go - Minimalist above.

---

## Rust - Minimalist

```
project/
├── src/
│   ├── main.rs           # Entry point
│   ├── core.rs           # Core logic
│   └── utils.rs          # Shared utilities
├── tests/
│   └── integration_test.rs
├── .github/workflows/ci.yml
├── sonar-project.properties
├── Cargo.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**Core template (core.rs):**
```rust
// Architecture note: pure functions only - no I/O side effects.
// Inspired by ecosystem research - avoids tight coupling (see PITFALLS.md #1)

pub fn run() -> Result<(), Box<dyn std::error::Error>> {
    // TODO: implement core logic
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_run_succeeds() {
        assert!(run().is_ok());
    }
}
```

---

## Rust - Scalable

```
project/
├── src/
│   ├── main.rs
│   ├── domain/           # Business entities (mod.rs + types)
│   │   └── mod.rs
│   ├── services/         # Use cases
│   │   └── mod.rs
│   ├── infrastructure/   # External: DB, APIs, filesystem
│   │   └── mod.rs
│   └── config.rs
├── tests/
│   └── integration_test.rs
├── .github/workflows/ci.yml
├── sonar-project.properties
├── Cargo.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

Use the same Cargo.toml, Dockerfile, structured logging, and env validation snippets as Rust - Minimalist above.
