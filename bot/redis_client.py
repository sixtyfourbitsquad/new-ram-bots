"""Async Redis client for broadcast queue and temporary state."""
import json
import time
from typing import Any, Optional

import redis.asyncio as redis
from bot import config
from bot.utils.logging import get_logger

logger = get_logger(__name__)

_redis: Optional[redis.Redis] = None

BROADCAST_QUEUE = "broadcast:queue"
BROADCAST_PENDING_PAYLOAD = "broadcast:pending"  # temp storage for admin's draft
BROADCAST_STATUS_KEY = "broadcast:status"
ADMIN_STATE_PREFIX = "admin:state:"


async def init_redis() -> redis.Redis:
    global _redis
    _redis = redis.from_url(config.REDIS_URL, decode_responses=True)
    await _redis.ping()
    logger.info("Redis connected")
    return _redis


def get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.close()
        _redis = None


async def push_broadcast_task(payload: dict) -> None:
    r = get_redis()
    await r.rpush(BROADCAST_QUEUE, json.dumps(payload))


async def get_broadcast_queue_length() -> int:
    r = get_redis()
    return int(await r.llen(BROADCAST_QUEUE))


async def pop_broadcast_task() -> Optional[dict]:
    r = get_redis()
    raw = await r.lpop(BROADCAST_QUEUE)
    if raw is None:
        return None
    return json.loads(raw)


async def set_broadcast_status(
    state: str,
    total: int = 0,
    processed: int = 0,
    success: int = 0,
    failed: int = 0,
    last_error: str = "",
) -> None:
    """Persist aggregate broadcast progress for admin status view."""
    r = get_redis()
    now = str(int(time.time()))
    current = await get_broadcast_status()
    started_at = current.get("started_at", "0")
    if state in {"running", "queued"} and (not started_at or started_at == "0"):
        started_at = now
    if state in {"completed", "idle", "error"}:
        started_at = current.get("started_at", "0")
    await r.hset(
        BROADCAST_STATUS_KEY,
        mapping={
            "state": state,
            "total": str(total),
            "processed": str(processed),
            "success": str(success),
            "failed": str(failed),
            "last_error": last_error[:500],
            "started_at": str(started_at),
            "updated_at": now,
        },
    )


async def get_broadcast_status() -> dict:
    r = get_redis()
    raw = await r.hgetall(BROADCAST_STATUS_KEY)
    if not raw:
        return {
            "state": "idle",
            "total": "0",
            "processed": "0",
            "success": "0",
            "failed": "0",
            "last_error": "",
            "started_at": "0",
            "updated_at": "0",
        }
    return raw


async def set_pending_broadcast(admin_id: int, payload: dict) -> None:
    r = get_redis()
    await r.setex(f"{BROADCAST_PENDING_PAYLOAD}:{admin_id}", 3600, json.dumps(payload))


async def get_pending_broadcast(admin_id: int) -> Optional[dict]:
    r = get_redis()
    raw = await r.get(f"{BROADCAST_PENDING_PAYLOAD}:{admin_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def clear_pending_broadcast(admin_id: int) -> None:
    r = get_redis()
    await r.delete(f"{BROADCAST_PENDING_PAYLOAD}:{admin_id}")


async def set_admin_state(admin_id: int, state: str) -> None:
    r = get_redis()
    await r.setex(f"{ADMIN_STATE_PREFIX}{admin_id}", 1800, state)


async def get_admin_state(admin_id: int) -> Optional[str]:
    r = get_redis()
    return await r.get(f"{ADMIN_STATE_PREFIX}{admin_id}")


async def clear_admin_state(admin_id: int) -> None:
    r = get_redis()
    await r.delete(f"{ADMIN_STATE_PREFIX}{admin_id}")
