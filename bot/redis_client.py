"""Async Redis client for broadcast queue and temporary state."""
import json
from typing import Any, Optional

import redis.asyncio as redis
from bot import config
from bot.utils.logging import get_logger

logger = get_logger(__name__)

_redis: Optional[redis.Redis] = None

BROADCAST_QUEUE = "broadcast:queue"
BROADCAST_PENDING_PAYLOAD = "broadcast:pending"
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


async def pop_broadcast_task() -> Optional[dict]:
    r = get_redis()
    raw = await r.lpop(BROADCAST_QUEUE)
    if raw is None:
        return None
    return json.loads(raw)


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
