import pytest
import pytest_asyncio
from memory.memory import MemorySystem
from db.database import Database

@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()

@pytest.fixture
def mem(db):
    return MemorySystem(db)

@pytest.mark.asyncio
async def test_remember_and_recall(mem):
    await mem.remember("jira", "api_url", "https://jira.example.com")
    result = await mem.recall("jira", "api_url")
    assert result is not None
    assert result["value"] == "https://jira.example.com"

@pytest.mark.asyncio
async def test_private_not_visible_to_others(mem):
    await mem.remember("jira", "secret", "value", scope="private")
    result = await mem.recall("code", "secret")
    assert result is None

@pytest.mark.asyncio
async def test_master_sees_all(mem):
    await mem.remember("jira", "secret", "value", scope="private")
    result = await mem.recall("master", "secret")
    assert result is not None

@pytest.mark.asyncio
async def test_shared_memory(mem):
    record_id = await mem.remember("jira", "shared_key", "shared_value", scope="private")
    await mem.share(record_id, ["code", "grok"])
    result = await mem.recall("code", "shared_key")
    assert result is not None

@pytest.mark.asyncio
async def test_forget(mem):
    record_id = await mem.remember("jira", "temp", "data")
    await mem.forget(record_id)
    result = await mem.recall("jira", "temp")
    assert result is None

@pytest.mark.asyncio
async def test_global_visible_to_all(mem):
    await mem.remember("master", "announcement", "hello", scope="global")
    result = await mem.recall("grok", "announcement")
    assert result is not None
