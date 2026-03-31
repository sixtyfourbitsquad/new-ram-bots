"""Broadcast: wait for message -> store -> confirm -> queue. Worker sends with rate limit."""
import asyncio
import time
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, Forbidden, TimedOut, NetworkError, BadRequest

from bot import config
from bot.database import get_pool, log_broadcast
from bot.redis_client import (
    set_pending_broadcast,
    get_pending_broadcast,
    clear_pending_broadcast,
    push_broadcast_task,
    clear_broadcast_queue,
    get_broadcast_queue_length,
    get_broadcast_status,
    set_broadcast_status,
    get_admin_state,
    set_admin_state,
    clear_admin_state,
)
from bot.keyboards import confirm_broadcast_keyboard, back_to_admin_keyboard
from bot.utils.logging import get_logger

logger = get_logger(__name__)

BROADCAST_RATE = config.BROADCAST_RATE_LIMIT  # 25/sec
SEM = asyncio.Semaphore(1)  # one broadcast at a time
TELEGRAM_RETRY_ATTEMPTS = 3


async def _with_telegram_retry(call_factory, attempts: int = TELEGRAM_RETRY_ATTEMPTS):
    """Retry transient Telegram API/network errors a few times."""
    for attempt in range(1, attempts + 1):
        try:
            return await call_factory()
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.2)
        except (TimedOut, NetworkError):
            if attempt >= attempts:
                raise
            # Short exponential backoff for transient timeout/network blips.
            await asyncio.sleep(min(2.0 * attempt, 5.0))


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await query.answer("Access denied.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "broadcast:status":
        status = await get_broadcast_status()
        queue_len = await get_broadcast_queue_length()
        await _safe_edit_status_message(query, status, queue_len)
        return

    if data == "broadcast:clear_pending":
        status = await get_broadcast_status()
        queue_len = await get_broadcast_queue_length()
        await _safe_edit_status_message(query, status, queue_len, confirm_clear=True)
        return

    if data == "broadcast:clear_pending_confirm":
        removed = await clear_broadcast_queue()
        status = await get_broadcast_status()
        state = status.get("state", "idle")
        if state == "running":
            await set_broadcast_status(
                state="running",
                total=_to_int(status.get("total")),
                processed=_to_int(status.get("processed")),
                success=_to_int(status.get("success")),
                failed=_to_int(status.get("failed")),
                last_error=f"Pending queue cleared by admin ({removed} removed).",
            )
        else:
            await set_broadcast_status(
                state="idle",
                total=0,
                processed=0,
                success=0,
                failed=0,
                last_error=f"Pending queue cleared by admin ({removed} removed).",
            )
        refreshed = await get_broadcast_status()
        queue_len = await get_broadcast_queue_length()
        await _safe_edit_status_message(query, refreshed, queue_len)
        await query.answer(f"Cleared {removed} pending broadcast job(s).", show_alert=True)
        logger.info("Admin %s cleared %s pending broadcast jobs", user_id, removed)
        return

    if data == "broadcast:cancel":
        await clear_admin_state(user_id)
        await clear_pending_broadcast(user_id)
        await query.edit_message_text("Broadcast cancelled.", reply_markup=back_to_admin_keyboard())
        return
    if data == "broadcast:confirm":
        payload = await get_pending_broadcast(user_id)
        if not payload:
            await query.edit_message_text("No pending broadcast.", reply_markup=back_to_admin_keyboard())
            return
        await push_broadcast_task(payload)
        queue_len = await get_broadcast_queue_length()
        status = await get_broadcast_status()
        if status.get("state") != "running":
            await set_broadcast_status(state="queued")
        await clear_pending_broadcast(user_id)
        await clear_admin_state(user_id)
        await query.edit_message_text(
            f"📢 Broadcast queued (queue: {queue_len}). Use `Broadcast Status` to track completion.",
            reply_markup=_broadcast_status_keyboard(),
            parse_mode="Markdown",
        )
        logger.info("Broadcast queued by admin %s", user_id)
        return


async def capture_message_for_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id not in config.ADMIN_IDS:
        return
    state = await get_admin_state(user_id)
    if state != "broadcast:wait_message":
        return
    if update.message and update.message.text and update.message.text.strip() == "/cancel":
        await clear_admin_state(user_id)
        await update.message.reply_text("Cancelled.", reply_markup=back_to_admin_keyboard())
        return
    payload = _message_to_payload(update)
    if not payload:
        await update.message.reply_text("Send text or one media (photo/video/document/audio/voice/animation).")
        return
    await set_pending_broadcast(user_id, payload)
    await set_admin_state(user_id, "broadcast:confirm")
    await update.message.reply_text("Confirm broadcast to all users?", reply_markup=confirm_broadcast_keyboard())


def _message_to_payload(update: Update) -> dict | None:
    msg = update.message
    if not msg:
        return None
    payload = {"type": "text", "text": "", "file_id": None, "caption": None}
    if msg.text:
        payload["text"] = msg.text
        return payload
    if msg.caption is not None:
        payload["caption"] = msg.caption
    if msg.photo:
        payload.update({"type": "photo", "file_id": msg.photo[-1].file_id, "text": msg.caption or ""})
        return payload
    if msg.video:
        payload.update({"type": "video", "file_id": msg.video.file_id, "text": msg.caption or ""})
        return payload
    if msg.animation:
        payload.update({"type": "animation", "file_id": msg.animation.file_id, "text": msg.caption or ""})
        return payload
    if msg.document:
        payload.update({"type": "document", "file_id": msg.document.file_id, "text": msg.caption or ""})
        return payload
    if msg.audio:
        payload.update({"type": "audio", "file_id": msg.audio.file_id, "text": msg.caption or ""})
        return payload
    if msg.voice:
        payload.update({"type": "voice", "file_id": msg.voice.file_id, "text": msg.caption or ""})
        return payload
    return None if payload["type"] == "text" and not payload["text"] else payload


async def _send_one_broadcast(bot, user_id: int, payload: dict) -> bool:
    try:
        t = payload.get("type", "text")
        text = payload.get("text") or ""
        file_id = payload.get("file_id")
        caption = payload.get("caption") or text
        if t == "text":
            await _with_telegram_retry(lambda: bot.send_message(user_id, text))
        elif t == "photo":
            await _with_telegram_retry(lambda: bot.send_photo(user_id, file_id, caption=caption or None))
        elif t == "video":
            await _with_telegram_retry(lambda: bot.send_video(user_id, file_id, caption=caption or None))
        elif t == "animation":
            await _with_telegram_retry(lambda: bot.send_animation(user_id, file_id, caption=caption or None))
        elif t == "document":
            await _with_telegram_retry(lambda: bot.send_document(user_id, file_id, caption=caption or None))
        elif t == "audio":
            await _with_telegram_retry(lambda: bot.send_audio(user_id, file_id, caption=caption or None))
        elif t == "voice":
            await _with_telegram_retry(lambda: bot.send_voice(user_id, file_id, caption=caption or None))
        else:
            await _with_telegram_retry(lambda: bot.send_message(user_id, text or "(no content)"))
        return True
    except Forbidden:
        return False
    except Exception as e:
        logger.warning("Broadcast to %s failed: %s", user_id, e)
        return False


def _progress_bar(processed: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[" + ("-" * width) + "] 0%"
    ratio = min(max(processed / total, 0.0), 1.0)
    filled = int(ratio * width)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + f"] {int(ratio * 100)}%"


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


async def _safe_edit_status_message(
    query,
    status: dict,
    queue_len: int,
    confirm_clear: bool = False,
) -> None:
    try:
        await query.edit_message_text(
            _format_broadcast_status(status, queue_len),
            reply_markup=_broadcast_status_keyboard(confirm_clear=confirm_clear),
            parse_mode="Markdown",
        )
    except BadRequest as e:
        # Telegram raises this when refreshed content is identical.
        if "message is not modified" in str(e).lower():
            await query.answer("Status unchanged.", show_alert=False)
            return
        raise


def _format_broadcast_status(status: dict, queue_len: int) -> str:
    state = status.get("state", "idle")
    total = int(status.get("total", "0") or 0)
    processed = int(status.get("processed", "0") or 0)
    success = int(status.get("success", "0") or 0)
    failed = int(status.get("failed", "0") or 0)
    started_at = int(status.get("started_at", "0") or 0)
    updated_at = int(status.get("updated_at", "0") or 0)
    last_error = status.get("last_error", "")

    elapsed = "-"
    if started_at > 0:
        ref = updated_at if updated_at > 0 else int(time.time())
        elapsed = f"{max(0, ref - started_at)}s"

    lines = [
        "📡 *Broadcast Status*",
        "",
        f"State: `{state}`",
        f"Queue: `{queue_len}` pending job(s)",
        f"Progress: `{processed}/{total}`",
        _progress_bar(processed, total),
        f"Success: `{success}`",
        f"Failed: `{failed}`",
        f"Elapsed: `{elapsed}`",
    ]
    if last_error:
        lines.append(f"Last error: `{last_error[:120]}`")
    return "\n".join(lines)


def _broadcast_status_keyboard(confirm_clear: bool = False) -> InlineKeyboardMarkup:
    if confirm_clear:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Confirm Clear Pending Queue", callback_data="broadcast:clear_pending_confirm")],
                [InlineKeyboardButton("↩️ Keep Queue", callback_data="broadcast:status")],
                [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin:main")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="broadcast:status")],
            [InlineKeyboardButton("🧹 Clear Pending Queue", callback_data="broadcast:clear_pending")],
            [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin:main")],
        ]
    )


async def broadcast_worker(bot) -> None:
    from bot.redis_client import pop_broadcast_task
    from bot.database import get_pool
    while True:
        try:
            await asyncio.sleep(1)
            payload = await pop_broadcast_task()
            if not payload:
                continue
            async with SEM:
                try:
                    pool = get_pool()
                    async with pool.acquire() as conn:
                        rows = await conn.fetch("SELECT user_id FROM users")
                    user_ids = [r["user_id"] for r in rows]
                except Exception as e:
                    logger.exception("Broadcast get users: %s", e)
                    await set_broadcast_status(state="error", last_error=str(e))
                    continue
                success = 0
                failed = 0
                processed = 0
                total = len(user_ids)
                await set_broadcast_status(
                    state="running",
                    total=total,
                    processed=0,
                    success=0,
                    failed=0,
                )
                interval = 1.0 / BROADCAST_RATE
                for uid in user_ids:
                    ok = await _send_one_broadcast(bot, uid, payload)
                    processed += 1
                    if ok:
                        success += 1
                    else:
                        failed += 1
                    if processed % 25 == 0 or processed == total:
                        await set_broadcast_status(
                            state="running",
                            total=total,
                            processed=processed,
                            success=success,
                            failed=failed,
                        )
                    await asyncio.sleep(interval)
                content_preview = (payload.get("text") or payload.get("caption") or payload.get("type", ""))[:500]
                try:
                    await log_broadcast(
                        payload.get("type", "text"),
                        content_preview,
                        success,
                        failed,
                    )
                except Exception as e:
                    logger.exception("log_broadcast: %s", e)
                await set_broadcast_status(
                    state="completed",
                    total=total,
                    processed=processed,
                    success=success,
                    failed=failed,
                )
                logger.info("Broadcast finished: success=%s failed=%s", success, failed)
        except Exception as e:
            # Guard the worker loop so transient errors never kill broadcast processing.
            logger.exception("Broadcast worker loop error: %s", e)
            await set_broadcast_status(state="error", last_error=str(e))
            await asyncio.sleep(2)


def register_broadcast(app) -> None:
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    app.add_handler(CallbackQueryHandler(broadcast_callback, pattern="^broadcast:"))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL | filters.AUDIO | filters.VOICE),
            capture_message_for_broadcast,
        ),
        group=-1,
    )
