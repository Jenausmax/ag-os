import pytest
from unittest.mock import MagicMock, patch
from runtime.tmux_runtime import TmuxRuntime


@pytest.fixture
def mock_server():
    with patch("runtime.tmux_runtime.libtmux.Server") as mock:
        server = MagicMock()
        session = MagicMock()
        server.sessions.filter.return_value = []
        server.new_session.return_value = session
        mock.return_value = server
        yield server, session


def test_init_creates_session(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = []
    TmuxRuntime("ag-os")
    server.new_session.assert_called_once_with(session_name="ag-os", attach=False)


def test_create_agent(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    session.new_window.return_value = window
    runtime = TmuxRuntime("ag-os")
    result = runtime.create_agent("jira", 'claude -p "test"')
    session.new_window.assert_called_once_with(window_name="jira", attach=False)
    assert result == window.name


def test_create_agent_auto_starts_claude_by_default(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.new_window.return_value = window
    runtime = TmuxRuntime("ag-os")
    runtime.create_agent("researcher")
    calls = [c.args[0] for c in pane.send_keys.call_args_list]
    assert "claude" in calls


def test_create_agent_custom_command_overrides_default(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.new_window.return_value = window
    runtime = TmuxRuntime("ag-os")
    runtime.create_agent("x", command="claude --model sonnet")
    calls = [c.args[0] for c in pane.send_keys.call_args_list]
    assert "claude --model sonnet" in calls
    assert "claude" not in calls  # дефолт не вызван


def test_destroy_agent(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.destroy_agent("jira")
    window.kill.assert_called_once()


def test_send_prompt(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.send_prompt("jira", "hello")
    pane.send_keys.assert_called_once_with("hello")


def test_read_output(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    pane.capture_pane.return_value = ["line1", "line2"]
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    output = runtime.read_output("jira")
    assert output == "line1\nline2"


def test_create_agent_exports_env_before_command(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.new_window.return_value = window
    runtime = TmuxRuntime("ag-os")
    runtime.create_agent("master", "claude", env={"ANTHROPIC_API_KEY": "sk-x"})
    calls = [c.args[0] for c in pane.send_keys.call_args_list]
    assert "export ANTHROPIC_API_KEY=sk-x" in calls
    assert calls.index("export ANTHROPIC_API_KEY=sk-x") < calls.index("claude")


def test_apply_env_to_existing_window(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.apply_env("master", {"ANTHROPIC_BASE_URL": "http://x", "ANTHROPIC_AUTH_TOKEN": "k"})
    calls = [c.args[0] for c in pane.send_keys.call_args_list]
    assert "export ANTHROPIC_BASE_URL=http://x" in calls
    assert "export ANTHROPIC_AUTH_TOKEN=k" in calls


def test_apply_env_missing_window_raises(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    session.windows.filter.return_value = []
    runtime = TmuxRuntime("ag-os")
    with pytest.raises(ValueError, match="not found"):
        runtime.apply_env("ghost", {"K": "v"})


def test_list_agents(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    w1 = MagicMock()
    w1.name = "master"
    w2 = MagicMock()
    w2.name = "jira"
    session.windows = [w1, w2]
    runtime = TmuxRuntime("ag-os")
    assert runtime.list_agents() == ["master", "jira"]


def test_clear_context_sends_clear(mock_server, monkeypatch):
    monkeypatch.setattr("runtime.tmux_runtime.time.sleep", lambda _: None)
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    window = MagicMock()
    pane = MagicMock()
    window.active_pane = pane
    session.windows.filter.return_value = [window]
    runtime = TmuxRuntime("ag-os")
    runtime.clear_context("jira")
    pane.send_keys.assert_called_once_with("/clear")


def test_clear_context_missing_agent_raises(mock_server):
    server, session = mock_server
    server.sessions.filter.return_value = [session]
    session.windows.filter.return_value = []
    runtime = TmuxRuntime("ag-os")
    with pytest.raises(ValueError, match="not found"):
        runtime.clear_context("ghost")
