---
id: AGOS-0036
title: MCP-сервер ag-os-telegram для двусторонней связи мастера с Telegram
phase: 8 — Two-way Telegram
status: completed
depends_on: [AGOS-0035]
files_create: [mcp_servers/__init__.py, mcp_servers/telegram_bridge.py, .claude/skills/agos-telegram-reply/SKILL.md, tests/test_telegram_bridge.py, docs/features/AGOS-0036-mcp-telegram-bridge.md]
files_modify: [requirements.txt, tgbot/handlers.py, tests/test_handlers.py, docs/quick-start.md]
---

## Описание

До этой фичи AG-OS-бот работал односторонне: пользовательский промт долетал до мастера через `tmux send_keys`, но ответ мастера оставался во внутреннем pane. Пользователь видел только «Промт отправлен агенту master» и должен был делать `tmux attach` чтобы увидеть что происходит дальше.

Фикс — MCP-сервер `ag-os-telegram`, который даёт мастеру одно-единственное tool:

```
telegram_reply(chat_id: int, text: str) -> {ok: True, message_id: int}
```

Мастер вызывает его когда хочет ответить пользователю. Сервер — обычный MCP stdio-процесс, запускается вместе с Claude Code через `claude mcp add`, шлёт POST в `api.telegram.org/bot<token>/sendMessage`.

Для того чтобы мастер знал **куда** отвечать (какой `chat_id`), AG-OS-бот в `handle_message` прикрепляет однострочную преамбулу к каждому входящему промту: `[ag-os chat=<chat_id> user=<username>]`. Мастер парсит её и передаёт `chat_id` в tool. Новый скилл `agos-telegram-reply` с `description` в верхней категории важности учит его делать это **всегда**, когда видит преамбулу.

## Acceptance Criteria

- [x] `mcp_servers/telegram_bridge.py` — FastMCP-сервер с tool `telegram_reply`
- [x] Конфиг токена через env `TELEGRAM_BOT_TOKEN` или из `config.yaml` (fallback)
- [x] `mcp` в `requirements.txt`
- [x] `tgbot/handlers.py.build_context_preamble()` — формирует `[ag-os chat=X user=Y]` с fallback username → first_name → id, заменой пробелов на `_`
- [x] `handle_message` оборачивает промт преамбулой перед `send_prompt`
- [x] `.claude/skills/agos-telegram-reply/SKILL.md` с жирным правилом «всегда отвечай через tool если видишь префикс»
- [x] Тесты: 4 варианта preamble, интеграционный тест handle_message → send_prompt с преамбулой, 6 тестов MCP-сервера (env/config/cache/success/error)
- [x] Документация: секция в quick-start с инструкцией по установке через `claude mcp add`

## Архитектура

```
пользователь → Telegram
    ↓ (update)
tgbot/handlers.handle_message
    ↓ (промт + preamble)
TmuxRuntime.send_prompt
    ↓ (send_keys в окно master)
claude REPL в tmux
    ↓ (решает ответить)
MCP stdio ← → ag-os-telegram subprocess
    ↓ (httpx POST)
api.telegram.org/bot<token>/sendMessage
    ↓
пользователь видит ответ в Telegram
```

Ключевые моменты:

- **chat_id** передаётся explicit через tool, а не unclеарно через "current chat" глобальное состояние — поэтому multi-user работает из коробки
- **MCP процесс subprocess** — не стартует вместе с AG-OS ботом, а поднимается самим Claude Code при вызове tool. Отдельный Python-процесс со своим httpx-клиентом
- **Токен** — не дублируется в коде мастера, читается через env или config.yaml
- **Markdown** — пока не поддерживается. Plain text only, многострочный можно

## Установка (на сервере)

Один раз после pull'а ветки:

```bash
cd ~/ag-os
source .venv/bin/activate
pip install -r requirements.txt   # подтянет mcp
claude mcp add ag-os-telegram -- $PWD/.venv/bin/python -m mcp_servers.telegram_bridge
```

Проверка регистрации:

```bash
claude mcp list
```

После этого — destroy + recreate мастера (чтобы новый claude-процесс подхватил MCP):

```bash
python main.py --config config.yaml agent destroy --name master
# запустить бот — bootstrap пересоздаст master
```

## Edge Cases

- **Toкен отсутствует везде** → MCP-сервер падает при первом вызове tool с `RuntimeError: telegram bot token not found`. Скилл говорит мастеру сообщить пользователю через pane.
- **Telegram API ответил `ok: False`** → `RuntimeError: Telegram API error: {...}`. Мастер должен укоротить text или упростить.
- **Текст > 4096 символов** → Telegram отрежет или отклонит. Документировано в скилле — мастер должен разбивать.
- **Одновременные сообщения от двух пользователей** → работает: каждое попадает в claude REPL со своей преамбулой, мастер отвечает каждому в свой chat_id.
- **Markdown в text** → попадёт как сырые символы (parse_mode не задан). Скилл явно предупреждает не использовать.

## Что НЕ сделано в этой итерации

- Автоматическая регистрация MCP через setup.sh или bootstrap — требует `claude mcp add` CLI с правами и интерактивным подтверждением. Делается руками один раз.
- Поддержка Markdown / HTML parse_mode — надо добавить опциональный параметр.
- Кнопки / inline keyboards через tool — отдельная задача если понадобится.
- Ответы с медиа (фото/файл) — аналогично, отдельный tool.
- Восстановление текущего состояния diff из pane в Telegram — намеренно не делаем, дизайн через явный tool-вызов чище и масштабируемее.
