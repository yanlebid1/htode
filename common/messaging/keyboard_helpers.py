# common/messaging/keyboard_helpers.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def build_inline_keyboard(buttons, row_width=2):
    """Build an InlineKeyboardMarkup from a flat list of buttons, grouping into rows of row_width."""
    rows = [buttons[i:i + row_width] for i in range(0, len(buttons), row_width)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reply_keyboard(rows, resize_keyboard=True, one_time_keyboard=False):
    """Build a ReplyKeyboardMarkup from a list of rows (each row is a list of KeyboardButton)."""
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=resize_keyboard,
        one_time_keyboard=one_time_keyboard,
    )
