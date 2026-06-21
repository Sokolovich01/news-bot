import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

import os
DB_PATH = "/data/news_bot.db"
os.makedirs("/data", exist_ok=True)
logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_articles (
                url      TEXT PRIMARY KEY,
                title    TEXT,
                category TEXT,
                seen_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id   INTEGER PRIMARY KEY,
                name      TEXT,
                username  TEXT,
                is_active INTEGER DEFAULT 1,
                added_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO bot_state (key, value) VALUES ('initialized', 'false')"
        )
        await db.commit()
    logger.info("DB initialized")


# ── Seen articles ────────────────────────────────────────────────────────────

async def is_seen(url: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM seen_articles WHERE url = ?", (url,)
        ) as cur:
            return await cur.fetchone() is not None


async def mark_seen_bulk(items: List[Tuple[str, str, str]]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO seen_articles (url, title, category) VALUES (?, ?, ?)",
            items,
        )
        await db.commit()


async def cleanup_old(days: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        await db.execute("DELETE FROM seen_articles WHERE seen_at < ?", (cutoff,))
        await db.commit()


# ── Bot state ────────────────────────────────────────────────────────────────

async def get_state(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else ""


async def set_state(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def is_paused() -> bool:
    value = await get_state("paused_until")
    if not value:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(value)
    except ValueError:
        return False


async def set_paused(minutes: int):
    if minutes == 0:
        await set_state("paused_until", "")
    else:
        until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        await set_state("paused_until", until)


async def is_initialized() -> bool:
    return await get_state("initialized") == "true"


async def mark_initialized():
    await set_state("initialized", "true")


# ── User management ──────────────────────────────────────────────────────────

async def add_user(chat_id: int, name: str, username: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO users (chat_id, name, username, is_active)
               VALUES (?, ?, ?, 1)""",
            (chat_id, name, username),
        )
        await db.commit()


async def remove_user(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_active = 0 WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()


async def get_active_users() -> List[int]:
    """Returns list of chat_ids for all active users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id FROM users WHERE is_active = 1"
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]


async def get_all_users() -> List[dict]:
    """Returns all users with details (for admin)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, name, username, is_active, added_at FROM users ORDER BY added_at"
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "chat_id":   row[0],
                    "name":      row[1],
                    "username":  row[2],
                    "is_active": row[3],
                    "added_at":  row[4],
                }
                for row in rows
            ]


async def user_exists(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM users WHERE chat_id = ? AND is_active = 1", (chat_id,)
        ) as cur:
            return await cur.fetchone() is not None
