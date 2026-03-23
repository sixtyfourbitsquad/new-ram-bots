"""Welcome message type selection keyboard."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TYPES = [
    ("text", "📝 Text"), ("photo", "🖼 Photo"), ("video", "🎬 Video"),
    ("animation", "🎞 Animation"), ("document", "📄 Document"),
    ("audio", "🎵 Audio"), ("voice", "🎤 Voice"),
]


def welcome_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(label, callback_data=f"welcome:type:{t}") for t, label in TYPES]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("◀️ Cancel", callback_data="admin:main")])
    return InlineKeyboardMarkup(rows)
