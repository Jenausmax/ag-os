from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telegram.router import parse_message
from core.agent_manager import AgentManager
from guard.prompt_guard import PromptGuard

if TYPE_CHECKING:
    pass


def is_authorized(user_id: int, allowed_users: list[int]) -> bool:
    return user_id in allowed_users


async def handle_message(
    update: Any,
    context: Any,
    manager: AgentManager,
    allowed_users: list[int],
    guard: PromptGuard | None = None,
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
    if guard:
        verdict = await guard.check(prompt, agent_name)
        if verdict.blocked:
            await update.message.reply_text(f"🛡 Промт заблокирован ({verdict.reason})")
            return
        if verdict.suspicious:
            await update.message.reply_text(
                f"⚠️ Подозрительный промт ({verdict.reason}), но пропущен."
            )
    await manager.send_prompt(agent_name, prompt)
    await update.message.reply_text(f"Промт отправлен агенту '{agent_name}'.")


async def handle_agents_command(update: Any, context: Any, manager: AgentManager, allowed_users: list[int]):
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
        status_emoji = {"idle": "🟢", "working": "🔵", "awaiting_confirmation": "🟡", "stopped": "🔴"}.get(a["status"], "⚪")
        task = a["current_task"] or "—"
        lines.append(f"{status_emoji} *{a['name']}* ({a['model']}) — {task}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
