import pytest
from unittest.mock import AsyncMock, MagicMock
from tgbot.handlers import (
    is_authorized,
    handle_message,
    handle_agents_command,
    handle_schedule_add,
    handle_schedule_list,
    handle_schedule_rm,
    handle_schedule_run,
)
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


def _schedule_context(args: list[str]):
    ctx = MagicMock()
    ctx.args = args
    return ctx


@pytest.mark.asyncio
async def test_schedule_add_unauthorized():
    update = make_update(999, "/schedule_add")
    manager = AsyncMock()
    scheduler = AsyncMock()
    await handle_schedule_add(update, _schedule_context([]), manager, scheduler, [123])
    scheduler.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_add_success():
    update = make_update(123, "/schedule_add")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master"}
    scheduler = AsyncMock()
    scheduler.add_task.return_value = 42
    ctx = _schedule_context(["0", "*", "*", "*", "*", "@master", "проверь", "почту"])
    await handle_schedule_add(update, ctx, manager, scheduler, [123])
    scheduler.add_task.assert_awaited_once_with("0 * * * *", "master", "проверь почту")
    reply = update.message.reply_text.call_args[0][0]
    assert "#42" in reply


@pytest.mark.asyncio
async def test_schedule_add_invalid_cron():
    update = make_update(123, "/schedule_add")
    manager = AsyncMock()
    scheduler = AsyncMock()
    ctx = _schedule_context(["bogus", "cron", "x", "y", "z", "@master", "hi"])
    await handle_schedule_add(update, ctx, manager, scheduler, [123])
    scheduler.add_task.assert_not_called()
    reply = update.message.reply_text.call_args[0][0]
    assert "cron" in reply.lower() or "ошибка" in reply.lower()


@pytest.mark.asyncio
async def test_schedule_add_too_few_args():
    update = make_update(123, "/schedule_add")
    manager = AsyncMock()
    scheduler = AsyncMock()
    ctx = _schedule_context(["0", "*", "*"])
    await handle_schedule_add(update, ctx, manager, scheduler, [123])
    scheduler.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_add_unknown_agent():
    update = make_update(123, "/schedule_add")
    manager = AsyncMock()
    manager.get_agent.return_value = None
    scheduler = AsyncMock()
    ctx = _schedule_context(["0", "*", "*", "*", "*", "@ghost", "hi"])
    await handle_schedule_add(update, ctx, manager, scheduler, [123])
    scheduler.add_task.assert_not_called()
    reply = update.message.reply_text.call_args[0][0]
    assert "не найден" in reply


@pytest.mark.asyncio
async def test_schedule_add_empty_prompt():
    update = make_update(123, "/schedule_add")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master"}
    scheduler = AsyncMock()
    ctx = _schedule_context(["0", "*", "*", "*", "*", "@master"])
    await handle_schedule_add(update, ctx, manager, scheduler, [123])
    scheduler.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_list_empty():
    update = make_update(123, "/schedule_list")
    scheduler = AsyncMock()
    scheduler.list_tasks.return_value = []
    await handle_schedule_list(update, _schedule_context([]), scheduler, [123])
    reply = update.message.reply_text.call_args[0][0]
    assert "пуст" in reply.lower()


@pytest.mark.asyncio
async def test_schedule_list_with_tasks():
    update = make_update(123, "/schedule_list")
    scheduler = AsyncMock()
    scheduler.list_tasks.return_value = [
        {"id": 1, "cron_expression": "0 * * * *", "agent_name": "master",
         "prompt": "check mail", "enabled": 1, "last_run": None, "last_result": None},
    ]
    await handle_schedule_list(update, _schedule_context([]), scheduler, [123])
    reply = update.message.reply_text.call_args[0][0]
    assert "master" in reply
    assert "#1" in reply


@pytest.mark.asyncio
async def test_schedule_rm_success():
    update = make_update(123, "/schedule_rm")
    scheduler = AsyncMock()
    await handle_schedule_rm(update, _schedule_context(["7"]), scheduler, [123])
    scheduler.remove_task.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_schedule_rm_no_args():
    update = make_update(123, "/schedule_rm")
    scheduler = AsyncMock()
    await handle_schedule_rm(update, _schedule_context([]), scheduler, [123])
    scheduler.remove_task.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_run_success():
    update = make_update(123, "/schedule_run")
    scheduler = AsyncMock()
    await handle_schedule_run(update, _schedule_context(["3"]), scheduler, [123])
    scheduler.run_now.assert_awaited_once_with(3)


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
