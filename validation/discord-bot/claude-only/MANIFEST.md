# Claude Only - Discord Moderation Bot - Manifest

## Files created
- bot.py

## Tests written
- None

## Security measures included
- DISCORD_TOKEN from env (correct)

## Latent bugs
- on_ready called on every reconnect - sync() called multiple times, hits global rate limit
- No permission check before ban/kick - any user can run these commands
- No slash command sync guard - syncs on every restart even in production (60/day global limit)
- warn command stores nothing - warnings not persisted, no history
- clear without limit cap - user can pass 10000, purge takes minutes, hangs interaction (15s timeout)
- No error handling - ban fails on higher-role user, exception propagates to Discord as internal error
