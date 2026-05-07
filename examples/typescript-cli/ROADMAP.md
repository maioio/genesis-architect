# Development Roadmap: csv-transform-cli

## Phase 1: Foundation (complete)
Genesis Architect scaffold with Commander.js, streaming I/O, unit tests, CI/CD.
Includes: `src/index.ts`, `src/core.ts`, `src/utils.ts`, `tests/core.test.ts`, CI workflow.

## Phase 2: Core Transformation
Implement the actual CSV parsing and transformation logic in `src/core.ts`.
- Read CSV from file or stdin using Node.js streams
- Parse columns, apply transformations
- Write output to file or stdout
Estimated effort: 2-4 hours

## Phase 3: Column Selection
Add `--columns` flag to select specific columns from input.
- Parse column names from header row
- Filter output to selected columns only
- Handle missing column names gracefully
Estimated effort: 1-2 hours

## Phase 4: Transformations
Add `--filter`, `--map`, `--sort` flags for common operations.
- `--filter "column=value"` to filter rows
- `--map "column=expression"` to transform values
- `--sort "column"` to sort output
Estimated effort: 3-5 hours

## Phase 5: Output Formats
Add `--format` flag to support JSON, TSV, and custom delimiters.
Estimated effort: 2-3 hours

## Phase 6: Performance
Benchmark against large files (1M+ rows). Optimize streaming pipeline if needed.
Estimated effort: 1-2 hours

## Phase 7: Distribution
- Add `bin` field to `package.json`
- Publish to npm
- Add installation instructions to README
Estimated effort: 1 hour

## Success Criteria
- Handles files up to 1GB without OOM errors
- Processes 100k rows/second minimum
- 95%+ test coverage on core transformation logic
- Published to npm with >0 weekly downloads
