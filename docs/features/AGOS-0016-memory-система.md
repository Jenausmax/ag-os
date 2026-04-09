---
id: AGOS-0016
title: Memory — CRUD и права доступа
phase: 4 — Memory System
status: pending
depends_on: [AGOS-0003]
files_create: [memory/access.py, memory/memory.py, tests/test_memory.py, tests/test_access.py]
files_modify: []
---

## Описание

Иерархическая память агентов. Три уровня видимости: private (только владелец), shared (указанные агенты), global (все). Мастер видит всё. CRUD операции: remember, recall, share, forget, get_context (все доступные записи для контекста), cleanup (удаление по TTL). Права проверяются через can_access.

## Acceptance Criteria

- [ ] master видит все записи (любой scope)
- [ ] owner видит свои private записи
- [ ] Другие агенты не видят чужие private
- [ ] shared работает для указанных в shared_with агентов
- [ ] global видят все агенты
- [ ] forget удаляет запись
- [ ] get_context возвращает все доступные записи
- [ ] Тесты проходят (5 тестов access + 6 тестов memory)

## Затрагиваемые модули

- memory/access.py: can_access
- memory/memory.py: MemorySystem
- tests/test_access.py, tests/test_memory.py: юнит-тесты

## Ключевые интерфейсы

```python
# access.py
def can_access(requester: str, owner: str, scope: str, shared_with: list[str]) -> bool

# memory.py
class MemorySystem:
    def __init__(self, db: Database)
    async def remember(self, owner, key, value, scope="private", ttl=None) -> int
    async def recall(self, requester, key) -> dict | None
    async def share(self, record_id, agents: list[str]) -> None
    async def forget(self, record_id) -> None
    async def get_context(self, agent) -> list[dict]
    async def cleanup(self) -> int
```

## Edge Cases

- TTL истёк — cleanup удаляет
- shared_with пустой список
- Запись не найдена — recall возвращает None
- Несколько записей с одним key — возвращается первая доступная

## План реализации

### Step 1: Написать тесты

```python
# tests/test_access.py
from memory.access import can_access


def test_master_sees_everything():
    assert can_access(requester="master", owner="jira", scope="private", shared_with=[])


def test_owner_sees_private():
    assert can_access(requester="jira", owner="jira", scope="private", shared_with=[])


def test_other_cannot_see_private():
    assert not can_access(requester="code", owner="jira", scope="private", shared_with=[])


def test_shared_with_specific_agent():
    assert can_access(requester="code", owner="jira", scope="shared", shared_with=["code"])


def test_global_visible_to_all():
    assert can_access(requester="grok", owner="jira", scope="global", shared_with=[])
```

```python
# tests/test_memory.py
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
```

### Step 2: Реализовать access.py

```python
# memory/access.py
import json


def can_access(
    requester: str, owner: str, scope: str, shared_with: list[str]
) -> bool:
    if requester == "master":
        return True
    if requester == owner:
        return True
    if scope == "global":
        return True
    if scope == "shared" and requester in shared_with:
        return True
    return False
```

### Step 3: Реализовать memory.py

```python
# memory/memory.py
import json
from db.database import Database
from memory.access import can_access


class MemorySystem:
    def __init__(self, db: Database):
        self.db = db

    async def remember(
        self,
        owner: str,
        key: str,
        value: str,
        scope: str = "private",
        ttl: str | None = None,
    ) -> int:
        return await self.db.execute(
            """INSERT INTO memory (owner, key, value, scope, ttl)
               VALUES (?, ?, ?, ?, ?)""",
            (owner, key, value, scope, ttl),
        )

    async def recall(self, requester: str, key: str) -> dict | None:
        rows = await self.db.fetch_all(
            "SELECT * FROM memory WHERE key = ?", (key,)
        )
        for row in rows:
            shared_with = json.loads(row["shared_with"]) if row["shared_with"] else []
            if can_access(requester, row["owner"], row["scope"], shared_with):
                return row
        return None

    async def share(self, record_id: int, agents: list[str]) -> None:
        await self.db.execute(
            "UPDATE memory SET scope = 'shared', shared_with = ? WHERE id = ?",
            (json.dumps(agents), record_id),
        )

    async def forget(self, record_id: int) -> None:
        await self.db.execute("DELETE FROM memory WHERE id = ?", (record_id,))

    async def get_context(self, agent: str) -> list[dict]:
        """Получить все записи доступные агенту (для инъекции в контекст)."""
        all_rows = await self.db.fetch_all("SELECT * FROM memory")
        result = []
        for row in all_rows:
            shared_with = json.loads(row["shared_with"]) if row["shared_with"] else []
            if can_access(agent, row["owner"], row["scope"], shared_with):
                result.append(row)
        return result

    async def cleanup(self) -> int:
        """Удалить записи с истекшим TTL. Вернуть количество удалённых."""
        result = await self.db.execute(
            "DELETE FROM memory WHERE ttl IS NOT NULL AND ttl < datetime('now')"
        )
        return result
```

### Step 4: Запустить тесты — PASS

```bash
pytest tests/test_access.py tests/test_memory.py -v
```

### Step 5: Commit

```bash
git add memory/access.py memory/memory.py tests/test_access.py tests/test_memory.py
git commit -m "feat: add hierarchical memory system with access control"
```
