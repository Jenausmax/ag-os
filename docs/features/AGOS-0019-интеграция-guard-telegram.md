---
id: AGOS-0019
title: Интеграция Prompt Guard в Telegram Bot
phase: 7 — Полировка
status: pending
depends_on: [AGOS-0008, AGOS-0012]
files_create: []
files_modify: [telegram/handlers.py, telegram/bot.py]
---

## Описание

Подключение Prompt Guard в поток обработки сообщений Telegram. После парсинга и перед отправкой агенту — проверка через PromptGuard. Заблокированные промты не доходят до агента, пользователь получает сообщение. Подозрительные — пропускаются с предупреждением.

## Acceptance Criteria

- [ ] Заблокированный промт → "Промт заблокирован" + не отправляется агенту
- [ ] Подозрительный промт → предупреждение + промт проходит
- [ ] Безопасный промт → без дополнительных сообщений
- [ ] guard=None (отключён) → работает как раньше
- [ ] Guard интегрирован в create_bot
- [ ] Все тесты проходят

## Затрагиваемые модули

- telegram/handlers.py: добавление guard в handle_message
- telegram/bot.py: добавление guard в create_bot

## Ключевые интерфейсы

Модификация существующих функций — добавление параметра `guard: PromptGuard | None = None`.

## Edge Cases

- guard=None — проверка пропускается
- Guard блокирует — промт не доходит до AgentManager

## План реализации

### Step 1: Обновить handlers.py — добавить guard в handle_message

Добавить параметр `guard: PromptGuard | None = None`. После `parse_message` и перед `send_prompt`:

```python
# Добавить в handle_message после parse_message:
if guard:
    verdict = await guard.check(prompt, agent_name)
    if verdict.blocked:
        await update.message.reply_text(
            f"🛡 Промт заблокирован ({verdict.reason})"
        )
        return
    if verdict.suspicious:
        await update.message.reply_text(
            f"⚠️ Подозрительный промт ({verdict.reason}), но пропущен."
        )
```

### Step 2: Обновить bot.py — подключить guard

Добавить `guard: PromptGuard | None = None` в `create_bot`. Передать в closure `on_message`.

### Step 3: Запустить все тесты

```bash
pytest tests/ -v --tb=short
```

### Step 4: Commit

```bash
git add telegram/handlers.py telegram/bot.py
git commit -m "feat: integrate PromptGuard into Telegram message flow"
```
