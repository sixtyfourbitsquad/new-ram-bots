"""Admin panel callback handlers."""
import asyncio
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import NetworkError
from telegram.helpers import escape_markdown

from bot import config
from bot.database import (
    get_user_stats,
    get_channel_id,
    get_welcome_messages,
    delete_welcome_message,
    get_pool,
)
from bot.redis_client import (
    get_redis,
    set_admin_state,
    get_admin_state,
    clear_admin_state,
    get_auto_accept_enabled,
    toggle_auto_accept_enabled,
)
from bot.keyboards import admin_main_keyboard, back_to_admin_keyboard
from bot.utils.logging import get_logger

logger = get_logger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await query.answer("Access denied.", show_alert=True)
        return
    await query.answer()
    try:
        await _admin_callback_handle(query, context, user_id, query.data)
    except NetworkError as e:
        logger.warning("Admin callback network error: %s", e)
        try:
            if query.message:
                await query.message.reply_text("⚠️ Network error. Please try again.")
        except Exception:
            pass


async def _admin_callback_handle(query, context, user_id, data) -> None:
    if data == "admin:main":
        await query.edit_message_text("👋 Admin panel. Choose an option:", reply_markup=admin_main_keyboard())
        await clear_admin_state(user_id)
        return

    if data == "admin:add_welcome":
        await set_admin_state(user_id, "welcome:add")
        await query.edit_message_text(
            "➕ **Add welcome messages**\n\n"
            "• Send or forward one or more messages.\n"
            "• Types: text, photo, video, GIF, document, audio, voice.\n"
            "• Use {name} in text/caption for the user's name.\n\n"
            "When finished: send /done or tap « Done adding » below.\n"
            "Send /cancel to cancel.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="Markdown",
        )
        return

    if data == "admin:set_channel":
        await set_admin_state(user_id, "channel:wait")
        await query.edit_message_text(
            "📺 **Set join-request channel**\n\n"
            "• Forward any message from your channel here, or\n"
            "• Send the channel ID (e.g. `-1001234567890`).\n\n"
            "Send /cancel to abort.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="Markdown",
        )
        return

    if data == "admin:manage_welcome":
        messages = await get_welcome_messages()
        if not messages:
            await query.edit_message_text("No welcome messages yet.", reply_markup=back_to_admin_keyboard())
            return
        await query.edit_message_text("Welcome messages (tap 🗑 to delete):", reply_markup=welcome_list_keyboard(messages))
        return

    if data == "admin:preview_welcome":
        await query.edit_message_text("Sending preview...")
        chat_id = query.message.chat_id if query.message else 0
        try:
            await send_full_welcome(context, chat_id, name="Admin")
            await context.bot.send_message(chat_id, "✅ Preview done.", reply_markup=back_to_admin_keyboard())
        except Exception as e:
            logger.exception("Preview error: %s", e)
            await context.bot.send_message(chat_id, f"⚠️ Error: {e}", reply_markup=back_to_admin_keyboard())
        return

    if data == "admin:auto_accept_toggle":
        enabled = await toggle_auto_accept_enabled()
        state_label = "ON ✅" if enabled else "OFF ❌"
        await query.edit_message_text(
            f"🤖 Channel Auto Accept is now: *{state_label}*\n\n"
            "When ON, join requests in your configured channel are automatically approved.\n"
            "When OFF, users only receive welcome messages.",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="Markdown",
        )
        return

    if data == "admin:stats":
        stats = await get_user_stats()
        text = (
            f"📊 **User Stats**\n\n"
            f"Total users: {stats['total_users']}\n"
            f"Total join requests: {stats['total_join_requests']}\n"
            f"Join requests today: {stats['join_requests_today']}\n"
            f"Active users (7 days): {stats['active_users_7d']}"
        )
        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="Markdown")
        return

    if data == "admin:broadcast":
        await set_admin_state(user_id, "broadcast:wait_message")
        await query.edit_message_text(
            "📢 Send the message to broadcast to all users. /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="broadcast:cancel")]]),
        )
        return

    if data == "admin:config":
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_status = "✅ Connected"
        except Exception as e:
            db_status = f"❌ {e!s}"
        try:
            r = get_redis()
            await r.ping()
            redis_status = "✅ Connected"
        except Exception as e:
            redis_status = f"❌ {e!s}"
        uptime = "N/A"
        if context.bot_data.get("start_time"):
            import time
            uptime = str(int(time.time() - context.bot_data["start_time"])) + "s"
        channel_id = await get_channel_id()
        if channel_id is None:
            channel_id = config.CHANNEL_ID
        channel_display = f"`{channel_id}`" if channel_id is not None else "_Not set (set via Admin → Set Channel)_"
        auto_accept = await get_auto_accept_enabled()
        auto_accept_label = "ON ✅" if auto_accept else "OFF ❌"
        stats = await get_user_stats()
        welcome_count = len(await get_welcome_messages())
        text = (
            f"⚙ **Bot Configuration**\n\n"
            f"Uptime: {uptime}\n"
            f"Total users: {stats['total_users']}\n"
            f"Welcome messages: {welcome_count}\n"
            f"Channel auto accept: {auto_accept_label}\n"
            f"Channel ID: {channel_display}\n"
            f"Admin IDs: `{config.ADMIN_IDS}`\n\n"
            f"DB: {db_status}\n"
            f"Redis: {redis_status}"
        )
        await query.edit_message_text(text, reply_markup=back_to_admin_keyboard(), parse_mode="Markdown")
        return

    if data == "admin:logs":
        await query.answer("Preparing logs...")
        log_path = Path(config.LOG_FILE)
        if not log_path.exists():
            await query.edit_message_text("No log file found.", reply_markup=back_to_admin_keyboard())
            return
        lines = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        last_100 = "\n".join(lines[-100:]) if lines else "(empty)"
        if len(last_100) > 4000:
            last_100 = last_100[-4000:]
        await query.edit_message_text(f"📜 Last 100 lines:\n\n```\n{last_100}\n```", reply_markup=back_to_admin_keyboard())
        try:
            with open(log_path, "rb") as f:
                await context.bot.send_document(chat_id=query.message.chat_id, document=f, filename="bot.log", caption="Full log file")
        except Exception as e:
            logger.exception("Send log file: %s", e)
        return


