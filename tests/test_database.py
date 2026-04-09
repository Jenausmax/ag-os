import pytest
import pytest_asyncio
from db.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_init_creates_tables(db):
    tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t["name"] for t in tables]
    assert "agents" in table_names
    assert "memory" in table_names
    assert "schedule" in table_names
    assert "guard_logs" in table_names


@pytest.mark.asyncio
async def test_execute_and_fetch(db):
    await db.execute("INSERT INTO agents (name, model, runtime, type, status) VALUES (?, ?, ?, ?, ?)", ("test", "claude-cli", "host", "permanent", "idle"))
    rows = await db.fetch_all("SELECT * FROM agents WHERE name = ?", ("test",))
    assert len(rows) == 1
    assert rows[0]["name"] == "test"
