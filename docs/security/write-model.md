# Write model

What Genesis may write or delete, and what consent that needs.

| Action | Default | Consent switch | Evidence |
|---|---|---|---|
| `genesis purge` (delete expired ephemeral resources) | Dry run: reports, deletes nothing | `--apply` | `pro/ephemeral_purge.py`, `pro/commands/parser.py`, `pro/commands/project_cmds.py` |
| `genesis sync` | Writes; can preview | `--dry-run` | `pro/genesis_sync.py`, `pro/commands/parser.py` |
| Public-surface generators in this repository | Write generated files | `--check` verifies without writing | `scripts/public_surface/generate_product_facts.py`, `sync_readme_facts.py`, `scripts/architecture_invariants.py` |
| Scaffold generation | Writes under the chosen target directory | Path containment check | `tests/test_scaffold_generator.py` |

Rules the code follows:

1. Deletion is never the default. A command that removes files reports what it would do first.
2. Writes resolve the final path and refuse anything outside the base directory.
3. Generated files in this repository have a `--check` mode so CI can fail on drift without
   modifying the tree.

Gaps: not every write command has a dry-run flag. `genesis sync` is dry-run on request, not by
default. Treat that as the current behavior, not as a guarantee for future commands.
