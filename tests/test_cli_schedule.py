"""Тесты для schedule_add --no-clear и schedule_list с колонкой clear_before."""
import argparse
import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock

from cli import commands as cli
from db.database import Database


def _args(**kwargs) -> argparse.Namespace:
    defaults = {"config": "", "json": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest_asyncio.fixture
async def test_db(tmp_path):
    db_path = tmp_path / "sched_cli.db"
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

    async def _noop():
        return None

    monkeypatch.setattr(cli, "init_core", fake_init)
    monkeypatch.setattr(db, "close", lambda: _noop())
    monkeypatch.setattr(cli, "_notify_bot", lambda: None)
    return db, mock_tmux


async def _create_master(patched_init):
    """Вспомогательная: создаёт агента master."""
    await cli.agent_create(_args(
        name="master", runtime="host", model="m",
        provider="", type="permanent",
    ))


# ─── Тест 1: default — clear_before = 1 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_default_clear_before_true(patched_init):
    """Без --no-clear INSERT кладёт clear_before=1."""
    db, _ = patched_init
    await _create_master((db, _))

    rc = await cli.schedule_add(_args(
        cron="0 * * * *",
        agent="master",
        prompt="daily check",
        no_clear=False,
    ))
    assert rc == 0

    row = await db.fetch_one("SELECT clear_before FROM schedule ORDER BY id DESC LIMIT 1")
    assert row is not None
    assert row["clear_before"] == 1


# ─── Тест 2: --no-clear — clear_before = 0 ────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_no_clear_flag_persists_zero(patched_init):
    """С --no-clear (args.no_clear=True) INSERT кладёт clear_before=0."""
    db, _ = patched_init
    await _create_master((db, _))

    rc = await cli.schedule_add(_args(
        cron="0 * * * *",
        agent="master",
        prompt="persistent task",
        no_clear=True,
    ))
    assert rc == 0

    row = await db.fetch_one("SELECT clear_before FROM schedule ORDER BY id DESC LIMIT 1")
    assert row is not None
    assert row["clear_before"] == 0


# ─── Тест 3: JSON-output содержит clear_before ────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_json_includes_clear_before(patched_init, capsys):
    """JSON-вывод schedule_add содержит поле clear_before."""
    db, _ = patched_init
    await _create_master((db, _))

    rc = await cli.schedule_add(_args(
        cron="0 * * * *",
        agent="master",
        prompt="json task",
        no_clear=False,
        json=True,
    ))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(out)
    assert "clear_before" in data
    assert data["clear_before"] is True


# ─── Тест 4: schedule_list показывает колонку C / - ──────────────────────────

@pytest.mark.asyncio
async def test_schedule_list_shows_clear_flag(patched_init, capsys):
    """schedule_list в text-режиме показывает [C] и [-] в соответствии с clear_before."""
    db, _ = patched_init
    await _create_master((db, _))

    await cli.schedule_add(_args(
        cron="0 * * * *", agent="master", prompt="t1", no_clear=False,
    ))
    await cli.schedule_add(_args(
        cron="0 * * * *", agent="master", prompt="t2", no_clear=True,
    ))
    capsys.readouterr()

    rc = await cli.schedule_list(_args())
    assert rc == 0
    out = capsys.readouterr().out
    assert "[C]" in out
    assert "[-]" in out


# ─── Тест 5: schedule_list JSON содержит clear_before ─────────────────────────

@pytest.mark.asyncio
async def test_schedule_list_json_includes_clear_before(patched_init, capsys):
    """schedule_list --json включает clear_before в каждом элементе."""
    db, _ = patched_init
    await _create_master((db, _))

    await cli.schedule_add(_args(
        cron="0 * * * *", agent="master", prompt="check", no_clear=False,
    ))
    capsys.readouterr()

    rc = await cli.schedule_list(_args(json=True))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    tasks = json.loads(out)
    assert len(tasks) == 1
    assert "clear_before" in tasks[0]
    assert tasks[0]["clear_before"] is True


# ─── Тест 6: argparse --no-clear флаг регистрируется ─────────────────────────

def test_argparse_no_clear_flag_registered():
    """register_cli_parsers регистрирует --no-clear для schedule add."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode")
    cli.register_cli_parsers(sub)

    ns = parser.parse_args([
        "schedule", "add",
        "--cron", "0 * * * *",
        "--agent", "master",
        "--prompt", "test",
        "--no-clear",
    ])
    assert ns.no_clear is True

    ns2 = parser.parse_args([
        "schedule", "add",
        "--cron", "0 * * * *",
        "--agent", "master",
        "--prompt", "test",
    ])
    assert ns2.no_clear is False
