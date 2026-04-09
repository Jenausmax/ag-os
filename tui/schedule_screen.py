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
