---
id: AGOS-0020
title: Интеграция Memory в Agent Manager
phase: 7 — Полировка
status: pending
depends_on: [AGOS-0006, AGOS-0016]
files_create: []
files_modify: [core/agent_manager.py]
---

## Описание

Подключение Memory System в Agent Manager. При отправке промта агенту — загрузка контекста памяти и добавление как преамбулы. Формат: `[Memory] key: value`. Мастер получает все записи, агенты — только доступные по scope.

## Acceptance Criteria

- [ ] send_prompt загружает контекст памяти перед отправкой
- [ ] Контекст добавляется как преамбула `[Memory] key: value`
- [ ] Если памяти нет — промт отправляется без изменений
- [ ] Если memory=None — работает как раньше
- [ ] Все тесты проходят

## Затрагиваемые модули

- core/agent_manager.py: добавление memory в __init__ и send_prompt

## Ключевые интерфейсы

Модификация AgentManager:
- `__init__` — добавление `memory: MemorySystem | None = None`
- `send_prompt` — инъекция контекста памяти

## Edge Cases

- memory=None — без изменений
- Пустой контекст — промт без преамбулы
- Большой контекст — много записей в преамбуле

## План реализации

### Step 1: Добавить Memory в send_prompt

Добавить `self._memory = memory` в `__init__`. В `send_prompt` перед `rt.send_prompt()`:

```python
if self._memory:
    context = await self._memory.get_context(name)
    if context:
        memory_lines = [f"[Memory] {r['key']}: {r['value']}" for r in context]
        prompt = "\n".join(memory_lines) + "\n\n" + prompt
```

### Step 2: Запустить тесты

```bash
pytest tests/ -v --tb=short
```

### Step 3: Commit

```bash
git add core/agent_manager.py
git commit -m "feat: inject agent memory context into prompts"
```
