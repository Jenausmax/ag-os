---
id: AGOS-0015
title: TUI — экран расписания
phase: 3 — TUI Dashboard
status: pending
depends_on: [AGOS-0003]
files_create: [tui/schedule_screen.py]
files_modify: []
---

## Описание

Экран расписания в TUI-дашборде. Таблица cron-задач из SQLite с колонками: ID, Cron, Agent, Prompt, Enabled, Last Run, Result. Горячие клавиши: A (add), D (delete), R (run now), B (back). Переключение с экрана агентов по клавише S.

## Acceptance Criteria

- [ ] DataTable с 7 колонками рендерится
- [ ] Данные загружаются из таблицы schedule
- [ ] Enabled отображается как ✅/❌
- [ ] Длинный промт обрезается до 30 символов
- [ ] action_back возвращает на предыдущий экран
- [ ] Горячие клавиши привязаны

## Затрагиваемые модули

- tui/schedule_screen.py: ScheduleScreen

## Ключевые интерфейсы

```python
class ScheduleScreen(Screen):
    BINDINGS = [("a", "add_task", "Add"), ("d", "delete_task", "Delete"), ("r", "run_now", "Run Now"), ("b", "back", "Back")]
    def __init__(self, db: Database)
    async def on_mount(self)
    async def refresh_schedule(self)
    def action_back(self)
```

## Edge Cases

- Пустое расписание — пустая таблица
- last_run = None → "—"
- Длинный промт обрезается

## План реализации

### Step 1: Реализовать schedule_screen.py

```python
# tui/schedule_screen.py
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static
from db.database import Database


class ScheduleScreen(Screen):
    BINDINGS = [
        ("a", "add_task", "Add"),
        ("d", "delete_task", "Delete"),
        ("r", "run_now", "Run Now"),
        ("b", "back", "Back"),
    ]

    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Scheduled Tasks", id="title")
        yield DataTable(id="schedule-table")
        yield Footer()

    async def on_mount(self):
        table = self.query_one("#schedule-table", DataTable)
        table.add_columns("ID", "Cron", "Agent", "Prompt", "Enabled", "Last Run", "Result")
        await self.refresh_schedule()

    async def refresh_schedule(self):
        table = self.query_one("#schedule-table", DataTable)
        table.clear()
        tasks = await self.db.fetch_all("SELECT * FROM schedule ORDER BY id")
        for t in tasks:
            enabled = "✅" if t["enabled"] else "❌"
            last_run = t["last_run"] or "—"
            result = t["last_result"] or "—"
            prompt = (t["prompt"] or "")[:30]
            table.add_row(
                str(t["id"]), t["cron_expression"], t["agent_name"],
                prompt, enabled, str(last_run), result,
            )

    def action_back(self):
        self.app.pop_screen()
```

### Step 2: Commit

```bash
git add tui/schedule_screen.py
git commit -m "feat: add TUI schedule screen"
```
