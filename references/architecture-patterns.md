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

import { run } from './core';

async function main(): Promise<void> {
  try {
    await run();
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

export async function run(): Promise<void> {
  // TODO: implement core logic
  console.log('Genesis scaffold running');
}
```

**Test template (core.test.ts):**
```typescript
import { run } from '../src/core';

describe('core', () => {
  it('runs without throwing', async () => {
    await expect(run()).resolves.not.toThrow();
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
└── .env.example
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


def run() -> None:
    """Main entry point for core logic."""
    # TODO: implement
    print("Genesis scaffold running")
```

**Test template (test_core.py):**
```python
"""Unit tests for core module."""
from src.[project_name].core import run


def test_run_does_not_raise():
    """Verify core function executes without errors."""
    run()  # Should not raise
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

[tool.pytest.ini_options]
testpaths = ["tests"]
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
└── .env.example
```

---

## GitHub Actions CI/CD Template

Works for all languages. Replace [COMMAND] with the appropriate test runner.

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

      - name: Set up environment
        # For Node: uses: actions/setup-node@v4 with node-version: '20'
        # For Python: uses: actions/setup-python@v5 with python-version: '3.11'
        run: echo "Configure for your language above"

      - name: Install dependencies
        run: [INSTALL_COMMAND]
        # npm ci | pip install -e ".[dev]" | cargo build

      - name: Run tests
        run: [TEST_COMMAND]
        # npm test | pytest | cargo test

      - name: Lint
        run: [LINT_COMMAND]
        # npm run lint | ruff check . | cargo clippy
        continue-on-error: true
```

---

## .env.example Template

```bash
# Application settings
APP_ENV=development
APP_PORT=3000
LOG_LEVEL=info

# Add project-specific variables here
# Never commit actual values to git
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
