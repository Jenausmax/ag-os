from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apscheduler.triggers.cron import CronTrigger

from telegram.router import parse_message
from core.agent_manager import AgentManager
from guard.prompt_guard import PromptGuard
from scheduler.scheduler import AgScheduler

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


def _parse_cron_and_rest(args: list[str]) -> tuple[str, list[str]]:
    if len(args) < 6:
        raise ValueError("нужно 5 полей cron + @agent + промт")
    cron = " ".join(args[:5])
    try:
        CronTrigger.from_crontab(cron)
    except Exception as e:
        raise ValueError(f"невалидный cron: {e}")
    return cron, args[5:]


async def handle_schedule_add(
    update: Any,
    context: Any,
    manager: AgentManager,
    scheduler: AgScheduler,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return
    try:
        cron, rest = _parse_cron_and_rest(context.args or [])
    except ValueError as e:
        await update.message.reply_text(
            f"Использование: /schedule_add <min> <hour> <day> <month> <dow> @agent <prompt>\nОшибка: {e}"
        )
        return
    raw = " ".join(rest)
    agent_name, prompt = parse_message(raw)
    if not prompt:
        await update.message.reply_text("Пустой промт.")
        return
    agent = await manager.get_agent(agent_name)
    if not agent:
        await update.message.reply_text(f"Агент '{agent_name}' не найден.")
        return
    task_id = await scheduler.add_task(cron, agent_name, prompt)
    await update.message.reply_text(
        f"🗓 Задача #{task_id} создана: `{cron}` → @{agent_name}",
        parse_mode="Markdown",
    )


async def handle_schedule_list(
    update: Any,
    context: Any,
    scheduler: AgScheduler,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return
    tasks = await scheduler.list_tasks()
    if not tasks:
        await update.message.reply_text("Расписание пустое.")
        return
    lines = ["*Расписание:*\n"]
    for t in tasks:
        enabled = "✅" if t.get("enabled") else "⏸"
        last = t.get("last_run") or "—"
        result = t.get("last_result") or "—"
        lines.append(
            f"{enabled} #{t['id']} `{t['cron_expression']}` → @{t['agent_name']}\n"
            f"    prompt: {t['prompt'][:60]}\n"
            f"    last: {last} ({result})"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_schedule_rm(
    update: Any,
    context: Any,
    scheduler: AgScheduler,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /schedule_rm <id>")
        return
    task_id = int(args[0])
    await scheduler.remove_task(task_id)
    await update.message.reply_text(f"🗑 Задача #{task_id} удалена.")


async def handle_schedule_run(
    update: Any,
    context: Any,
    scheduler: AgScheduler,
    allowed_users: list[int],
):
    user_id = update.effective_user.id
    if not is_authorized(user_id, allowed_users):
        await update.message.reply_text("Доступ запрещён. Пользователь не авторизован.")
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /schedule_run <id>")
        return
    task_id = int(args[0])
    await scheduler.run_now(task_id)
    await update.message.reply_text(f"▶️ Задача #{task_id} запущена вручную.")


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
