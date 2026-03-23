"""All database queries. Uses get_pool() for asyncpg."""
from datetime import datetime, timedelta
from typing import List, Optional

from bot.database.pool import get_pool

INIT_SQL = """
CREATE TABLE IF NOT EXISTS welcome_messages (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    file_id VARCHAR(255),
    text TEXT,
    caption TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_welcome_messages_position ON welcome_messages(position);

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_join_requests INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);

CREATE TABLE IF NOT EXISTS broadcast_history (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    content TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_broadcast_history_sent_at ON broadcast_history(sent_at);

CREATE TABLE IF NOT EXISTS welcome_config (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    video_file_id VARCHAR(255),
    video_caption TEXT,
    apk_file_id VARCHAR(255),
    apk_caption TEXT,
    channel_id BIGINT
);
INSERT INTO welcome_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
ALTER TABLE welcome_config ADD COLUMN IF NOT EXISTS channel_id BIGINT;

ALTER TABLE welcome_messages ADD COLUMN IF NOT EXISTS copy_from_chat_id BIGINT;
ALTER TABLE welcome_messages ADD COLUMN IF NOT EXISTS copy_from_message_id INTEGER;
"""


async def ensure_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(INIT_SQL)


async def get_user(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, first_seen, last_seen, total_join_requests FROM users WHERE user_id = $1",
            user_id,
        )
        return dict(row) if row else None


async def upsert_user(user_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, first_seen, last_seen, total_join_requests)
            VALUES ($1, NOW(), NOW(), 0)
            ON CONFLICT (user_id) DO UPDATE SET last_seen = NOW()
            """,
            user_id,
        )


async def increment_join_requests(user_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, first_seen, last_seen, total_join_requests)
            VALUES ($1, NOW(), NOW(), 1)
            ON CONFLICT (user_id) DO UPDATE SET
                last_seen = NOW(),
                total_join_requests = users.total_join_requests + 1
            """,
            user_id,
        )


async def get_user_stats() -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_join = await conn.fetchval("SELECT COALESCE(SUM(total_join_requests), 0) FROM users")
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        join_today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE last_seen >= $1 AND total_join_requests > 0",
            today_start,
        )
        week_ago = datetime.utcnow() - timedelta(days=7)
        active_7d = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen >= $1", week_ago)
    return {
        "total_users": total_users or 0,
        "total_join_requests": total_join or 0,
        "join_requests_today": join_today or 0,
        "active_users_7d": active_7d or 0,
    }


async def get_channel_id():
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT channel_id FROM welcome_config WHERE id = 1")


async def set_channel_id(channel_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE welcome_config SET channel_id = $1 WHERE id = 1", channel_id)


async def get_welcome_messages() -> List[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, type, file_id, text, caption, position,
                      copy_from_chat_id, copy_from_message_id
               FROM welcome_messages ORDER BY position, id"""
        )
        return [dict(r) for r in rows]


async def add_welcome_message(
    msg_type: str,
    file_id: Optional[str],
    text: Optional[str],
    caption: Optional[str],
    copy_from_chat_id: Optional[int] = None,
    copy_from_message_id: Optional[int] = None,
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        max_pos = await conn.fetchval("SELECT COALESCE(MAX(position), -1) FROM welcome_messages")
        new_pos = (max_pos or -1) + 1
        return await conn.fetchval(
            """
            INSERT INTO welcome_messages (type, file_id, text, caption, position, copy_from_chat_id, copy_from_message_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            msg_type, file_id, text or "", caption or "", new_pos, copy_from_chat_id, copy_from_message_id,
        )


async def delete_welcome_message(msg_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM welcome_messages WHERE id = $1", msg_id)
        return result == "DELETE 1"


async def log_broadcast(msg_type: str, content: str, success_count: int, failed_count: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO broadcast_history (type, content, success_count, failed_count) VALUES ($1, $2, $3, $4)",
            msg_type, content[:5000] if content else "", success_count, failed_count,
        )
