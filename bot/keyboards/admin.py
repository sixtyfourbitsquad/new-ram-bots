"""Admin panel inline keyboards."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Welcome Message", callback_data="admin:add_welcome")],
        [InlineKeyboardButton("📂 Manage Welcome Messages", callback_data="admin:manage_welcome")],
        [InlineKeyboardButton("📺 Set Channel", callback_data="admin:set_channel")],
        [InlineKeyboardButton("🤖 Toggle Auto Accept", callback_data="admin:auto_accept_toggle")],
        [InlineKeyboardButton("🔍 Preview Welcome", callback_data="admin:preview_welcome")],
        [InlineKeyboardButton("📊 User Stats", callback_data="admin:stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton("📡 Broadcast Status", callback_data="broadcast:status")],
        [InlineKeyboardButton("⚙ Bot Configuration", callback_data="admin:config")],
        [InlineKeyboardButton("📜 View Logs", callback_data="admin:logs")],
    ])


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Send", callback_data="broadcast:confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="broadcast:cancel"),
    ]])


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Back to Admin", callback_data="admin:main"),
    ]])
