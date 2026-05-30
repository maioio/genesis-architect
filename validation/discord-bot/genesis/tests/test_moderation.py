# Tests from PITFALLS.md Pitfalls 2 + 3
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from commands.moderation import MAX_PURGE

def test_max_purge_constant_is_100_or_less():
    """MAX_PURGE must be <= 100 - Discord bulk delete hard limit."""
    assert MAX_PURGE <= 100

@pytest.mark.asyncio
async def test_clear_rejects_amount_above_max():
    """Pitfall 3: clear with amount > MAX_PURGE must return error, not call purge."""
    from commands.moderation import setup_moderation
    bot = MagicMock()
    bot.tree = MagicMock()
    captured_commands = {}

    def register_command(**kwargs):
        def decorator(f):
            captured_commands[f.__name__] = f
            return f
        return decorator

    bot.tree.command = register_command
    setup_moderation(bot)

    # Simulate calling clear with amount=10000
    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.channel = MagicMock()
    interaction.channel.purge = AsyncMock()

    clear_fn = captured_commands.get("clear")
    if clear_fn:
        await clear_fn(interaction, amount=10000)
        interaction.channel.purge.assert_not_called()
        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args[0][0]
        assert str(MAX_PURGE) in msg or "between" in msg.lower()

@pytest.mark.asyncio
async def test_clear_accepts_valid_amount():
    """clear with amount=10 must call purge."""
    from commands.moderation import setup_moderation
    bot = MagicMock()
    bot.tree = MagicMock()
    captured_commands = {}

    def register_command(**kwargs):
        def decorator(f):
            captured_commands[f.__name__] = f
            return f
        return decorator

    bot.tree.command = register_command
    setup_moderation(bot)

    interaction = MagicMock()
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = MagicMock()
    interaction.channel.purge = AsyncMock(return_value=[MagicMock()] * 10)

    clear_fn = captured_commands.get("clear")
    if clear_fn:
        await clear_fn(interaction, amount=10)
        interaction.channel.purge.assert_called_once()
        call_kwargs = interaction.channel.purge.call_args
        limit_used = call_kwargs[1].get("limit") or call_kwargs[0][0]
        assert limit_used <= MAX_PURGE
