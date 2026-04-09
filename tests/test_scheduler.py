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
