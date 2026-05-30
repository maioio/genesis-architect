"""Discord moderation bot - Claude Only version."""
import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

@bot.tree.command(name="ban", description="Ban a user")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    await interaction.guild.ban(user, reason=reason)
    await interaction.response.send_message(f"Banned {user.mention}")

@bot.tree.command(name="kick", description="Kick a user")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason"):
    await interaction.guild.kick(user, reason=reason)
    await interaction.response.send_message(f"Kicked {user.mention}")

@bot.tree.command(name="warn", description="Warn a user")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    await interaction.response.send_message(f"Warned {user.mention}: {reason}")

@bot.tree.command(name="clear", description="Clear messages")
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"Cleared {amount} messages", ephemeral=True)

bot.run(os.environ["DISCORD_TOKEN"])
