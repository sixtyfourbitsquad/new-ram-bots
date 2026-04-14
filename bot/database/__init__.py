"""Database package: pool and table access."""
from bot.database.pool import get_pool, init_pool, close_pool
from bot.database.queries import (
    ensure_tables,
    get_user,
    upsert_user,
    increment_join_requests,
    get_channel_id,
    set_channel_id,
    get_welcome_messages,
    add_welcome_message,
    delete_welcome_message,
    get_user_stats,
    log_broadcast,
    schedule_retention_drip_jobs,
    reclaim_stale_retention_jobs,
    claim_due_retention_jobs,
    mark_retention_job_sent,
    mark_retention_job_cancelled,
    mark_retention_job_failed,
)

__all__ = [
    "get_pool", "init_pool", "close_pool",
    "ensure_tables", "get_user", "upsert_user",
    "increment_join_requests", "get_channel_id", "set_channel_id",
    "get_welcome_messages", "add_welcome_message", "delete_welcome_message",
    "get_user_stats", "log_broadcast",
    "schedule_retention_drip_jobs", "reclaim_stale_retention_jobs",
    "claim_due_retention_jobs", "mark_retention_job_sent",
    "mark_retention_job_cancelled", "mark_retention_job_failed",
]
