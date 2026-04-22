import os
import tempfile
import aiosqlite
import pytest

from db.database import Database


@pytest.mark.asyncio
async def test_fresh_db_has_clear_before_default_one():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = os.path.join(tmp, "ag.db")
        db = Database(path)
        try:
            await db.init()
            await db.execute(
                "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
                ("* * * * *", "finik", "do stuff"),
            )
            row = await db.fetch_one("SELECT clear_before FROM schedule WHERE agent_name = ?", ("finik",))
            assert row["clear_before"] == 1
        finally:
            await db.close()


@pytest.mark.asyncio
async def test_legacy_db_gets_clear_before_via_alter():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = os.path.join(tmp, "ag.db")
        # Симулируем старую БД без колонки clear_before
        async with aiosqlite.connect(path) as conn:
            await conn.execute(
                "CREATE TABLE schedule ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "cron_expression TEXT NOT NULL, "
                "agent_name TEXT NOT NULL, "
                "prompt TEXT NOT NULL, "
                "enabled INTEGER DEFAULT 1, "
                "last_run TIMESTAMP, "
                "last_result TEXT DEFAULT '', "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            await conn.execute(
                "INSERT INTO schedule (cron_expression, agent_name, prompt) VALUES (?, ?, ?)",
                ("* * * * *", "old", "legacy"),
            )
            await conn.commit()

        db = Database(path)
        try:
            await db.init()
            row = await db.fetch_one("SELECT clear_before FROM schedule WHERE agent_name = ?", ("old",))
            assert row["clear_before"] == 1
        finally:
            await db.close()
