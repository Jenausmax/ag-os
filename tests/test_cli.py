import argparse
import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch

from cli import commands as cli
from db.database import Database


def _args(**kwargs) -> argparse.Namespace:
    defaults = {"config": "", "json": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest_asyncio.fixture
async def test_db(tmp_path):
    db_path = tmp_path / "cli.db"
    db = Database(str(db_path))
    await db.init()
    yield db, str(db_path)
    await db.close()


@pytest_asyncio.fixture
async def patched_init(test_db, monkeypatch):
    db, db_path = test_db
    config = MagicMock()
    config.database.path = db_path
    config.agents.session_name = "ag-os-test"
    config.docker.defaults = MagicMock(
        cpus=2, memory="4g", network="ag-os-net",
        workspace_base="/tmp/ws", shared_dir="/tmp/shared",
    )
    config.model_providers = {}

    mock_tmux = MagicMock()
    mock_tmux.create_agent.return_value = "win"
    mock_tmux.agent_exists.return_value = False
    mock_tmux.apply_env = MagicMock()

    async def fake_init(config_path, need_tmux=False, need_docker=False):
        from core.agent_manager import AgentManager
        manager = AgentManager(
            db=db,
            tmux_runtime=mock_tmux if need_tmux else None,
            docker_runtime=None,
            model_providers={},
        )
        return db, manager, config

    monkeypatch.setattr(cli, "init_core", fake_init)
    monkeypatch.setattr(db, "close", lambda: _noop())
    return db, mock_tmux


async def _noop():
    return None


# ─── agent ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_list_empty(patched_init, capsys):
    rc = await cli.agent_list(_args())
    assert rc == 0
    assert "(no agents)" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_agent_create_and_list(patched_init, capsys):
    rc = await cli.agent_create(_args(
        name="jira", runtime="host", model="claude-cli",
        provider="", type="dynamic",
    ))
    assert rc == 0
    rc = await cli.agent_list(_args(json=True))
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert any(a["name"] == "jira" for a in data)


@pytest.mark.asyncio
async def test_agent_destroy(patched_init, capsys):
    await cli.agent_create(_args(
        name="tmp", runtime="host", model="m", provider="", type="dynamic",
    ))
    rc = await cli.agent_destroy(_args(name="tmp"))
    assert rc == 0


@pytest.mark.asyncio
async def test_agent_destroy_not_found(patched_init, capsys):
    rc = await cli.agent_destroy(_args(name="ghost"))
    assert rc != 0


@pytest.mark.asyncio
async def test_agent_create_unknown_provider(patched_init, capsys):
    rc = await cli.agent_create(_args(
        name="x", runtime="host", model="m",
        provider="nonexistent", type="dynamic",
    ))
    assert rc != 0


# ─── schedule ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_invalid_cron(patched_init, capsys):
    rc = await cli.schedule_add(_args(
        cron="bogus", agent="master", prompt="hi",
    ))
    assert rc != 0


@pytest.mark.asyncio
async def test_schedule_add_unknown_agent(patched_init):
    rc = await cli.schedule_add(_args(
        cron="0 * * * *", agent="ghost", prompt="hi",
    ))
    assert rc != 0


@pytest.mark.asyncio
async def test_schedule_add_list_rm_flow(patched_init, capsys):
    await cli.agent_create(_args(
        name="master", runtime="host", model="m", provider="", type="permanent",
    ))
    rc = await cli.schedule_add(_args(
        cron="0 * * * *", agent="master", prompt="check mail",
    ))
    assert rc == 0
    capsys.readouterr()
    rc = await cli.schedule_list(_args(json=True))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    tasks = json.loads(out)
    assert len(tasks) == 1
    task_id = tasks[0]["id"]
    rc = await cli.schedule_rm(_args(id=task_id))
    assert rc == 0
    rc = await cli.schedule_rm(_args(id=task_id))
    assert rc != 0


# ─── memory ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_remember_and_get(patched_init, capsys):
    rc = await cli.memory_remember(_args(
        agent="master", key="project", value="AG-OS",
        scope="private", ttl=None,
    ))
    assert rc == 0
    capsys.readouterr()
    rc = await cli.memory_get(_args(agent="master", key="project", json=True))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    row = json.loads(out)
    assert row["value"] == "AG-OS"


@pytest.mark.asyncio
async def test_memory_get_no_key_lists_context(patched_init, capsys):
    await cli.memory_remember(_args(
        agent="jira", key="k1", value="v1", scope="private", ttl=None,
    ))
    await cli.memory_remember(_args(
        agent="master", key="rule", value="no force push",
        scope="global", ttl=None,
    ))
    capsys.readouterr()
    rc = await cli.memory_get(_args(agent="jira", key="", json=True))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    rows = json.loads(out)
    keys = [r["key"] for r in rows]
    assert "k1" in keys
    assert "rule" in keys  # global visible to everyone


@pytest.mark.asyncio
async def test_memory_forget(patched_init, capsys):
    await cli.memory_remember(_args(
        agent="x", key="k", value="v", scope="private", ttl=None,
    ))
    capsys.readouterr()
    rc = await cli.memory_get(_args(agent="x", key="", json=True))
    out = capsys.readouterr().out.strip().splitlines()[-1]
    rows = json.loads(out)
    rec_id = rows[0]["id"]
    rc = await cli.memory_forget(_args(id=rec_id))
    assert rc == 0


# ─── dispatch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_unknown_mode(capsys):
    rc = await cli.dispatch(argparse.Namespace(mode="bogus", cmd="x"))
    assert rc != 0


def test_register_cli_parsers_smoke():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode")
    cli.register_cli_parsers(sub)
    ns = parser.parse_args(["agent", "list"])
    assert ns.mode == "agent"
    assert ns.cmd == "list"

    ns = parser.parse_args([
        "schedule", "add", "--cron", "0 * * * *",
        "--agent", "master", "--prompt", "check",
    ])
    assert ns.cron == "0 * * * *"
    assert ns.agent == "master"
