# Architecture note: on_ready guard - setup runs exactly once, not on every reconnect
# Avoids: Pitfall 1 - tree.sync() hitting 60/day global rate limit

import discord
from discord.ext import commands
from commands.moderation import setup_moderation
from error_handler import setup_error_handler
import os
import sys

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    if hasattr(bot, "_ready_done"):
        return
    bot._ready_done = True

    setup_moderation(bot)
    setup_error_handler(bot)

    if "--sync" in sys.argv:
        await bot.tree.sync()
        print("Slash commands synced.")
    else:
        print("Skipping sync (use --sync flag to sync in dev)")

    print(f"Ready: {bot.user}")

def run():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable not set")
    bot.run(token)

if __name__ == "__main__":
    run()
