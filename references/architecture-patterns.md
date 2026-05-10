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
│   └── utils.ts          # Shared utilities
├── tests/
│   └── core.test.ts      # Unit tests
├── .github/
│   └── workflows/
│       └── ci.yml
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
│   └── config/
│       └── index.ts
├── tests/
│   ├── unit/
│   └── integration/
├── .github/workflows/ci.yml
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
│       └── utils.py
├── tests/
│   ├── __init__.py
│   └── test_core.py
├── .github/workflows/ci.yml
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
│       └── config.py
├── tests/
│   ├── unit/
│   └── integration/
├── .github/workflows/ci.yml
├── pyproject.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

---

## GitHub Actions CI/CD Template

Use the language-specific template directly. Never use the generic template verbatim.

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
```

---

## README.md Badge Block

Include at the top of every generated README.md, below the project title.
Replace `{user}`, `{repo}`, `{workflow}`, and `{package}` with real values.

```markdown
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/{user}/{repo}/{workflow}.yml?branch=main&label=CI)](.github/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/release/{user}/{repo})](https://github.com/{user}/{repo}/releases)
```

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
    "lint": "eslint src --ext .ts,.tsx"
  }
}
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
├── go.mod
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**go.mod template:**
```
module github.com/[user]/[project]

go 1.22

require ()
```

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

**Cargo.toml template:**
```toml
[package]
name = "[project-name]"
version = "0.1.0"
edition = "2021"

[dependencies]

[dev-dependencies]
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
├── Cargo.toml
├── .env.example
├── RESEARCH.md
├── PITFALLS.md
└── ROADMAP.md
```

**Cargo.toml template:**
```toml
[package]
name = "[project-name]"
version = "0.1.0"
edition = "2021"

[dependencies]

[dev-dependencies]
```
