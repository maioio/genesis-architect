# Tests from PITFALLS.md Pitfall 1 - on_ready guard
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def _fresh_bot_module():
    """Re-import bot module with a clean state (removes cached module)."""
    for key in list(sys.modules.keys()):
        if key in ('bot', 'commands.moderation', 'commands', 'error_handler'):
            del sys.modules[key]
    import bot as bot_module
    return bot_module


@pytest.mark.asyncio
async def test_on_ready_runs_setup_only_once():
    """tree.sync must NOT be called on second on_ready (reconnect)."""
    with patch.dict(os.environ, {"DISCORD_TOKEN": "fake"}):
        bot_module = _fresh_bot_module()
        bot_module.bot.tree.sync = AsyncMock()
        user_mock = MagicMock()
        user_mock.__str__ = lambda s: "TestBot#0000"

        with patch.object(sys, 'argv', ['bot.py', '--sync']):
            with patch.object(type(bot_module.bot), 'user', new_callable=PropertyMock, return_value=user_mock):
                await bot_module.on_ready()
                await bot_module.on_ready()  # second call = reconnect

        assert bot_module.bot.tree.sync.call_count == 1, (
            f"tree.sync called {bot_module.bot.tree.sync.call_count} times - "
            "should be 1 (only on first ready, not on reconnect)"
        )


@pytest.mark.asyncio
async def test_on_ready_without_sync_flag_does_not_sync():
    """Without --sync flag, tree.sync must not be called at all."""
    with patch.dict(os.environ, {"DISCORD_TOKEN": "fake"}):
        bot_module = _fresh_bot_module()
        bot_module.bot.tree.sync = AsyncMock()
        user_mock = MagicMock()

        with patch.object(sys, 'argv', ['bot.py']):  # no --sync
            with patch.object(type(bot_module.bot), 'user', new_callable=PropertyMock, return_value=user_mock):
                await bot_module.on_ready()

        bot_module.bot.tree.sync.assert_not_called()
