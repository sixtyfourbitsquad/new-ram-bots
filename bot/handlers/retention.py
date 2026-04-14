"""Retention drip scheduler and worker (+1h/+1d/+3d)."""
import asyncio

from telegram.error import Forbidden, RetryAfter, TimedOut, NetworkError

from bot import config
from bot.database import (
    schedule_retention_drip_jobs,
    reclaim_stale_retention_jobs,
    claim_due_retention_jobs,
    mark_retention_job_sent,
    mark_retention_job_cancelled,
    mark_retention_job_failed,
)
from bot.utils.logging import get_logger

logger = get_logger(__name__)


async def schedule_retention_for_user(user_id: int, name: str) -> None:
    """Queue drip messages for a user if they were not scheduled yet."""
    if not config.RETENTION_ENABLED:
        return
    try:
        inserted = await schedule_retention_drip_jobs(user_id, name)
        if inserted:
            logger.info("Retention jobs scheduled for user=%s inserted=%s", user_id, inserted)
    except Exception as e:
        logger.exception("schedule_retention_for_user user=%s: %s", user_id, e)


async def _send_retention_message(bot, user_id: int, text: str) -> None:
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            await bot.send_message(chat_id=user_id, text=text)
            return
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.2)
        except (TimedOut, NetworkError):
            if attempt >= attempts:
                raise
            await asyncio.sleep(min(2.0 * attempt, 5.0))


async def retention_worker(bot) -> None:
    """Process due retention jobs from Postgres in small batches."""
    if not config.RETENTION_ENABLED:
        logger.info("Retention worker is disabled by config.")
        return

    interval = max(1, config.RETENTION_CHECK_INTERVAL_SEC)
    batch_size = max(1, config.RETENTION_BATCH_SIZE)
    tick = 0
    logger.info("Retention worker started (interval=%ss, batch=%s).", interval, batch_size)

    while True:
        try:
            await asyncio.sleep(interval)
            tick += 1

            if tick % 6 == 0:
                recovered = await reclaim_stale_retention_jobs()
                if recovered:
                    logger.warning("Recovered %s stale retention job(s).", recovered)

            jobs = await claim_due_retention_jobs(batch_size)
            if not jobs:
                continue

            for job in jobs:
                job_id = int(job["id"])
                user_id = int(job["user_id"])
                attempts = int(job["attempts"] or 0)
                max_attempts = int(job["max_attempts"] or 3)
                text = job.get("message_text") or ""
                stage = job.get("stage_key") or "unknown"
                try:
                    await _send_retention_message(bot, user_id, text)
                    await mark_retention_job_sent(job_id)
                    logger.info("Retention sent: job=%s stage=%s user=%s", job_id, stage, user_id)
                except Forbidden:
                    await mark_retention_job_cancelled(job_id, "Forbidden: user blocked bot or never started")
                except Exception as e:
                    await mark_retention_job_failed(job_id, attempts, max_attempts, str(e))
                    logger.warning(
                        "Retention failed: job=%s stage=%s user=%s attempt=%s/%s error=%s",
                        job_id,
                        stage,
                        user_id,
                        attempts,
                        max_attempts,
                        e,
                    )
        except Exception as e:
            logger.exception("Retention worker loop error: %s", e)
            await asyncio.sleep(2)
