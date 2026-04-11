import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram.handlers import is_authorized, handle_message, handle_agents_command
from guard.prompt_guard import GuardVerdict


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


def make_manager_with_agent():
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master", "status": "idle"}
    return manager


@pytest.mark.asyncio
async def test_handle_message_guard_blocks():
    update = make_update(123, "@master rm -rf /")
    manager = make_manager_with_agent()
    guard = AsyncMock()
    guard.check.return_value = GuardVerdict(blocked=True, reason="regex:destructive")
    await handle_message(update, MagicMock(), manager, [123], guard=guard)
    guard.check.assert_awaited_once()
    manager.send_prompt.assert_not_called()
    reply = update.message.reply_text.call_args[0][0]
    assert "заблокирован" in reply.lower()


@pytest.mark.asyncio
async def test_handle_message_guard_suspicious_passes():
    update = make_update(123, "@master do thing")
    manager = make_manager_with_agent()
    guard = AsyncMock()
    guard.check.return_value = GuardVerdict(suspicious=True, reason="llm:suspicious")
    await handle_message(update, MagicMock(), manager, [123], guard=guard)
    manager.send_prompt.assert_awaited_once()
    replies = [c[0][0] for c in update.message.reply_text.call_args_list]
    assert any("подозрительный" in r.lower() for r in replies)


@pytest.mark.asyncio
async def test_handle_message_guard_safe_silent():
    update = make_update(123, "@master hello")
    manager = make_manager_with_agent()
    guard = AsyncMock()
    guard.check.return_value = GuardVerdict()
    await handle_message(update, MagicMock(), manager, [123], guard=guard)
    manager.send_prompt.assert_awaited_once()
    replies = [c[0][0] for c in update.message.reply_text.call_args_list]
    assert not any("заблокирован" in r.lower() or "подозрительный" in r.lower() for r in replies)


@pytest.mark.asyncio
async def test_handle_message_guard_none_skips_check():
    update = make_update(123, "@master hello")
    manager = make_manager_with_agent()
    await handle_message(update, MagicMock(), manager, [123])
    manager.send_prompt.assert_awaited_once()


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
