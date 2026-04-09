import json
from core.models import AgentRuntime, AgentStatus
from db.database import Database
from runtime.base import BaseRuntime


class AgentManager:
    def __init__(self, db: Database, tmux_runtime: BaseRuntime | None = None, docker_runtime: BaseRuntime | None = None):
        self.db = db
        self._tmux = tmux_runtime
        self._docker = docker_runtime

    def _get_runtime(self, runtime: AgentRuntime) -> BaseRuntime:
        if runtime == AgentRuntime.HOST:
            if not self._tmux:
                raise RuntimeError("tmux runtime not configured")
            return self._tmux
        if not self._docker:
            raise RuntimeError("docker runtime not configured")
        return self._docker

    async def create_agent(self, name: str, model: str, runtime: AgentRuntime, agent_type: str = "dynamic", config: dict | None = None) -> dict:
        existing = await self.db.fetch_one("SELECT id FROM agents WHERE name = ?", (name,))
        if existing:
            raise ValueError(f"Agent '{name}' already exists")
        rt = self._get_runtime(runtime)
        rt.create_agent(name)
        await self.db.execute(
            "INSERT INTO agents (name, model, runtime, type, status, tmux_window, config) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, model, runtime.value, agent_type, AgentStatus.IDLE.value, name if runtime == AgentRuntime.HOST else "", json.dumps(config or {})),
        )
        return await self.get_agent(name)

    async def destroy_agent(self, name: str) -> None:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        rt.destroy_agent(name)
        await self.db.execute("DELETE FROM agents WHERE name = ?", (name,))

    async def send_prompt(self, name: str, prompt: str) -> None:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        rt.send_prompt(name, prompt)
        await self.db.execute("UPDATE agents SET status = ?, current_task = ? WHERE name = ?", (AgentStatus.WORKING.value, prompt, name))

    async def read_output(self, name: str, lines: int = 50) -> str:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        return rt.read_output(name, lines)

    async def get_agent(self, name: str) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM agents WHERE name = ?", (name,))

    async def list_agents(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM agents ORDER BY name")

    async def update_status(self, name: str, status: AgentStatus) -> None:
        await self.db.execute("UPDATE agents SET status = ? WHERE name = ?", (status.value, name))
