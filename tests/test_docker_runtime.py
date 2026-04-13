import pytest
from unittest.mock import MagicMock, patch

import docker

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
    kwargs = mock_docker.containers.run.call_args.kwargs
    assert kwargs["name"] == "ag-os-test"
    assert kwargs["detach"] is True
    assert kwargs["mem_limit"] == "4g"
    assert kwargs["nano_cpus"] == int(2 * 1e9)


def test_destroy_agent(mock_docker):
    container = MagicMock()
    mock_docker.containers.get.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    runtime.destroy_agent("test")

    mock_docker.containers.get.assert_called_once_with("ag-os-test")
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
    output = runtime.read_output("test", lines=50)

    assert "line1" in output
    assert "line3" in output
    container.logs.assert_called_once_with(tail=50)


def test_agent_exists_true(mock_docker):
    mock_docker.containers.get.return_value = MagicMock()
    runtime = DockerRuntime(prefix="ag-os")
    assert runtime.agent_exists("test") is True


def test_agent_exists_false(mock_docker):
    mock_docker.containers.get.side_effect = docker.errors.NotFound("missing")
    runtime = DockerRuntime(prefix="ag-os")
    assert runtime.agent_exists("test") is False


def test_create_agent_passes_env(mock_docker):
    container = MagicMock()
    container.id = "abc123"
    mock_docker.containers.run.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    runtime.create_agent(
        "test",
        env={"ANTHROPIC_BASE_URL": "http://litellm:4000", "ANTHROPIC_AUTH_TOKEN": "k"},
    )

    kwargs = mock_docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ANTHROPIC_BASE_URL"] == "http://litellm:4000"
    assert kwargs["environment"]["ANTHROPIC_AUTH_TOKEN"] == "k"


def test_create_agent_empty_env_default(mock_docker):
    container = MagicMock()
    container.id = "abc123"
    mock_docker.containers.run.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    runtime.create_agent("test")

    kwargs = mock_docker.containers.run.call_args.kwargs
    assert kwargs["environment"] == {}


def test_send_prompt_escapes_quotes(mock_docker):
    container = MagicMock()
    mock_docker.containers.get.return_value = container

    runtime = DockerRuntime(prefix="ag-os")
    runtime.send_prompt("test", 'hello "world"')

    container.exec_run.assert_called_once()
    cmd = container.exec_run.call_args.args[0]
    assert '\\"world\\"' in cmd
