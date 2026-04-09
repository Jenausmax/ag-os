---
id: AGOS-0021
title: Интеграция TUI и main.py
phase: 7 — Полировка
status: pending
depends_on: [AGOS-0009, AGOS-0014]
files_create: []
files_modify: [main.py]
---

## Описание

Добавление режима TUI в main.py. Режим `tui` запускает Textual-приложение AgOsApp. Режим `all` запускает бот и TUI параллельно через asyncio-задачи. Все компоненты инициализируются одинаково для обоих режимов.

## Acceptance Criteria

- [ ] `python main.py tui` запускает TUI-дашборд
- [ ] `python main.py all` запускает бот и TUI параллельно
- [ ] Все компоненты (БД, tmux, AgentManager) инициализируются
- [ ] Мастер-агент создаётся при старте

## Затрагиваемые модули

- main.py: run_tui, обновлённый main

## Ключевые интерфейсы

```python
async def run_tui(config_path: str)
```

## Edge Cases

- TUI без tmux (только просмотр из БД)
- Параллельный запуск bot + TUI

## План реализации

### Step 1: Обновить main.py — поддержка mode=tui и mode=all

```python
# Добавить в main.py:
async def run_tui(config_path: str):
    config = load_config(config_path)
    db = Database(config.database.path)
    await db.init()
    tmux = TmuxRuntime(config.agents.session_name)
    manager = AgentManager(db=db, tmux_runtime=tmux)
    from tui.app import AgOsApp
    app = AgOsApp(manager)
    await app.run_async()
```

Для `mode=all` запустить бота и TUI в параллельных asyncio-задачах.

### Step 2: Проверить запуск

```bash
python main.py tui --config config.yaml
```

### Step 3: Commit

```bash
git add main.py
git commit -m "feat: integrate TUI mode and all-in-one startup"
```
