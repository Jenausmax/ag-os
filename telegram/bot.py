from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.handlers import handle_message, handle_agents_command
from core.agent_manager import AgentManager
from core.config import TelegramConfig
from guard.prompt_guard import PromptGuard

if TYPE_CHECKING:
    pass

# Импорт python-telegram-bot — доступен только при установленной библиотеке
from telegram.ext import Application, MessageHandler, CommandHandler, filters  # noqa: E402


def create_bot(
    config: TelegramConfig,
    manager: AgentManager,
    guard: PromptGuard | None = None,
) -> Application:
    app = Application.builder().token(config.token).build()
    allowed = config.allowed_users

    async def on_message(update, context):
        await handle_message(update, context, manager, allowed, guard)

    async def on_agents(update, context):
        await handle_agents_command(update, context, manager, allowed)

    app.add_handler(CommandHandler("agents", on_agents))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    return app
