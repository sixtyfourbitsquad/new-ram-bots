"""Register all handlers with the Application."""
from telegram.ext import Application

from bot.handlers.start import register_start
from bot.handlers.admin import register_admin
from bot.handlers.welcome import register_welcome
from bot.handlers.broadcast import register_broadcast
from bot.handlers.join_request import register_join_request


def register_handlers(app: Application) -> None:
    register_start(app)
    register_admin(app)
    register_welcome(app)
    register_broadcast(app)
    register_join_request(app)
