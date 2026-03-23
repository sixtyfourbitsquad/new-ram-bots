"""Capture admin's welcome and channel setting (states: welcome:add, channel:wait)."""
from telegram import Update
from telegram.ext import ContextTypes

from bot import config
from bot.database import set_channel_id, add_welcome_message
from bot.redis_client import get_admin_state, clear_admin_state
from bot.keyboards import admin_main_keyboard, back_to_admin_keyboard
from bot.utils.logging import get_logger

logger = get_logger(__name__)


def _parse_message_content(msg) -> tuple:
    msg_type = "text"
    file_id = None
    text = None
    caption = None
    if msg.text and not (msg.photo or msg.video or msg.animation or msg.document or msg.audio or msg.voice):
        return ("text", None, msg.text, None)
    if msg.photo:
        msg_type, file_id = "photo", msg.photo[-1].file_id
    elif msg.video:
        msg_type, file_id = "video", msg.video.file_id
    elif msg.animation:
        msg_type, file_id = "animation", msg.animation.file_id
    elif msg.document:
        msg_type, file_id = "document", msg.document.file_id
    elif msg.audio:
        msg_type, file_id = "audio", msg.audio.file_id
    elif msg.voice:
        msg_type, file_id = "voice", msg.voice.file_id
    else:
        return (None, None, None, None)
    caption = (msg.caption or "").strip()
    return (msg_type, file_id, text, caption)


async def capture_message_for_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id not in config.ADMIN_IDS:
        return

    state = await get_admin_state(user_id)
    if not state:
        return

    if update.message and update.message.text:
        raw = update.message.text.strip().lower()
        if raw == "/cancel":
            await clear_admin_state(user_id)
            await update.message.reply_text("Cancelled.", reply_markup=admin_main_keyboard())
            return
        if raw == "/done":
            if state == "welcome:add":
                await clear_admin_state(user_id)
                await update.message.reply_text("Done adding welcome messages.", reply_markup=admin_main_keyboard())
            else:
                return
            return

    if state == "channel:wait":
        msg = update.message
        if not msg:
            return
        channel_id = None
        fwd_chat = getattr(msg, "forward_from_chat", None)
        if fwd_chat and getattr(fwd_chat, "type", None) == "channel":
            channel_id = getattr(fwd_chat, "id", None)
        if channel_id is None:
            origin = getattr(msg, "forward_origin", None)
            if origin:
                origin_chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
                if origin_chat and getattr(origin_chat, "type", None) == "channel":
                    channel_id = getattr(origin_chat, "id", None)
        if channel_id is None and msg.text:
            try:
                channel_id = int(msg.text.strip())
            except ValueError:
                pass
        if channel_id is None:
            await msg.reply_text(
                "Send a forwarded message from your channel, or the channel ID (e.g. -1001234567890). /cancel to abort.",
                reply_markup=back_to_admin_keyboard(),
            )
            return
        try:
            await set_channel_id(channel_id)
            await clear_admin_state(user_id)
            await msg.reply_text(
                f"✅ Channel set to `{channel_id}`. Join requests from this channel will be handled.",
                reply_markup=admin_main_keyboard(),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.exception("set_channel_id: %s", e)
            await msg.reply_text(f"Error: {e}", reply_markup=back_to_admin_keyboard())
        return

    if state == "welcome:add":
        msg = update.message
        if not msg:
            return
        msg_type, file_id, text, caption = _parse_message_content(msg)
        if msg_type is None:
            await msg.reply_text("Send text or one media message, or /cancel to abort.", reply_markup=back_to_admin_keyboard())
            return
        try:
            await add_welcome_message(msg_type, file_id, text or "", caption, copy_from_chat_id=msg.chat.id, copy_from_message_id=msg.message_id)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            done_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Done adding", callback_data="welcome:done")],
                [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin:main")],
            ])
            await msg.reply_text(f"✅ Added ({msg_type}). Send another or /done when finished.", reply_markup=done_kb)
        except Exception as e:
            logger.exception("add_welcome_message: %s", e)
            await msg.reply_text(f"Error: {e}")
        return


def register_welcome(app) -> None:
    from telegram.ext import MessageHandler, filters
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL | filters.AUDIO | filters.VOICE),
            capture_message_for_welcome,
        ),
        group=-2,
    )
