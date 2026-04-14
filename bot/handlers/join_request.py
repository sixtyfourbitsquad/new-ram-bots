"""Chat join request: send full welcome, do NOT approve, log, update stats."""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import Forbidden

from bot import config
from bot.database import increment_join_requests, get_channel_id
from bot.handlers.admin import send_full_welcome
from bot.handlers.retention import schedule_retention_for_user
from bot.redis_client import get_auto_accept_enabled
from bot.utils.logging import get_logger

logger = get_logger(__name__)


async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    req = update.chat_join_request
    if not req:
        return
    channel_id = await get_channel_id()
    if channel_id is None:
        channel_id = config.CHANNEL_ID
    if channel_id is None or req.chat.id != channel_id:
        return

    user_id = req.from_user.id if req.from_user else 0
    name = (req.from_user.first_name or "User") if req.from_user else "User"
    try:
        await increment_join_requests(user_id)
    except Exception as e:
        logger.exception("increment_join_requests: %s", e)

    logger.info("Join request from user_id=%s", user_id)
    try:
        await send_full_welcome(context, user_id, name=name)
        await schedule_retention_for_user(user_id, name)
    except Forbidden:
        logger.info("User %s has not started bot or blocked bot; skip sending", user_id)
    except Exception as e:
        logger.exception("Welcome send to %s: %s", user_id, e)

    try:
        auto_accept = await get_auto_accept_enabled()
    except Exception as e:
        auto_accept = False
        logger.exception("get_auto_accept_enabled: %s", e)

    if auto_accept:
        try:
            await context.bot.approve_chat_join_request(chat_id=req.chat.id, user_id=user_id)
            logger.info("Auto-approved join request for user_id=%s", user_id)
        except Exception as e:
            logger.exception("approve_chat_join_request user_id=%s: %s", user_id, e)

def register_join_request(app) -> None:
    from telegram.ext import ChatJoinRequestHandler
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
