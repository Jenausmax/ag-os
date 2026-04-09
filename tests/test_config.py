import pytest
from core.config import load_config, AppConfig


def test_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
telegram:
  token: "123:ABC"
  allowed_users: [111, 222]
agents:
  session_name: "ag-os"
  master:
    name: "master"
    model: "claude-cli"
    runtime: "host"
    type: "permanent"
  permanent: []
database:
  path: "test.db"
""")
    config = load_config(str(config_file))
    assert config.telegram.token == "123:ABC"
    assert config.telegram.allowed_users == [111, 222]
    assert config.agents.session_name == "ag-os"
    assert config.agents.master.name == "master"


def test_load_config_missing_token(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
telegram:
  token: ""
  allowed_users: []
agents:
  session_name: "ag-os"
  master:
    name: "master"
    model: "claude-cli"
    runtime: "host"
    type: "permanent"
  permanent: []
database:
  path: "test.db"
""")
    config = load_config(str(config_file))
    assert config.telegram.token == ""
