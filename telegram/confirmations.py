from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def build_confirmation_message(
    agent_name: str, action: str
) -> tuple[str, list[list[dict]]]:
    """Создаёт текст и клавиатуру для подтверждения опасного действия.

    Возвращает (text, keyboard) где keyboard — список рядов кнопок.
    Каждая кнопка — dict с text и callback_data.
    При отправке в Telegram конвертируется в InlineKeyboardButton.
    """
    request_id = uuid.uuid4().hex[:8]
    text = f"🔴 Агент [{agent_name}] запрашивает подтверждение:\n\n> {action}"
    keyboard = [
        [
            {"text": "✅ Подтвердить", "callback_data": f"confirm:{agent_name}:{request_id}:approve"},
            {"text": "❌ Отклонить", "callback_data": f"confirm:{agent_name}:{request_id}:deny"},
        ]
    ]
    return text, keyboard


def parse_callback_data(data: str) -> dict | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "confirm":
        return None
    return {"agent": parts[1], "request_id": parts[2], "action": parts[3]}
