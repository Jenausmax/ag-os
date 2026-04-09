---
id: AGOS-0006
title: Agent Manager
phase: 1 — MVP
status: pending
depends_on: [AGOS-0002, AGOS-0003, AGOS-0005]
files_create: [core/agent_manager.py, tests/test_agent_manager.py]
files_modify: []
---

## Описание

Центральный компонент системы. Управляет жизненным циклом агентов: CRUD операции через SQLite, делегирование runtime-операций нужному runtime (tmux или docker). Обновляет статусы агентов в БД при отправке промтов. Проверяет уникальность имён и существование агентов.

## Acceptance Criteria

- [ ] create_agent создаёт агента в БД и runtime, возвращает dict
- [ ] Дубликат имени → ValueError "already exists"
- [ ] destroy_agent удаляет из БД и runtime
- [ ] send_prompt обновляет статус на working и current_task
- [ ] read_output делегирует runtime
- [ ] list_agents возвращает всех агентов из БД
- [ ] get_agent возвращает dict или None
- [ ] Тесты с моками проходят (6 тестов)

## Затрагиваемые модули

- core/agent_manager.py: AgentManager
- tests/test_agent_manager.py: юнит-тесты с моками runtime

## Ключевые интерфейсы

```python
class AgentManager:
    def __init__(self, db: Database, tmux_runtime: BaseRuntime | None = None, docker_runtime: BaseRuntime | None = None)
    async def create_agent(self, name: str, model: str, runtime: AgentRuntime, agent_type: str = "dynamic", config: dict | None = None) -> dict
    async def destroy_agent(self, name: str) -> None
    async def send_prompt(self, name: str, prompt: str) -> None
    async def read_output(self, name: str, lines: int = 50) -> str
    async def get_agent(self, name: str) -> dict | None
    async def list_agents(self) -> list[dict]
    async def update_status(self, name: str, status: AgentStatus) -> None
```

## Edge Cases

- Создание дубликата агента
- Отправка промта несуществующему агенту
- Docker runtime не сконфигурирован → RuntimeError
- tmux runtime не сконфигурирован → RuntimeError

## План реализации

### Step 1: Написать тест

```python
# tests/test_agent_manager.py
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from core.agent_manager import AgentManager
from core.models import AgentRuntime, AgentStatus
from db.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def mock_tmux():
    runtime = MagicMock()
    runtime.create_agent.return_value = "test-window"
    runtime.read_output.return_value = "output text"
    runtime.list_agents.return_value = []
    runtime.agent_exists.return_value = False
    return runtime


@pytest.fixture
def manager(db, mock_tmux):
    return AgentManager(db=db, tmux_runtime=mock_tmux, docker_runtime=None)


@pytest.mark.asyncio
async def test_create_agent(manager, mock_tmux):
    agent = await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    assert agent["name"] == "jira"
    assert agent["status"] == "idle"
    mock_tmux.create_agent.assert_called_once()


@pytest.mark.asyncio
async def test_create_duplicate_agent(manager):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    with pytest.raises(ValueError, match="already exists"):
        await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)


@pytest.mark.asyncio
async def test_destroy_agent(manager, mock_tmux):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.destroy_agent("jira")
    mock_tmux.destroy_agent.assert_called_once_with("jira")
    agents = await manager.list_agents()
    assert len(agents) == 0


@pytest.mark.asyncio
async def test_send_prompt(manager, mock_tmux):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.send_prompt("jira", "hello")
    mock_tmux.send_prompt.assert_called_once_with("jira", "hello")
    agent = await manager.get_agent("jira")
    assert agent["status"] == "working"
    assert agent["current_task"] == "hello"


@pytest.mark.asyncio
async def test_read_output(manager, mock_tmux):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    output = await manager.read_output("jira")
    assert output == "output text"


@pytest.mark.asyncio
async def test_list_agents(manager):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.create_agent("code", "claude-cli", AgentRuntime.HOST)
    agents = await manager.list_agents()
    assert len(agents) == 2
    names = [a["name"] for a in agents]
    assert "jira" in names
    assert "code" in names
```

### Step 2: Запустить тест — FAIL

```bash
pytest tests/test_agent_manager.py -v
```

### Step 3: Реализовать agent_manager.py

```python
# core/agent_manager.py
from core.models import AgentRuntime, AgentStatus
from db.database import Database
from runtime.base import BaseRuntime


class AgentManager:
    def __init__(
        self,
        db: Database,
        tmux_runtime: BaseRuntime | None = None,
        docker_runtime: BaseRuntime | None = None,
    ):
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

    async def create_agent(
        self,
        name: str,
        model: str,
        runtime: AgentRuntime,
        agent_type: str = "dynamic",
        config: dict | None = None,
    ) -> dict:
        existing = await self.db.fetch_one(
            "SELECT id FROM agents WHERE name = ?", (name,)
        )
        if existing:
            raise ValueError(f"Agent '{name}' already exists")

        rt = self._get_runtime(runtime)
        rt.create_agent(name)

        import json
        await self.db.execute(
            """INSERT INTO agents (name, model, runtime, type, status, tmux_window, config)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                model,
                runtime.value,
                agent_type,
                AgentStatus.IDLE.value,
                name if runtime == AgentRuntime.HOST else "",
                json.dumps(config or {}),
            ),
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
        await self.db.execute(
            "UPDATE agents SET status = ?, current_task = ? WHERE name = ?",
            (AgentStatus.WORKING.value, prompt, name),
        )

    async def read_output(self, name: str, lines: int = 50) -> str:
        agent = await self.get_agent(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        rt = self._get_runtime(AgentRuntime(agent["runtime"]))
        return rt.read_output(name, lines)

    async def get_agent(self, name: str) -> dict | None:
        return await self.db.fetch_one(
            "SELECT * FROM agents WHERE name = ?", (name,)
        )

    async def list_agents(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM agents ORDER BY name")

    async def update_status(self, name: str, status: AgentStatus) -> None:
        await self.db.execute(
            "UPDATE agents SET status = ? WHERE name = ?", (status.value, name)
        )
```

### Step 4: Запустить тест — PASS

```bash
pytest tests/test_agent_manager.py -v
```

Expected: 6 passed

### Step 5: Commit

```bash
git add core/agent_manager.py tests/test_agent_manager.py
git commit -m "feat: add AgentManager with CRUD and runtime delegation"
```
