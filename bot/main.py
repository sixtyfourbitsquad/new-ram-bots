"""Entry point: webhook server, uvloop, pool, redis, handlers."""
import asyncio
import time
import sys

if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass

from telegram import Update
from telegram.ext import Application, ContextTypes
from telegram.request import HTTPXRequest

from bot import config
from bot.database import init_pool, close_pool, ensure_tables
from bot.redis_client import init_redis, close_redis
from bot.handlers import register_handlers
from bot.handlers.broadcast import broadcast_worker
from bot.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def _cleanup() -> None:
    try:
        await close_redis()
        logger.info("Redis connection closed.")
    except Exception as e:
        logger.exception("Redis close: %s", e)
    try:
        await close_pool()
        logger.info("Database pool closed.")
    except Exception as e:
        logger.exception("Pool close: %s", e)


async def post_init(app: Application) -> None:
    await init_pool()
    await init_redis()
    await ensure_tables()
    app.bot_data["start_time"] = time.time()
    asyncio.create_task(broadcast_worker(app.bot))
    logger.info("Bot initialized; pool, redis, broadcast worker started.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Update %s caused error: %s", update, context.error)
    if update and isinstance(update, Update) and update.effective_message:
        try:
            user_id = update.effective_user.id if update.effective_user else 0
            if user_id in config.ADMIN_IDS:
                detail = str(context.error) if context.error else "Unknown error"
                if len(detail) > 3000:
                    detail = detail[-3000:]
                await update.effective_message.reply_text(f"⚠️ Error:\n{detail}\n\nCheck Admin → View Logs for details.")
            else:
                await update.effective_message.reply_text("An error occurred. Please try again or contact the admin.")
        except Exception:
            pass


def main() -> None:
    setup_logging()
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    request = HTTPXRequest(connection_pool_size=8, read_timeout=30, write_timeout=30)
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .request(request)
        .build()
    )
    register_handlers(app)
    app.add_error_handler(error_handler)
    try:
        app.run_webhook(
            listen=config.WEBHOOK_HOST,
            port=config.WEBHOOK_PORT,
            url_path=config.WEBHOOK_PATH,
            webhook_url=f"{config.WEBHOOK_URL}/{config.WEBHOOK_PATH}",
        )
    finally:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_cleanup())
        finally:
            loop.close()


if __name__ == "__main__":
    main()
