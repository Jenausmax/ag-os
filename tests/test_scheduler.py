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
