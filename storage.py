# storage.py
# Хранение счётчика в SQLite c async-доступом и транзакционной инкрементацией.

import aiosqlite
import asyncio
from pathlib import Path

DB_PATH = Path("counter.db")
_INIT_SQL = """
CREATE TABLE IF NOT EXISTS counter(
    id INTEGER PRIMARY KEY CHECK (id = 1),
    n  INTEGER NOT NULL
);
"""
_SELECT_SQL = "SELECT n FROM counter WHERE id = 1;"
_INSERT_SQL = "INSERT INTO counter(id, n) VALUES (1, 0);"
_UPDATE_SQL = "UPDATE counter SET n = n + 1 WHERE id = 1 RETURNING n;"

class CounterStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(_INIT_SQL)
            cur = await db.execute(_SELECT_SQL)
            row = await cur.fetchone()
            if row is None:
                await db.execute(_INSERT_SQL)
            await db.commit()

    async def next_number(self) -> int:
        # Гарантируем последовательный инкремент даже при конкурентных апдейтах
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cur = await db.execute(_UPDATE_SQL)
                row = await cur.fetchone()
                await db.commit()
                return int(row[0])