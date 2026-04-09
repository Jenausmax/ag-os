---
id: AGOS-0007
title: Telegram Bot — маршрутизация сообщений
phase: 1 — MVP
status: pending
depends_on: [AGOS-0001]
files_create: [telegram/router.py, tests/test_router.py]
files_modify: []
---

## Описание

Парсер входящих сообщений Telegram. Если сообщение начинается с `@тег` — направляет промт конкретному агенту, иначе — мастеру. Тег case-insensitive. Используется regex для парсинга.

## Acceptance Criteria

- [ ] `@jira отчёт` → agent="jira", prompt="отчёт"
- [ ] Без тега → agent="master", prompt=текст
- [ ] `@JIRA отчёт` → agent="jira" (case-insensitive)
- [ ] `@jira` (без промта) → agent="jira", prompt=""
- [ ] Тесты проходят (5 тестов)

## Затрагиваемые модули

- telegram/router.py: parse_message
- tests/test_router.py: юнит-тесты

## Ключевые интерфейсы

```python
TAG_PATTERN = re.compile(r"^@(\w+)\s*(.*)", re.DOTALL)

def parse_message(text: str) -> tuple[str, str]:
    """Парсит сообщение, возвращает (agent_name, prompt)."""
```

## Edge Cases

- Пустое сообщение после тега
- Тег в верхнем регистре
- Многострочный промт (re.DOTALL)

## План реализации

### Step 1: Написать тест

```python
# tests/test_router.py
from telegram.router import parse_message


def test_parse_tagged_message():
    agent, prompt = parse_message("@jira отчёт за вчера")
    assert agent == "jira"
    assert prompt == "отчёт за вчера"


def test_parse_untagged_message():
    agent, prompt = parse_message("подними агента для ревью")
    assert agent == "master"
    assert prompt == "подними агента для ревью"


def test_parse_tag_with_multiword():
    agent, prompt = parse_message("@code запусти тесты и покажи результат")
    assert agent == "code"
    assert prompt == "запусти тесты и покажи результат"


def test_parse_empty_after_tag():
    agent, prompt = parse_message("@jira")
    assert agent == "jira"
    assert prompt == ""


def test_parse_tag_case_insensitive():
    agent, prompt = parse_message("@JIRA отчёт")
    assert agent == "jira"
    assert prompt == "отчёт"
```

### Step 2: Запустить тест — FAIL

```bash
pytest tests/test_router.py -v
```

### Step 3: Реализовать router.py

```python
# telegram/router.py
import re

TAG_PATTERN = re.compile(r"^@(\w+)\s*(.*)", re.DOTALL)


def parse_message(text: str) -> tuple[str, str]:
    """Парсит сообщение, возвращает (agent_name, prompt).

    Если сообщение начинается с @tag — направляет конкретному агенту.
    Иначе — мастеру.
    """
    match = TAG_PATTERN.match(text.strip())
    if match:
        agent = match.group(1).lower()
        prompt = match.group(2).strip()
        return agent, prompt
    return "master", text.strip()
```

### Step 4: Запустить тест — PASS

```bash
pytest tests/test_router.py -v
```

Expected: 5 passed

### Step 5: Commit

```bash
git add telegram/router.py tests/test_router.py
git commit -m "feat: add message router with @tag parsing"
```
