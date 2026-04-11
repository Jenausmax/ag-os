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
