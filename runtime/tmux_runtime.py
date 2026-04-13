import libtmux
from runtime.base import BaseRuntime


class TmuxRuntime(BaseRuntime):
    def __init__(self, session_name: str):
        self.session_name = session_name
        self._server = libtmux.Server()
        sessions = self._server.sessions.filter(session_name=session_name)
        if sessions:
            self._session = sessions[0]
        else:
            self._session = self._server.new_session(session_name=session_name, attach=False)

    def create_agent(self, name: str, command: str = "", env: dict[str, str] | None = None) -> str:
        window = self._session.new_window(window_name=name, attach=False)
        if env:
            for key, value in env.items():
                window.active_pane.send_keys(f"export {key}={value}")
        if command:
            window.active_pane.send_keys(command)
        return window.name

    def apply_env(self, name: str, env: dict[str, str]) -> None:
        windows = self._session.windows.filter(window_name=name)
        if not windows:
            raise ValueError(f"Agent '{name}' not found")
        pane = windows[0].active_pane
        for key, value in env.items():
            pane.send_keys(f"export {key}={value}")

    def destroy_agent(self, name: str) -> None:
        windows = self._session.windows.filter(window_name=name)
        if windows:
            windows[0].kill()

    def send_prompt(self, name: str, prompt: str) -> None:
        windows = self._session.windows.filter(window_name=name)
        if not windows:
            raise ValueError(f"Agent '{name}' not found")
        windows[0].active_pane.send_keys(prompt)

    def read_output(self, name: str, lines: int = 50) -> str:
        windows = self._session.windows.filter(window_name=name)
        if not windows:
            raise ValueError(f"Agent '{name}' not found")
        captured = windows[0].active_pane.capture_pane()
        return "\n".join(captured)

    def list_agents(self) -> list[str]:
        return [w.name for w in self._session.windows]

    def agent_exists(self, name: str) -> bool:
        return bool(self._session.windows.filter(window_name=name))
