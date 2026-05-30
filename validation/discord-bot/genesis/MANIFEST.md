# Genesis - Discord Moderation Bot - Manifest

## Files created
- PITFALLS.md (3 pitfalls with Implementation + Validate blocks)
- src/bot.py (on_ready guard, --sync flag only)
- src/commands/moderation.py (has_permissions, MAX_PURGE, defer)
- src/commands/__init__.py
- src/error_handler.py (MissingPermissions -> ephemeral message)
- tests/test_bot.py (2 async tests)
- tests/test_moderation.py (3 async tests)

## Tests written (5 total)
- test_on_ready_runs_setup_only_once: tree.sync called once, not on reconnect
- test_on_ready_without_sync_flag_does_not_sync: no sync in production
- test_max_purge_constant_is_100_or_less: MAX_PURGE <= Discord limit
- test_clear_rejects_amount_above_max: purge not called for amount=10000
- test_clear_accepts_valid_amount: purge called with valid amount

## Security measures included
- has_permissions decorator on all moderation commands
- MissingPermissions error handler (no stack trace to user)
- DISCORD_TOKEN from env, raises RuntimeError if not set

## Error handling included
- Forbidden on ban/kick: user-facing message, not crash
- MissingPermissions: ephemeral error to user
- Purge cap: error before API call, not timeout

## What Genesis added vs Claude Only
- on_ready guard (Claude Only: sync on every reconnect, burns 60/day quota)
- has_permissions on all commands (Claude Only: any user can ban)
- MAX_PURGE cap (Claude Only: user passes 10000, bot times out)
- error_handler.py (Claude Only: exceptions go to Discord as internal errors)
- 5 tests vs 0 tests
