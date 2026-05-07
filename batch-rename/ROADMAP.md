# Development Roadmap: batch-rename

## Phase 1: Foundation (complete)
Genesis Architect built:
- Core modules: `renamer.py`, `sanitizer.py`, `patterns.py`, `config.py`, `log.py`, `exceptions.py`
- CLI entry point via `typer` with dry-run default, `--execute`, `--copy`, `--undo`
- 14 passing unit tests covering rename logic, sanitization, and pattern escaping
- GitHub Actions CI across Python 3.10-3.13
- All 7 pitfalls from research pre-mitigated in architecture

## Phase 2: Core features (estimated: 1-2 days)
- Add `--extension` filter (rename only `.jpg` files, etc.)
- Add `--recursive` flag for subdirectory traversal
- Add `--case` option: `lower`, `upper`, `title`
- Test: recursive rename with extension filter

## Phase 3: Safety and UX (estimated: 1 day)
- Collision detection: warn if two source files would rename to the same target
- `--interactive` mode: confirm each rename one by one
- Progress bar via `rich.progress` for large batches
- Better error messages with `rich` markup

## Phase 4: Config file support (estimated: 1 day)
- `batch-rename init` command: generates `~/.batch-rename.json` with defaults
- Support `glob`, `prefix`, `suffix`, `regex` in config
- CLI flags always override config values
- Test: config loading, missing config error, config override

## Phase 5: Advanced patterns (estimated: 2 days)
- Date/time tokens in replacement: `{date}`, `{year}`, `{mtime}`
- EXIF metadata tokens for image files: `{camera}`, `{taken}`
- Numbered sequences with padding control: `{n:03d}`
- Test: token expansion in replacement strings

## Phase 6: Distribution (estimated: 1 day)
- Publish to PyPI: `pip install batch-rename`
- Add `--version` flag
- Write full README with examples
- Add `pipx install batch-rename` instructions

## Phase 7: Polish (estimated: 1 day)
- Shell completion via `typer --install-completion`
- `--format` option for output: `table` (default), `json`, `plain`
- Benchmark: measure performance on 10,000 files
- Add `py.typed` marker for typed library consumers

## Success Criteria
- `batch-rename /path --search old --replace new --execute` renames all matching files
- `batch-rename undo /path` restores previous names exactly
- All tests pass on Python 3.10-3.13 in CI
- Zero crashes on filenames with colons, Unicode, double extensions, or reserved names
- Published on PyPI with >10 stars within 30 days of release
