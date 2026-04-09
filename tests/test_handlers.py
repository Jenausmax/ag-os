import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram.handlers import is_authorized, handle_message, handle_agents_command


def make_update(user_id: int, text: str):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_is_authorized_allowed():
    assert is_authorized(123, [123, 456])


@pytest.mark.asyncio
async def test_is_authorized_denied():
    assert not is_authorized(789, [123, 456])


@pytest.mark.asyncio
async def test_is_authorized_empty_whitelist():
    assert not is_authorized(123, [])


@pytest.mark.asyncio
async def test_handle_message_unauthorized():
    update = make_update(999, "hello")
    context = MagicMock()
    manager = AsyncMock()
    await handle_message(update, context, manager, [123])
    update.message.reply_text.assert_called_once()
    assert "авторизован" in update.message.reply_text.call_args[0][0].lower() or \
           "denied" in update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_agents_command():
    update = make_update(123, "/agents")
    context = MagicMock()
    manager = AsyncMock()
    manager.list_agents.return_value = [
        {"name": "master", "status": "idle", "model": "claude-cli", "current_task": ""},
        {"name": "jira", "status": "working", "model": "claude-cli", "current_task": "отчёт"},
    ]
    await handle_agents_command(update, context, manager, [123])
    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "master" in reply
    assert "jira" in reply
