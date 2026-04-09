---
id: AGOS-0018
title: Docker Runtime
phase: 6 — Docker
status: pending
depends_on: [AGOS-0005]
files_create: [runtime/docker_runtime.py, tests/test_docker_runtime.py, Dockerfile]
files_modify: []
---

## Описание

Реализация BaseRuntime для Docker-контейнеров через docker-py. Контейнеры с префиксом `ag-os-`, ограничения ресурсов (CPU, RAM), изолированные volumes (workspace rw + shared ro). Отправка промтов через exec_run, чтение логов. Базовый Dockerfile с Ubuntu 22.04, Claude Code CLI, Python, anthropic SDK.

## Acceptance Criteria

- [ ] create_agent запускает контейнер с ограничениями ресурсов
- [ ] destroy_agent останавливает и удаляет контейнер
- [ ] list_agents фильтрует по префиксу ag-os-
- [ ] read_output возвращает декодированные логи
- [ ] agent_exists проверяет через docker API
- [ ] send_prompt экранирует кавычки в промте
- [ ] Dockerfile собирается
- [ ] Тесты с моками проходят (4 теста)

## Затрагиваемые модули

- runtime/docker_runtime.py: DockerRuntime
- tests/test_docker_runtime.py: юнит-тесты с моками docker-py
- Dockerfile: базовый образ агента

## Ключевые интерфейсы

```python
class DockerRuntime(BaseRuntime):
    def __init__(self, prefix="ag-os", image="ag-os-full:latest", cpus=2, memory="4g", network="bridge", workspace_base="/data/ag-os/workspaces", shared_dir="/data/ag-os/shared")
    def create_agent(self, name, command="") -> str  # returns container.id
    def destroy_agent(self, name) -> None
    def send_prompt(self, name, prompt) -> None
    def read_output(self, name, lines=50) -> str
    def list_agents(self) -> list[str]
    def agent_exists(self, name) -> bool
```

## Edge Cases

- Контейнер не найден → docker.errors.NotFound
- Длинный промт с кавычками — экранирование
- Контейнер без префикса — не попадает в list_agents

## План реализации

### Step 1: Написать тест (с моком docker-py)

```python
# tests/test_docker_runtime.py
import pytest
from unittest.mock import MagicMock, patch
from runtime.docker_runtime import DockerRuntime


@pytest.fixture
def mock_docker():
    with patch("runtime.docker_runtime.docker.from_env") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


def test_create_agent(mock_docker):
    container = MagicMock()
    container.id = "abc123"
    container.name = "ag-os-test"
    mock_docker.containers.run.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    result = runtime.create_agent("test", "claude -p 'hello'")
    assert result == "abc123"
    mock_docker.containers.run.assert_called_once()


def test_destroy_agent(mock_docker):
    container = MagicMock()
    mock_docker.containers.get.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    runtime.destroy_agent("test")
    container.stop.assert_called_once()
    container.remove.assert_called_once()


def test_list_agents(mock_docker):
    c1 = MagicMock()
    c1.name = "ag-os-jira"
    c2 = MagicMock()
    c2.name = "ag-os-code"
    c3 = MagicMock()
    c3.name = "other-container"
    mock_docker.containers.list.return_value = [c1, c2, c3]

    runtime = DockerRuntime(prefix="ag-os")
    agents = runtime.list_agents()
    assert agents == ["jira", "code"]


def test_read_output(mock_docker):
    container = MagicMock()
    container.logs.return_value = b"line1\nline2\nline3"
    mock_docker.containers.get.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    output = runtime.read_output("test")
    assert "line1" in output
```

### Step 2: Реализовать docker_runtime.py

```python
# runtime/docker_runtime.py
import docker
from runtime.base import BaseRuntime


class DockerRuntime(BaseRuntime):
    def __init__(
        self,
        prefix: str = "ag-os",
        image: str = "ag-os-full:latest",
        cpus: int = 2,
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
```

### Step 3: Создать Dockerfile

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3 \
    python3-pip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

RUN pip3 install anthropic httpx

WORKDIR /workspace

ENTRYPOINT ["bash"]
```

### Step 4: Запустить тесты — PASS

```bash
pytest tests/test_docker_runtime.py -v
```

### Step 5: Commit

```bash
git add runtime/docker_runtime.py tests/test_docker_runtime.py Dockerfile
git commit -m "feat: add Docker runtime with resource limits and isolation"
```
