import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from scheduler.scheduler import AgScheduler
from db.database import Database

@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()

@pytest.fixture
def scheduler(db):
    manager = AsyncMock()
    return AgScheduler(db=db, agent_manager=manager)


@pytest_asyncio.fixture
async def running_scheduler(db):
    manager = AsyncMock()
    sched = AgScheduler(db=db, agent_manager=manager)
    sched._scheduler.start()
    yield sched
    try:
        sched.stop()
    except Exception:
        pass

@pytest.mark.asyncio
async def test_add_task(scheduler):
    task_id = await scheduler.add_task("0 9 * * 1-5", "jira", "отчёт за вчера")
    assert task_id > 0
    tasks = await scheduler.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["agent_name"] == "jira"

@pytest.mark.asyncio
async def test_remove_task(scheduler):
    task_id = await scheduler.add_task("0 9 * * *", "jira", "test")
    await scheduler.remove_task(task_id)
    tasks = await scheduler.list_tasks()
    assert len(tasks) == 0

@pytest.mark.asyncio
async def test_toggle_task(scheduler):
    task_id = await scheduler.add_task("0 9 * * *", "jira", "test")
    await scheduler.toggle_task(task_id, enabled=False)
    tasks = await scheduler.list_tasks()
    assert tasks[0]["enabled"] == 0


@pytest.mark.asyncio
async def test_reload_adds_new_tasks(running_scheduler):
    scheduler = running_scheduler
    await scheduler.db.execute(
        "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
        ("0 * * * *", "master", "check"),
    )
    assert scheduler._jobs == {}
    report = await scheduler.reload_from_db()
    assert len(report.added) == 1
    assert len(scheduler._jobs) == 1
    assert report.removed == []
    assert report.updated == []


@pytest.mark.asyncio
async def test_reload_removes_deleted_tasks(running_scheduler):
    scheduler = running_scheduler
    task_id = await scheduler.add_task("0 * * * *", "master", "check")
    assert task_id in scheduler._jobs
    await scheduler.db.execute("DELETE FROM schedule WHERE id = ?", (task_id,))
    report = await scheduler.reload_from_db()
    assert report.removed == [task_id]
    assert task_id not in scheduler._jobs


@pytest.mark.asyncio
async def test_reload_detects_updated_task(running_scheduler):
    scheduler = running_scheduler
    task_id = await scheduler.add_task("0 * * * *", "master", "old prompt")
    await scheduler.db.execute(
        "UPDATE schedule SET prompt = ? WHERE id = ?",
        ("new prompt", task_id),
    )
    report = await scheduler.reload_from_db()
    assert report.updated == [task_id]
    assert scheduler._live_tasks[task_id]["prompt"] == "new prompt"


@pytest.mark.asyncio
async def test_reload_is_idempotent(running_scheduler):
    scheduler = running_scheduler
    await scheduler.add_task("0 * * * *", "master", "check")
    report1 = await scheduler.reload_from_db()
    report2 = await scheduler.reload_from_db()
    assert not report1.changed
    assert not report2.changed


@pytest.mark.asyncio
async def test_reload_skips_disabled_tasks(running_scheduler):
    scheduler = running_scheduler
    task_id = await scheduler.add_task("0 * * * *", "master", "check")
    await scheduler.toggle_task(task_id, enabled=False)
    report = await scheduler.reload_from_db()
    assert report.removed == [task_id]
    assert task_id not in scheduler._jobs


@pytest.mark.asyncio
async def test_remove_task_cleans_live_tasks(running_scheduler):
    scheduler = running_scheduler
    task_id = await scheduler.add_task("0 * * * *", "master", "check")
    assert task_id in scheduler._live_tasks
    await scheduler.remove_task(task_id)
    assert task_id not in scheduler._live_tasks
    assert task_id not in scheduler._jobs


# --- clear_before tests ---

@pytest.mark.asyncio
async def test_execute_task_calls_clear_before_send_prompt(scheduler):
    """clear_before=1: clear_context должен вызываться ровно один раз и ДО send_prompt."""
    call_order = []
    scheduler.manager.clear_context = AsyncMock(side_effect=lambda name: call_order.append("clear"))
    scheduler.manager.send_prompt = AsyncMock(side_effect=lambda name, prompt: call_order.append("send"))
    scheduler.manager.get_agent = AsyncMock(return_value={"name": "master"})

    task = {"id": 99, "agent_name": "master", "prompt": "hello", "clear_before": 1}
    await scheduler._execute_task(task)

    scheduler.manager.clear_context.assert_called_once_with("master")
    scheduler.manager.send_prompt.assert_called_once_with("master", "hello")
    assert call_order == ["clear", "send"], f"Expected clear before send, got: {call_order}"


@pytest.mark.asyncio
async def test_execute_task_skips_clear_when_flag_false(scheduler):
    """clear_before=0: clear_context не должен вызываться, send_prompt должен вызваться."""
    scheduler.manager.clear_context = AsyncMock()
    scheduler.manager.send_prompt = AsyncMock()
    scheduler.manager.get_agent = AsyncMock(return_value={"name": "master"})

    task = {"id": 100, "agent_name": "master", "prompt": "hello", "clear_before": 0}
    await scheduler._execute_task(task)

    scheduler.manager.clear_context.assert_not_called()
    scheduler.manager.send_prompt.assert_called_once_with("master", "hello")


@pytest.mark.asyncio
async def test_execute_task_skips_tick_when_clear_fails(scheduler):
    """Если clear_context бросает исключение — send_prompt НЕ вызывается, результат 'error'."""
    scheduler.manager.clear_context = AsyncMock(side_effect=RuntimeError("tmux gone"))
    scheduler.manager.send_prompt = AsyncMock()
    scheduler.manager.get_agent = AsyncMock(return_value={"name": "master"})

    task_id = await scheduler.add_task("0 9 * * *", "master", "hello", clear_before=True)
    tasks = await scheduler.list_tasks()
    task = next(t for t in tasks if t["id"] == task_id)

    await scheduler._execute_task(task)

    scheduler.manager.send_prompt.assert_not_called()

    tasks = await scheduler.list_tasks()
    assert tasks[0]["last_result"] == "error"


@pytest.mark.asyncio
async def test_add_task_persists_clear_before(scheduler):
    """add_task сохраняет clear_before в БД корректно."""
    # По умолчанию (True) → 1
    task_id1 = await scheduler.add_task("0 9 * * *", "master", "prompt1")
    tasks = await scheduler.list_tasks()
    assert tasks[0]["clear_before"] == 1

    # Явно False → 0
    task_id2 = await scheduler.add_task("0 10 * * *", "master", "prompt2", clear_before=False)
    tasks = await scheduler.list_tasks()
    row2 = next(t for t in tasks if t["id"] == task_id2)
    assert row2["clear_before"] == 0
