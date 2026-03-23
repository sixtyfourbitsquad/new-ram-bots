"""Start command: admin panel for admins, welcome flow for users."""
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from bot import config
from bot.database import upsert_user
from bot.keyboards import admin_main_keyboard
from bot.handlers.admin import send_full_welcome
from bot.utils.logging import get_logger

logger = get_logger(__name__)


async def update_last_seen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        try:
            await upsert_user(user.id)
        except Exception as e:
            logger.debug("upsert_user: %s", e)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    try:
        await upsert_user(user_id)
    except Exception as e:
        logger.exception("upsert_user: %s", e)

    if user_id in config.ADMIN_IDS:
        await update.message.reply_text("👋 Admin panel. Choose an option:", reply_markup=admin_main_keyboard())
    else:
        name = user.first_name or "User"
        await send_full_welcome(context, user_id, name=name)


async def _callback_update_seen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        try:
            await upsert_user(user.id)
        except Exception as e:
            logger.debug("upsert_user: %s", e)


def register_start(app) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, update_last_seen), group=0)
    app.add_handler(CallbackQueryHandler(_callback_update_seen), group=-1)
