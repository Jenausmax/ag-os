from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.handlers import (
    handle_message,
    handle_agents_command,
    handle_schedule_add,
    handle_schedule_list,
    handle_schedule_rm,
    handle_schedule_run,
)
from core.agent_manager import AgentManager
from core.config import TelegramConfig
from guard.prompt_guard import PromptGuard
from scheduler.scheduler import AgScheduler

if TYPE_CHECKING:
    pass

# Импорт python-telegram-bot — доступен только при установленной библиотеке
from telegram.ext import Application, MessageHandler, CommandHandler, filters  # noqa: E402


def create_bot(
    config: TelegramConfig,
    manager: AgentManager,
    guard: PromptGuard | None = None,
    scheduler: AgScheduler | None = None,
) -> Application:
    app = Application.builder().token(config.token).build()
    allowed = config.allowed_users

    async def on_message(update, context):
        await handle_message(update, context, manager, allowed, guard)

    async def on_agents(update, context):
        await handle_agents_command(update, context, manager, allowed)

    app.add_handler(CommandHandler("agents", on_agents))

    if scheduler is not None:
        async def on_schedule_add(update, context):
            await handle_schedule_add(update, context, manager, scheduler, allowed)

        async def on_schedule_list(update, context):
            await handle_schedule_list(update, context, scheduler, allowed)

        async def on_schedule_rm(update, context):
            await handle_schedule_rm(update, context, scheduler, allowed)

        async def on_schedule_run(update, context):
            await handle_schedule_run(update, context, scheduler, allowed)

        app.add_handler(CommandHandler("schedule_add", on_schedule_add))
        app.add_handler(CommandHandler("schedule_list", on_schedule_list))
        app.add_handler(CommandHandler("schedule_rm", on_schedule_rm))
        app.add_handler(CommandHandler("schedule_run", on_schedule_run))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    return app
