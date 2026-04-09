---
id: AGOS-0008
title: Telegram Bot — обработчики и запуск
phase: 1 — MVP
status: pending
depends_on: [AGOS-0006, AGOS-0007]
files_create: [telegram/bot.py, telegram/handlers.py, tests/test_handlers.py]
files_modify: []
---

## Описание

Обработчики сообщений Telegram: авторизация по whitelist user ID, маршрутизация через router, отправка промтов агентам через AgentManager, команда /agents для отображения списка агентов со статусами. bot.py — сборка Application с хендлерами через python-telegram-bot.

## Acceptance Criteria

- [ ] is_authorized проверяет user_id в whitelist
- [ ] Пустой whitelist → все запрещены
- [ ] Неавторизованный пользователь → "Доступ запрещён"
- [ ] /agents показывает список с эмодзи-статусами
- [ ] handle_message отправляет промт через AgentManager
- [ ] create_bot собирает Application с CommandHandler и MessageHandler
- [ ] Тесты с моками проходят (5 тестов)

## Затрагиваемые модули

- telegram/handlers.py: is_authorized, handle_message, handle_agents_command
- telegram/bot.py: create_bot
- tests/test_handlers.py: юнит-тесты

## Ключевые интерфейсы

```python
def is_authorized(user_id: int, allowed_users: list[int]) -> bool
async def handle_message(update, context, manager, allowed_users)
async def handle_agents_command(update, context, manager, allowed_users)
def create_bot(config: TelegramConfig, manager: AgentManager) -> Application
```

## Edge Cases

- Пустой whitelist — все запрещены
- Агент не найден — сообщение об ошибке
- Пустой промт после тега

## План реализации

### Step 1: Написать тест

```python
# tests/test_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
```

### Step 2: Запустить тест — FAIL

```bash
pytest tests/test_handlers.py -v
```

### Step 3: Реализовать handlers.py

```python
# telegram/handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from telegram.router import parse_message
from core.agent_manager import AgentManager


def is_authorized(user_id: int, allowed_users: list[int]) -> bool:
    return user_id in allowed_users


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    manager: AgentManager,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return

    text = update.message.text
    agent_name, prompt = parse_message(text)

    agent = await manager.get_agent(agent_name)
    if not agent:
        await update.message.reply_text(f"Агент '{agent_name}' не найден.")
        return

    if not prompt:
        await update.message.reply_text(f"Пустой промт для агента '{agent_name}'.")
        return

    await manager.send_prompt(agent_name, prompt)
    await update.message.reply_text(f"Промт отправлен агенту '{agent_name}'.")


async def handle_agents_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    manager: AgentManager,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return

    agents = await manager.list_agents()
    if not agents:
        await update.message.reply_text("Нет активных агентов.")
        return

    lines = ["*Активные агенты:*\n"]
    for a in agents:
        status_emoji = {
            "idle": "🟢",
            "working": "🔵",
            "awaiting_confirmation": "🟡",
            "stopped": "🔴",
        }.get(a["status"], "⚪")
        task = a["current_task"] or "—"
        lines.append(f"{status_emoji} *{a['name']}* ({a['model']}) — {task}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
```

### Step 4: Реализовать bot.py

```python
# telegram/bot.py
from functools import partial
from telegram.ext import Application, MessageHandler, CommandHandler, filters
from telegram.handlers import handle_message, handle_agents_command
from core.agent_manager import AgentManager
from core.config import TelegramConfig


def create_bot(config: TelegramConfig, manager: AgentManager) -> Application:
    app = Application.builder().token(config.token).build()

    allowed = config.allowed_users

    async def on_message(update, context):
        await handle_message(update, context, manager, allowed)

    async def on_agents(update, context):
        await handle_agents_command(update, context, manager, allowed)

    app.add_handler(CommandHandler("agents", on_agents))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    return app
```

### Step 5: Запустить тест — PASS

```bash
pytest tests/test_handlers.py -v
```

Expected: 5 passed

### Step 6: Commit

```bash
git add telegram/bot.py telegram/handlers.py tests/test_handlers.py
git commit -m "feat: add Telegram bot with auth, routing, and /agents command"
```
