from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static
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
