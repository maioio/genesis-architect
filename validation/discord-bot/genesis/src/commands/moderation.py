# Architecture note: has_permissions on every moderation command, MAX_PURGE cap
# Avoids: Pitfall 2 - any user can run ban/kick
# Avoids: Pitfall 3 - purge without cap times out at 15s

import discord
from discord import app_commands

MAX_PURGE = 100

def setup_moderation(bot):
    @bot.tree.command(name="ban", description="Ban a member from the server")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        try:
            await interaction.guild.ban(user, reason=reason)
            await interaction.response.send_message(f"Banned {user.mention}. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban this user (check role hierarchy).", ephemeral=True)

    @bot.tree.command(name="kick", description="Kick a member from the server")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        try:
            await interaction.guild.kick(user, reason=reason)
            await interaction.response.send_message(f"Kicked {user.mention}. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick this user.", ephemeral=True)

    @bot.tree.command(name="clear", description=f"Clear messages (max {MAX_PURGE})")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > MAX_PURGE:
            await interaction.response.send_message(
                f"Amount must be between 1 and {MAX_PURGE}.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)
