---
id: AGOS-0014
title: TUI — экран агентов
phase: 3 — TUI Dashboard
status: pending
depends_on: [AGOS-0006]
files_create: [tui/app.py, tui/agents_screen.py]
files_modify: []
---

## Описание

TUI-дашборд на Textual. AgentsScreen — таблица агентов с live-обновлением каждые 2 секунды. Колонки: Name, Status (с эмодзи), Model, Task, Runtime, Preview (последняя строка вывода). Docker-агенты отмечены 🐳. Горячие клавиши: N (new), K (kill), Enter (open), S (schedule), L (logs), Q (quit). AgOsApp — главное приложение с CSS-стилизацией.

## Acceptance Criteria

- [ ] AgentsScreen рендерит DataTable с 6 колонками
- [ ] Live-обновление через set_interval(2.0)
- [ ] Docker-агенты отмечены 🐳
- [ ] Статусы отображаются с эмодзи (🟢🔵🟡🔴)
- [ ] Горячие клавиши привязаны через BINDINGS
- [ ] AgOsApp пушит AgentsScreen при монтировании
- [ ] Импорты проходят

## Затрагиваемые модули

- tui/agents_screen.py: AgentsScreen
- tui/app.py: AgOsApp

## Ключевые интерфейсы

```python
class AgentsScreen(Screen):
    BINDINGS = [("n", "new_agent", "New"), ("k", "kill_agent", "Kill"), ("enter", "open_agent", "Open"), ("s", "schedule", "Schedule"), ("l", "logs", "Logs"), ("q", "quit", "Quit")]
    def __init__(self, manager: AgentManager)
    async def on_mount(self)
    async def refresh_agents(self)

class AgOsApp(App):
    def __init__(self, manager: AgentManager)
    def on_mount(self)
```

## Edge Cases

- Пустой список агентов — пустая таблица
- Ошибка при read_output — preview = "—"
- Длинная задача обрезается до 30 символов

## План реализации

### Step 1: Реализовать agents_screen.py

```python
# tui/agents_screen.py
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static
from textual.containers import Container
from core.agent_manager import AgentManager

STATUS_EMOJI = {
    "idle": "🟢",
    "working": "🔵",
    "awaiting_confirmation": "🟡",
    "stopped": "🔴",
}


class AgentsScreen(Screen):
    BINDINGS = [
        ("n", "new_agent", "New"),
        ("k", "kill_agent", "Kill"),
        ("enter", "open_agent", "Open"),
        ("s", "schedule", "Schedule"),
        ("l", "logs", "Logs"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, manager: AgentManager):
        super().__init__()
        self.manager = manager

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("AG-OS Dashboard", id="title")
        yield DataTable(id="agents-table")
        yield Footer()

    async def on_mount(self):
        table = self.query_one("#agents-table", DataTable)
        table.add_columns("Name", "Status", "Model", "Task", "Runtime", "Preview")
        await self.refresh_agents()
        self.set_interval(2.0, self.refresh_agents)

    async def refresh_agents(self):
        table = self.query_one("#agents-table", DataTable)
        table.clear()
        agents = await self.manager.list_agents()
        for a in agents:
            emoji = STATUS_EMOJI.get(a["status"], "⚪")
            runtime_icon = "🐳" if a["runtime"] == "docker" else ""
            name = f"{runtime_icon}{a['name']}"
            task = (a["current_task"] or "—")[:30]
            preview = ""
            try:
                out = await self.manager.read_output(a["name"])
                preview = out.strip().split("\n")[-1][:40] if out.strip() else ""
            except Exception:
                preview = "—"
            table.add_row(name, f"{emoji} {a['status']}", a["model"], task, a["runtime"], preview)
```

### Step 2: Реализовать app.py

```python
# tui/app.py
from textual.app import App
from tui.agents_screen import AgentsScreen
from core.agent_manager import AgentManager


class AgOsApp(App):
    TITLE = "AG-OS"
    CSS = """
    #title {
        text-align: center;
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    DataTable {
        height: 1fr;
    }
    """

    def __init__(self, manager: AgentManager):
        super().__init__()
        self.manager = manager

    def on_mount(self):
        self.push_screen(AgentsScreen(self.manager))
```

### Step 3: Проверить импорты

```bash
python -c "from tui.app import AgOsApp; print('OK')"
```

### Step 4: Commit

```bash
git add tui/app.py tui/agents_screen.py
git commit -m "feat: add TUI dashboard with agents table (Textual)"
```
