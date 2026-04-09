---
id: AGOS-0013
title: Telegram подтверждения (inline-кнопки)
phase: 2 — Безопасность
status: pending
depends_on: [AGOS-0008]
files_create: [telegram/confirmations.py, tests/test_confirmations.py]
files_modify: []
---

## Описание

Механизм inline-кнопок для подтверждения опасных действий агентов через Telegram. Генерирует сообщение с описанием действия и двумя кнопками: "Подтвердить" / "Отклонить". Парсит callback_data для определения агента, request_id и решения.

## Acceptance Criteria

- [ ] build_confirmation_message создаёт текст с именем агента и действием
- [ ] Клавиатура содержит 1 ряд с 2 кнопками
- [ ] parse_callback_data парсит approve/deny
- [ ] Невалидный callback_data → None
- [ ] Тесты проходят (4 теста)

## Затрагиваемые модули

- telegram/confirmations.py: build_confirmation_message, parse_callback_data
- tests/test_confirmations.py: юнит-тесты

## Ключевые интерфейсы

```python
def build_confirmation_message(agent_name: str, action: str) -> tuple[str, list[list[InlineKeyboardButton]]]
def parse_callback_data(data: str) -> dict | None
```

## Edge Cases

- Невалидный callback_data формат
- Длинное описание действия
- Уникальный request_id для каждого подтверждения

## План реализации

### Step 1: Написать тест

```python
# tests/test_confirmations.py
import pytest
from telegram.confirmations import build_confirmation_message, parse_callback_data


def test_build_confirmation_message():
    text, keyboard = build_confirmation_message(
        agent_name="code",
        action="git push --force origin main",
    )
    assert "code" in text
    assert "git push --force" in text
    assert len(keyboard) == 1
    assert len(keyboard[0]) == 2


def test_parse_callback_approve():
    result = parse_callback_data("confirm:code:abc123:approve")
    assert result["agent"] == "code"
    assert result["request_id"] == "abc123"
    assert result["action"] == "approve"


def test_parse_callback_deny():
    result = parse_callback_data("confirm:jira:xyz789:deny")
    assert result["agent"] == "jira"
    assert result["action"] == "deny"


def test_parse_callback_invalid():
    result = parse_callback_data("invalid_data")
    assert result is None
```

### Step 2: Реализовать confirmations.py

```python
# telegram/confirmations.py
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_confirmation_message(
    agent_name: str, action: str
) -> tuple[str, list[list[InlineKeyboardButton]]]:
    request_id = uuid.uuid4().hex[:8]
    text = f"🔴 Агент [{agent_name}] запрашивает подтверждение:\n\n> {action}"
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Подтвердить",
                callback_data=f"confirm:{agent_name}:{request_id}:approve",
            ),
            InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"confirm:{agent_name}:{request_id}:deny",
            ),
        ]
    ]
    return text, keyboard


def parse_callback_data(data: str) -> dict | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "confirm":
        return None
    return {
        "agent": parts[1],
        "request_id": parts[2],
        "action": parts[3],
    }
```

### Step 3: Запустить тесты — PASS

```bash
pytest tests/test_confirmations.py -v
```

### Step 4: Commit

```bash
git add telegram/confirmations.py tests/test_confirmations.py
git commit -m "feat: add inline confirmation buttons for dangerous actions"
```
