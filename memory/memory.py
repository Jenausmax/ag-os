import json
from db.database import Database
from memory.access import can_access

class MemorySystem:
    def __init__(self, db: Database):
        self.db = db

    async def remember(self, owner: str, key: str, value: str, scope: str = "private", ttl: str | None = None) -> int:
        return await self.db.execute(
            "INSERT INTO memory (owner, key, value, scope, ttl) VALUES (?, ?, ?, ?, ?)",
            (owner, key, value, scope, ttl),
        )

    async def recall(self, requester: str, key: str) -> dict | None:
        rows = await self.db.fetch_all("SELECT * FROM memory WHERE key = ?", (key,))
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
        all_rows = await self.db.fetch_all("SELECT * FROM memory")
        result = []
        for row in all_rows:
            shared_with = json.loads(row["shared_with"]) if row["shared_with"] else []
            if can_access(agent, row["owner"], row["scope"], shared_with):
                result.append(row)
        return result

    async def cleanup(self) -> int:
        result = await self.db.execute(
            "DELETE FROM memory WHERE ttl IS NOT NULL AND ttl < datetime('now')"
        )
        return result
