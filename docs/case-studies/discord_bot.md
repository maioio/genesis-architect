# Case Study: Discord Bot

## What was requested

```
genesis init a Discord bot that tracks GitHub activity and posts digests
```

## What Genesis found

**Repos researched:** Rapptz/discord.py, pycord-development/pycord, discord-disnake/disnake, interactions-py/interactions.py, PyCQA/bot (16 repos total)

**Top pitfalls from GitHub Issues:**

| Pitfall | Issue | Found in |
|---------|-------|----------|
| Intents not declared causes silent message drop | [discord.py#8931](https://github.com/Rapptz/discord.py/issues/8931) | 8/8 repos |
| Rate limit not respected causes 429 cascade | [discord.py#9428](https://github.com/Rapptz/discord.py/issues/9428) | 6/8 repos |
| Bot token in code committed to GitHub | [pycord#2187](https://github.com/pycord-development/pycord/issues/2187) | 7/8 repos |
| `on_ready` called multiple times on reconnect | [discord.py#7439](https://github.com/Rapptz/discord.py/issues/7439) | 5/8 repos |
| Slash command sync on every restart hits global rate limit | [discord.py#9462](https://github.com/Rapptz/discord.py/issues/9462) | 4/8 repos |

## What was saved

- `on_ready` guarded with `hasattr(self, '_ready_done')` check - runs setup once
- Slash commands synced only in development via `--sync` flag, not on every prod start
- Rate limiter: exponential backoff wrapper on all GitHub API calls
- Token: loaded from env, never default-valued, bot refuses to start if missing
- Message intents declared in manifest and requested in code

## What was built

```
github-digest-bot/
├── src/
│   ├── bot.py           # discord.Client subclass, on_ready guard
│   ├── commands/
│   │   └── digest.py    # Slash commands, sync only with --sync flag
│   ├── github/
│   │   ├── client.py    # GitHub API wrapper with exponential backoff
│   │   └── digest.py    # Activity aggregation logic
│   └── scheduler.py     # APScheduler for periodic digest posting
├── tests/
│   ├── test_github_client.py   # Rate limit simulation
│   └── test_digest.py
├── .env.example         # DISCORD_TOKEN, GITHUB_TOKEN - never default values
├── Dockerfile           # Non-root, health check via discord gateway ping
└── .github/workflows/ci.yml   # Secret scan catches token patterns
```

**Token leak incidents:** 0
**429 cascade incidents:** 0
**Duplicate setup on reconnect:** 0
