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
