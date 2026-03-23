"""Broadcast: wait for message -> store -> confirm -> queue. Worker sends with rate limit."""
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, Forbidden

from bot import config
from bot.database import get_pool, log_broadcast
from bot.redis_client import (
    set_pending_broadcast, get_pending_broadcast, clear_pending_broadcast,
    push_broadcast_task, get_admin_state, set_admin_state, clear_admin_state,
)
from bot.keyboards import confirm_broadcast_keyboard, back_to_admin_keyboard
from bot.utils.logging import get_logger

logger = get_logger(__name__)
BROADCAST_RATE = config.BROADCAST_RATE_LIMIT
SEM = asyncio.Semaphore(1)


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
        await clear_pending_broadcast(user_id)
        await clear_admin_state(user_id)
        await query.edit_message_text("📢 Broadcast queued.", reply_markup=back_to_admin_keyboard())
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
            await bot.send_message(user_id, text)
        elif t == "photo":
            await bot.send_photo(user_id, file_id, caption=caption or None)
        elif t == "video":
            await bot.send_video(user_id, file_id, caption=caption or None)
        elif t == "animation":
            await bot.send_animation(user_id, file_id, caption=caption or None)
        elif t == "document":
            await bot.send_document(user_id, file_id, caption=caption or None)
        elif t == "audio":
            await bot.send_audio(user_id, file_id, caption=caption or None)
        elif t == "voice":
            await bot.send_voice(user_id, file_id, caption=caption or None)
        else:
            await bot.send_message(user_id, text or "(no content)")
        return True
    except Forbidden:
        return False
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await _send_one_broadcast(bot, user_id, payload)
    except Exception as e:
        logger.warning("Broadcast to %s failed: %s", user_id, e)
        return False


async def broadcast_worker(bot) -> None:
    from bot.redis_client import pop_broadcast_task
    from bot.database import get_pool
    while True:
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
                continue
            success = failed = 0
            interval = 1.0 / BROADCAST_RATE
            for uid in user_ids:
                ok = await _send_one_broadcast(bot, uid, payload)
                if ok:
                    success += 1
                else:
                    failed += 1
                await asyncio.sleep(interval)
            content_preview = (payload.get("text") or payload.get("caption") or payload.get("type", ""))[:500]
            try:
                await log_broadcast(payload.get("type", "text"), content_preview, success, failed)
            except Exception as e:
                logger.exception("log_broadcast: %s", e)
            logger.info("Broadcast finished: success=%s failed=%s", success, failed)


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
