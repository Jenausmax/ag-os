import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from tgbot.handlers import (
    is_authorized,
    handle_message,
    handle_agents_command,
    handle_pane_command,
    handle_schedule_add,
    handle_schedule_list,
    handle_schedule_rm,
    handle_schedule_run,
    build_context_preamble,
    PANE_FOLLOWUP_TIMEOUT,
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


def _make_update_with_chat(user_id: int, chat_id: int, text: str, username: str = "Max"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = username
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def test_build_context_preamble_with_username():
    update = _make_update_with_chat(1, 249402107, "hi", username="Max")
    preamble = build_context_preamble(update)
    assert preamble == "[ag-os chat=249402107 user=Max]"


def test_build_context_preamble_falls_back_to_first_name():
    update = MagicMock()
    update.effective_chat.id = 42
    update.effective_user.username = None
    update.effective_user.first_name = "Vasya"
    update.effective_user.id = 7
    assert build_context_preamble(update) == "[ag-os chat=42 user=Vasya]"


def test_build_context_preamble_falls_back_to_user_id():
    update = MagicMock()
    update.effective_chat.id = 42
    update.effective_user.username = None
    update.effective_user.first_name = None
    update.effective_user.id = 7
    assert build_context_preamble(update) == "[ag-os chat=42 user=7]"


def test_build_context_preamble_replaces_spaces_in_name():
    update = _make_update_with_chat(1, 42, "hi", username=None)
    update.effective_user.username = None
    update.effective_user.first_name = "Maxim Minaev"
    assert build_context_preamble(update) == "[ag-os chat=42 user=Maxim_Minaev]"


@pytest.mark.asyncio
async def test_handle_message_prepends_context_preamble():
    update = _make_update_with_chat(123, 249402107, "@master привет")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master", "status": "idle"}
    await handle_message(update, MagicMock(), manager, [123])
    sent = manager.send_prompt.call_args[0][1]
    assert sent.startswith("[ag-os chat=249402107 user=Max] ")
    assert sent.endswith("привет")


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


# ─────────────────────────── /pane (AGOS-0040) ────────────────────────────

def _pane_context(args: list[str], user_data: dict | None = None):
    ctx = MagicMock()
    ctx.args = args
    ctx.user_data = user_data if user_data is not None else {}
    return ctx


@pytest.mark.asyncio
async def test_handle_pane_command_unauthorized():
    update = make_update(999, "/pane")
    manager = AsyncMock()
    await handle_pane_command(update, _pane_context([]), manager, [123])
    manager.read_output.assert_not_called()
    update.message.reply_text.assert_called_once()
    assert "авторизован" in update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_handle_pane_command_unknown_agent():
    update = make_update(123, "/pane ghost")
    manager = AsyncMock()
    manager.get_agent.return_value = None
    await handle_pane_command(update, _pane_context(["ghost"]), manager, [123])
    update.message.reply_text.assert_called_once()
    assert "ghost" in update.message.reply_text.call_args[0][0]
    manager.read_output.assert_not_called()


@pytest.mark.asyncio
async def test_handle_pane_command_default_agent_is_master():
    update = make_update(123, "/pane")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master", "status": "idle"}
    manager.read_output.return_value = "line1\nline2\n❯ 1. Dark\n   2. Light"
    ctx = _pane_context([])
    await handle_pane_command(update, ctx, manager, [123])
    manager.get_agent.assert_awaited_once_with("master")
    manager.read_output.assert_awaited_once()
    assert ctx.user_data["pane_followup"]["agent"] == "master"
    assert ctx.user_data["pane_followup"]["expires_at"] > time.time()
    reply = update.message.reply_text.call_args[0][0]
    assert "master" in reply
    assert "Dark" in reply


@pytest.mark.asyncio
async def test_handle_pane_command_named_agent_sets_followup():
    update = make_update(123, "/pane finik")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "finik", "status": "idle"}
    manager.read_output.return_value = "(y/N)?"
    ctx = _pane_context(["finik"])
    await handle_pane_command(update, ctx, manager, [123])
    assert ctx.user_data["pane_followup"]["agent"] == "finik"


@pytest.mark.asyncio
async def test_handle_message_pane_followup_sends_raw():
    update = _make_update_with_chat(123, 42, "1")
    manager = AsyncMock()
    ctx = MagicMock()
    ctx.user_data = {
        "pane_followup": {"agent": "master", "expires_at": time.time() + 60},
    }
    await handle_message(update, ctx, manager, [123])
    manager.send_raw.assert_awaited_once_with("master", "1")
    manager.send_prompt.assert_not_called()
    assert "pane_followup" not in ctx.user_data
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_pane_followup_expired_falls_through():
    update = _make_update_with_chat(123, 42, "@master привет")
    manager = AsyncMock()
    manager.get_agent.return_value = {"name": "master", "status": "idle"}
    ctx = MagicMock()
    ctx.user_data = {
        "pane_followup": {"agent": "master", "expires_at": time.time() - 10},
    }
    await handle_message(update, ctx, manager, [123])
    manager.send_raw.assert_not_called()
    manager.send_prompt.assert_awaited_once()
    sent = manager.send_prompt.call_args[0][1]
    assert sent.endswith("привет")
