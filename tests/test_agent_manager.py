import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from core.agent_manager import AgentManager
from core.models import AgentRuntime, AgentStatus
from db.database import Database
from memory.memory import MemorySystem


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
async def test_send_prompt_injects_memory_context(db, mock_tmux):
    memory = MemorySystem(db)
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, memory=memory)
    await mgr.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await memory.remember("jira", "project", "AGOS", scope="private")
    await memory.remember("master", "rule", "no force push", scope="global")
    await mgr.send_prompt("jira", "do the thing")
    sent = mock_tmux.send_prompt.call_args[0][1]
    assert "[Memory] project: AGOS" in sent
    assert "[Memory] rule: no force push" in sent
    assert sent.endswith("do the thing")
    agent = await mgr.get_agent("jira")
    assert agent["current_task"] == "do the thing"


@pytest.mark.asyncio
async def test_send_prompt_empty_memory_no_preamble(db, mock_tmux):
    memory = MemorySystem(db)
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, memory=memory)
    await mgr.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await mgr.send_prompt("jira", "hello")
    mock_tmux.send_prompt.assert_called_once_with("jira", "hello")


@pytest.mark.asyncio
async def test_send_prompt_no_memory_backward_compat(manager, mock_tmux):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.send_prompt("jira", "hello")
    mock_tmux.send_prompt.assert_called_once_with("jira", "hello")


@pytest.mark.asyncio
async def test_list_agents(manager):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.create_agent("code", "claude-cli", AgentRuntime.HOST)
    agents = await manager.list_agents()
    assert len(agents) == 2
    names = [a["name"] for a in agents]
    assert "jira" in names
    assert "code" in names