def welcome_list_keyboard(messages: list) -> InlineKeyboardMarkup:
    rows = []
    for idx, m in enumerate(messages, start=1):
        rows.append([
            InlineKeyboardButton(f"#{idx} {m.get('type', 'text')}", callback_data="noop"),
            InlineKeyboardButton("🗑", callback_data=f"welcome:del:{m['id']}"),
        ])
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="admin:main")])
    return InlineKeyboardMarkup(rows)


def _apply_name(text: str | None, name: str) -> str:
    if not text:
        return ""
    name = name or "User"
    if "{name}" not in text:
        return text
    parts = text.split("{name}")
    escaped_parts = [escape_markdown(p, version=1) for p in parts]
    bold_name = "*" + escape_markdown(name, version=1) + "*"
    return bold_name.join(escaped_parts)


async def _send_message_list(bot, chat_id, messages, name, log_prefix="send") -> None:
    for m in messages:
        raw_text = m.get("text") or ""
        raw_caption = m.get("caption") or ""
        needs_name = "{name}" in raw_text or "{name}" in raw_caption
        copy_chat = m.get("copy_from_chat_id")
        copy_msg_id = m.get("copy_from_message_id")
        if not needs_name and copy_chat is not None and copy_msg_id is not None:
            try:
                await bot.copy_message(chat_id=chat_id, from_chat_id=copy_chat, message_id=copy_msg_id)
                await asyncio.sleep(0.25)
                continue
            except Exception as e:
                logger.warning("%s copy_message fallback: %s", log_prefix, e)
        t = m.get("type", "text")
        file_id = m.get("file_id")
        text = _apply_name(raw_text, name)
        caption = _apply_name(raw_caption, name)
        if caption and len(caption) > 1024:
            caption = caption[:1021] + "..."
        use_md = bool(needs_name)
        try:
            if t == "text":
                await bot.send_message(chat_id, text or "(empty)", parse_mode="Markdown" if use_md else None)
            elif t == "photo":
                await bot.send_photo(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            elif t == "video":
                await bot.send_video(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            elif t == "animation":
                await bot.send_animation(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            elif t == "document":
                await bot.send_document(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            elif t == "audio":
                await bot.send_audio(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            elif t == "voice":
                await bot.send_voice(chat_id, file_id, caption=caption or None, parse_mode="Markdown" if use_md else None)
            else:
                await bot.send_message(chat_id, text or "(unknown type)", parse_mode="Markdown" if use_md else None)
        except Exception as e:
            logger.exception("%s error: %s", log_prefix, e)
        await asyncio.sleep(0.25)


async def send_full_welcome(context: ContextTypes.DEFAULT_TYPE, chat_id: int, name: str) -> None:
    """Send all welcome messages. Replaces {name} in text and captions."""
    from bot.database import get_welcome_messages
    bot = context.bot
    welcome = await get_welcome_messages()
    if not welcome:
        try:
            await bot.send_message(chat_id, "Welcome! No messages configured yet.")
        except Exception as e:
            logger.exception("send_full_welcome (empty): %s", e)
        return
    await _send_message_list(bot, chat_id, welcome, name, "welcome")


async def handle_welcome_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("welcome:"):
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await query.answer("Access denied.", show_alert=True)
        return
    try:
        data = query.data
        if data == "welcome:done":
            await query.answer()
            await clear_admin_state(user_id)
            await query.edit_message_text("Done adding welcome messages.", reply_markup=back_to_admin_keyboard())
            return
        if data.startswith("welcome:del:"):
            try:
                msg_id = int(data.split(":")[-1])
            except ValueError:
                await query.answer("Invalid id.", show_alert=True)
                return
            ok = await delete_welcome_message(msg_id)
            await query.answer("Deleted." if ok else "Not found.", show_alert=not ok)
            messages = await get_welcome_messages()
            if not messages:
                await query.edit_message_text("No welcome messages left.", reply_markup=back_to_admin_keyboard())
            else:
                await query.edit_message_text("Welcome messages (tap 🗑 to delete):", reply_markup=welcome_list_keyboard(messages))
    except NetworkError as e:
        logger.warning("Welcome callback network error: %s", e)
        try:
            if query.message:
                await query.message.reply_text("⚠️ Network error. Please try again.")
        except Exception:
            pass


def register_admin(app) -> None:
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(handle_welcome_callbacks, pattern="^welcome:"))
