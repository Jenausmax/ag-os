import aiosqlite
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        schema = SCHEMA_PATH.read_text()
        await self._conn.executescript(schema)
        await self._ensure_schedule_clear_before()
        await self._conn.commit()

    async def _ensure_schedule_clear_before(self) -> None:
        cur = await self._conn.execute("PRAGMA table_info(schedule)")
        cols = {row[1] for row in await cur.fetchall()}
        if "clear_before" not in cols:
            await self._conn.execute(
                "ALTER TABLE schedule ADD COLUMN clear_before INTEGER NOT NULL DEFAULT 1"
            )

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def execute(self, query: str, params: tuple = ()) -> int:
        cursor = await self._conn.execute(query, params)
        await self._conn.commit()
        return cursor.lastrowid

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
