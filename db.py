import aiosqlite
import logging
import os
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

# On Railway a volume is mounted at /data (see README "Хостинг — Railway") —
# writing the DB there means it survives redeploys. Falls back to a local
# file for local/dev runs where /data doesn't exist. Without this, EVERY
# redeploy wiped the users table, which is exactly what happened in
# production (mom/dad got silently removed after an unrelated code push).
_DATA_DIR = "/data"
if os.path.isdir(_DATA_DIR):
    DB_PATH = os.path.join(_DATA_DIR, "news_bot.db")
else:
    DB_PATH = "news_bot.db"
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
                language  TEXT DEFAULT 'ru',
                added_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migration: add language column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
            await db.commit()
        except Exception:
            pass  # column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS source_health (
                source            TEXT PRIMARY KEY,
                category          TEXT,
                last_success_at   TEXT,
                last_error_at     TEXT,
                last_error        TEXT,
                consecutive_empty INTEGER DEFAULT 0,
                total_fetches     INTEGER DEFAULT 0,
                total_articles    INTEGER DEFAULT 0
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


async def get_active_users_by_lang() -> dict:
    """Returns {lang: [chat_ids]} for all active users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT chat_id, COALESCE(language, 'ru') FROM users WHERE is_active = 1"
        ) as cur:
            rows = await cur.fetchall()
    result: dict = {}
    for chat_id, lang in rows:
        result.setdefault(lang, []).append(chat_id)
    return result


async def set_user_language(chat_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET language = ? WHERE chat_id = ?", (lang, chat_id)
        )
        await db.commit()


async def get_user_language(chat_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(language, 'ru') FROM users WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else "ru"


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


# ── Source health ────────────────────────────────────────────────────────────

async def record_source_result(
    source: str, category: str, ok: bool, article_count: int = 0, error: Optional[str] = None
):
    """
    Track per-RSS-source reliability. `ok=False` means the fetch itself threw
    (network/parse error) — a dead/broken feed. `ok=True, article_count=0` is
    normal (no new articles this cycle) and does NOT count as a failure, but
    still increments the "consecutive empty" streak so a feed that's been
    silent for weeks (likely dead, just not throwing) can also be flagged —
    see SOURCE_FAIL_ALERT_THRESHOLD / cmd_sources in bot.py.
    """
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT consecutive_empty, total_fetches, total_articles FROM source_health WHERE source = ?",
            (source,),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            await db.execute(
                """INSERT INTO source_health
                       (source, category, last_success_at, last_error_at, last_error,
                        consecutive_empty, total_fetches, total_articles)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    source, category,
                    now if ok else None,
                    None if ok else now,
                    None if ok else error,
                    1 if (ok and article_count == 0) else 0,
                    article_count,
                ),
            )
        else:
            prev_empty, prev_fetches, prev_articles = row
            consecutive_empty = prev_empty + 1 if (ok and article_count == 0) else 0
            await db.execute(
                """UPDATE source_health SET
                       category          = ?,
                       last_success_at   = CASE WHEN ? THEN ? ELSE last_success_at END,
                       last_error_at     = CASE WHEN ? THEN ? ELSE last_error_at END,
                       last_error        = CASE WHEN ? THEN ? ELSE last_error END,
                       consecutive_empty = ?,
                       total_fetches     = ?,
                       total_articles    = ?
                   WHERE source = ?""",
                (
                    category,
                    ok, now,
                    not ok, now,
                    not ok, error,
                    consecutive_empty,
                    prev_fetches + 1,
                    prev_articles + article_count,
                    source,
                ),
            )
        await db.commit()


async def get_source_health() -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT source, category, last_success_at, last_error_at, last_error,
                      consecutive_empty, total_fetches, total_articles
               FROM source_health ORDER BY category, source"""
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "source": r[0], "category": r[1],
            "last_success_at": r[2], "last_error_at": r[3], "last_error": r[4],
            "consecutive_empty": r[5], "total_fetches": r[6], "total_articles": r[7],
        }
        for r in rows
    ]
