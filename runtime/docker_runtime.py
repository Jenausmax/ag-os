import docker

from runtime.base import BaseRuntime


class DockerRuntime(BaseRuntime):
    def __init__(
        self,
        prefix: str = "ag-os",
        image: str = "ag-os-full:latest",
        cpus: float = 2,
        memory: str = "4g",
        network: str = "bridge",
        workspace_base: str = "/data/ag-os/workspaces",
        shared_dir: str = "/data/ag-os/shared",
    ):
        self.prefix = prefix
        self.image = image
        self.cpus = cpus
        self.memory = memory
        self.network = network
        self.workspace_base = workspace_base
        self.shared_dir = shared_dir
        self._client = docker.from_env()

    def _container_name(self, name: str) -> str:
        return f"{self.prefix}-{name}"

    def create_agent(self, name: str, command: str = "") -> str:
        container_name = self._container_name(name)
        volumes = {
            f"{self.workspace_base}/{name}": {"bind": "/workspace", "mode": "rw"},
            self.shared_dir: {"bind": "/shared", "mode": "ro"},
        }
        container = self._client.containers.run(
            self.image,
            command=command or "tail -f /dev/null",
            name=container_name,
            detach=True,
            nano_cpus=int(self.cpus * 1e9),
            mem_limit=self.memory,
            network=self.network,
            volumes=volumes,
        )
        return container.id

    def destroy_agent(self, name: str) -> None:
        container = self._client.containers.get(self._container_name(name))
        container.stop(timeout=10)
        container.remove()

    def send_prompt(self, name: str, prompt: str) -> None:
        container = self._client.containers.get(self._container_name(name))
        escaped = prompt.replace('"', '\\"')
        container.exec_run(
            f'claude -p "{escaped}" --output-format json',
            detach=True,
        )

    def read_output(self, name: str, lines: int = 50) -> str:
        container = self._client.containers.get(self._container_name(name))
        logs = container.logs(tail=lines)
        return logs.decode("utf-8", errors="replace")

    def list_agents(self) -> list[str]:
        containers = self._client.containers.list(all=True)
        prefix = f"{self.prefix}-"
        return [
            c.name[len(prefix):]
            for c in containers
            if c.name.startswith(prefix)
        ]

    def agent_exists(self, name: str) -> bool:
        try:
            self._client.containers.get(self._container_name(name))
            return True
        except docker.errors.NotFound:
            return False
