import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from core.agent_manager import AgentManager
from core.models import AgentRuntime
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
async def test_create_agent_subscription_no_env(db, mock_tmux):
    providers = {"claude-sub": {"provider": "claude_subscription"}}
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    await mgr.create_agent("jira", "claude-cli", AgentRuntime.HOST, provider_name="claude-sub")
    kwargs = mock_tmux.create_agent.call_args.kwargs
    # Subscription-провайдер не требует credentials env, но AG-OS всё равно
    # экспортирует AG_OS_AGENT_NAME для MCP-брижа (префикс имени в ответах).
    assert kwargs["env"] == {"AG_OS_AGENT_NAME": "jira"}


@pytest.mark.asyncio
async def test_create_agent_anthropic_api(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    providers = {
        "anth": {
            "provider": "anthropic_api",
            "api_key_env": "ANTHROPIC_API_KEY",
            "model_name": "claude-sonnet-4-5",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    await mgr.create_agent("jira", "claude-cli", AgentRuntime.HOST, provider_name="anth")
    env = mock_tmux.create_agent.call_args.kwargs["env"]
    assert env["ANTHROPIC_API_KEY"] == "sk-test"
    assert env["ANTHROPIC_MODEL"] == "claude-sonnet-4-5"
    assert "ANTHROPIC_BASE_URL" not in env


@pytest.mark.asyncio
async def test_create_agent_anthropic_compatible(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zai-xyz")
    providers = {
        "zai": {
            "provider": "anthropic_compatible",
            "base_url": "https://api.z.ai/anthropic",
            "model_name": "glm-4.6",
            "api_key_env": "ZAI_API_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    await mgr.create_agent("coder", "glm", AgentRuntime.HOST, provider_name="zai")
    env = mock_tmux.create_agent.call_args.kwargs["env"]
    assert env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "zai-xyz"
    assert env["ANTHROPIC_MODEL"] == "glm-4.6"


@pytest.mark.asyncio
async def test_create_agent_missing_api_key_env_fails_fast(db, mock_tmux, monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    providers = {
        "broken": {
            "provider": "anthropic_compatible",
            "base_url": "http://x",
            "api_key_env": "MISSING_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    with pytest.raises(ValueError, match="MISSING_KEY"):
        await mgr.create_agent("broken", "x", AgentRuntime.HOST, provider_name="broken")
    mock_tmux.create_agent.assert_not_called()


def test_validate_provider_subscription_warns_without_claude_dir(db, mock_tmux, monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux)
    with caplog.at_level("WARNING"):
        mgr.validate_provider("", AgentRuntime.HOST)
    assert any("claude login" in rec.message.lower() or "claude" in rec.message for rec in caplog.records)


def test_validate_provider_fails_fast_on_missing_env(db, mock_tmux, monkeypatch):
    monkeypatch.delenv("AGOS_TEST_KEY", raising=False)
    providers = {
        "broken": {
            "provider": "anthropic_compatible",
            "base_url": "http://x",
            "api_key_env": "AGOS_TEST_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    with pytest.raises(ValueError, match="AGOS_TEST_KEY"):
        mgr.validate_provider("broken", AgentRuntime.HOST)


def test_validate_provider_ok_with_env(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("AGOS_TEST_KEY", "k")
    providers = {
        "ok": {
            "provider": "anthropic_compatible",
            "base_url": "http://x",
            "api_key_env": "AGOS_TEST_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    mgr.validate_provider("ok", AgentRuntime.HOST)  # no raise


def test_apply_provider_env_reexports_to_existing_window(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("AGOS_TEST_KEY", "secret")
    mock_tmux.apply_env = MagicMock()
    providers = {
        "zai": {
            "provider": "anthropic_compatible",
            "base_url": "https://z.example",
            "model_name": "glm-4.6",
            "api_key_env": "AGOS_TEST_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    mgr.apply_provider_env("master", "zai", AgentRuntime.HOST)
    mock_tmux.apply_env.assert_called_once()
    name, env = mock_tmux.apply_env.call_args.args
    assert name == "master"
    assert env["ANTHROPIC_BASE_URL"] == "https://z.example"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "secret"
    assert env["ANTHROPIC_MODEL"] == "glm-4.6"


def test_apply_provider_env_subscription_noop(db, mock_tmux):
    mock_tmux.apply_env = MagicMock()
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux)
    mgr.apply_provider_env("master", "", AgentRuntime.HOST)
    mock_tmux.apply_env.assert_not_called()


@pytest.mark.asyncio
async def test_create_agent_unknown_provider(db, mock_tmux):
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers={})
    with pytest.raises(ValueError, match="Unknown model provider"):
        await mgr.create_agent("x", "y", AgentRuntime.HOST, provider_name="ghost")


def test_build_llm_credentials_anthropic_api(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("AGOS_TEST_KEY", "sk-x")
    providers = {
        "api": {
            "provider": "anthropic_api",
            "api_key_env": "AGOS_TEST_KEY",
            "model_name": "claude-haiku-4-5",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    creds = mgr.build_llm_credentials("api")
    assert creds["api_key"] == "sk-x"
    assert creds["base_url"] == ""
    assert creds["model_name"] == "claude-haiku-4-5"


def test_build_llm_credentials_anthropic_compatible(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("AGOS_TEST_KEY", "zai-k")
    providers = {
        "zai": {
            "provider": "anthropic_compatible",
            "base_url": "https://z.example",
            "model_name": "glm-4.6",
            "api_key_env": "AGOS_TEST_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    creds = mgr.build_llm_credentials("zai")
    assert creds["api_key"] == "zai-k"
    assert creds["base_url"] == "https://z.example"
    assert creds["model_name"] == "glm-4.6"


def test_build_llm_credentials_subscription_rejected(db, mock_tmux):
    providers = {"sub": {"provider": "claude_subscription"}}
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    with pytest.raises(ValueError, match="CLI-only"):
        mgr.build_llm_credentials("sub")


def test_build_llm_credentials_missing_env_fails(db, mock_tmux, monkeypatch):
    monkeypatch.delenv("AGOS_MISSING", raising=False)
    providers = {
        "broken": {
            "provider": "anthropic_api",
            "api_key_env": "AGOS_MISSING",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    with pytest.raises(ValueError, match="AGOS_MISSING"):
        mgr.build_llm_credentials("broken")


def test_build_llm_credentials_compatible_requires_base_url(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("AGOS_TEST_KEY", "k")
    providers = {
        "bad": {
            "provider": "anthropic_compatible",
            "api_key_env": "AGOS_TEST_KEY",
        }
    }
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    with pytest.raises(ValueError, match="base_url"):
        mgr.build_llm_credentials("bad")


@pytest.mark.asyncio
async def test_ensure_runtime_skips_when_alive(db, mock_tmux):
    mock_tmux.agent_exists.return_value = True
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux)
    await mgr.create_agent("master", "claude-cli", AgentRuntime.HOST)
    mock_tmux.create_agent.reset_mock()
    row = await mgr.get_agent("master")
    resurrected = await mgr.ensure_runtime(row)
    assert resurrected is False
    mock_tmux.create_agent.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_runtime_recreates_missing_window(db, mock_tmux):
    mock_tmux.agent_exists.return_value = False
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux)
    await mgr.create_agent("archivist", "claude-cli", AgentRuntime.HOST)
    mock_tmux.create_agent.reset_mock()
    row = await mgr.get_agent("archivist")
    resurrected = await mgr.ensure_runtime(row)
    assert resurrected is True
    mock_tmux.create_agent.assert_called_once()
    assert mock_tmux.create_agent.call_args.args[0] == "archivist"


@pytest.mark.asyncio
async def test_ensure_runtime_reuses_stored_provider(db, mock_tmux, monkeypatch):
    monkeypatch.setenv("ZAI_KEY", "secret")
    providers = {
        "zai": {
            "provider": "anthropic_compatible",
            "base_url": "https://z.example",
            "model_name": "glm-4.6",
            "api_key_env": "ZAI_KEY",
        }
    }
    mock_tmux.agent_exists.return_value = False
    mgr = AgentManager(db=db, tmux_runtime=mock_tmux, model_providers=providers)
    await mgr.create_agent(
        "coder", "glm", AgentRuntime.HOST, provider_name="zai",
    )
    mock_tmux.create_agent.reset_mock()
    row = await mgr.get_agent("coder")
    await mgr.ensure_runtime(row)
    env = mock_tmux.create_agent.call_args.kwargs["env"]
    assert env["ANTHROPIC_BASE_URL"] == "https://z.example"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "secret"


@pytest.mark.asyncio
async def test_list_agents(manager):
    await manager.create_agent("jira", "claude-cli", AgentRuntime.HOST)
    await manager.create_agent("code", "claude-cli", AgentRuntime.HOST)
    agents = await manager.list_agents()
    assert len(agents) == 2
    names = [a["name"] for a in agents]
    assert "jira" in names
    assert "code" in names
