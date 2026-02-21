# services/telegram_service/app/keyboards.py

import logging
from common.messaging.keyboard_utils import KeyboardFactory

logger = logging.getLogger(__name__)


# Re-export keyboard creation functions with platform set to "telegram"
def main_menu_keyboard():
    """Create the main menu keyboard for Telegram"""
    return KeyboardFactory.create_keyboard("telegram", "main_menu")


def property_type_keyboard():
    """Create keyboard for property type selection"""
    return KeyboardFactory.create_keyboard("telegram", "property_type")


def city_keyboard(cities, page=0, show_back=False, show_save=False, selected_city=None):
    """Create keyboard for city selection with pagination"""
    return KeyboardFactory.create_keyboard(
        "telegram",
        "city",
        cities=cities,
        page=page,
        show_back=show_back,
        show_save=show_save,
        selected_city=selected_city,
    )


def rooms_keyboard(selected_rooms=None, show_back=False, show_save=False):
    """Create keyboard for room selection"""
    return KeyboardFactory.create_keyboard(
        "telegram",
        "rooms",
        selected_rooms=selected_rooms,
        show_back=show_back,
        show_save=show_save,
    )


def price_keyboard(city="Київ"):
    """Create keyboard for price range selection"""
    return KeyboardFactory.create_keyboard("telegram", "price", city=city)


def confirmation_keyboard():
    """Create keyboard for subscription confirmation"""
    return KeyboardFactory.create_keyboard("telegram", "confirmation")


def edit_parameters_keyboard():
    """Create keyboard for parameter editing"""
    return KeyboardFactory.create_keyboard("telegram", "edit_parameters")


def floor_keyboard(floor_opts=None, show_back=False):
    """Create keyboard for floor selection"""
    return KeyboardFactory.create_keyboard(
        "telegram", "floor", floor_opts=floor_opts, show_back=show_back
    )


def subscription_menu_keyboard():
    """Sub-menu for "Моя підписка" """
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛑 Відключити"), KeyboardButton(text="✅ Включити")],
            [KeyboardButton(text="✏️ Редагувати"), KeyboardButton(text="↪️ Назад")],
        ],
        resize_keyboard=True,
    )


def how_to_use_keyboard():
    """Sub-menu for 'Як це працює?'"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↪️ Назад")]],
        resize_keyboard=True,
    )


def tech_support_keyboard():
    """Sub-menu for 'Техпідтримка'"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↪️ Назад")]],
        resize_keyboard=True,
    )


def make_subscriptions_page_kb(user_id, page, subscriptions, total_count, per_page=5):
    """Create keyboard for subscription page navigation"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from common.config import GEO_ID_MAPPING

    rows = []

    # 1) Add each subscription as a separate button:
    for sub in subscriptions:
        sub_id = sub["id"]
        city = GEO_ID_MAPPING.get(sub["city"], "Невідомо")
        mapping_property = {"apartment": "квартира", "house": "будинок"}
        ua_lang_property_type = mapping_property.get(sub["property_type"], "")

        # Handle rooms_list being None
        rooms_list = sub["rooms_count"] or []
        if not isinstance(rooms_list, list):
            rooms_list = [rooms_list]  # Convert single value to list

        rooms = []
        for el in rooms_list:
            if el is not None:  # Check for None values in the list
                rooms.append(str(el))

        rooms_text = "-".join(rooms) if rooms else "Будь-яка"

        # Handle price values safely
        price_min = sub.get("price_min", 0)
        price_max = sub.get("price_max", 0)
        if price_min:
            price_min = price_min / 1000
        if price_max:
            price_max = price_max / 1000

        paused_str = " (Призупинена)" if sub.get("is_paused") else ""
        button_text = f"м.{city}, {ua_lang_property_type}, {rooms_text} к., {price_min}-{price_max} тис.грн.{paused_str}"
        rows.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"sub_open:{sub_id}:{page}")]
        )

    # 2) Build the navigation row (Prev / Next) if needed
    max_pages = (total_count - 1) // per_page  # integer division
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="<< Prev", callback_data=f"subs_page:{page - 1}")
        )
    if page < max_pages:
        nav_row.append(
            InlineKeyboardButton(text="Next >>", callback_data=f"subs_page:{page + 1}")
        )

    if nav_row:
        rows.append(nav_row)

    # NEW: Add button to create a brand-new subscription
    rows.append([InlineKeyboardButton(text="➕ Додати підписку", callback_data="subs_new")])

    # Optionally add a "Close" or "Back" button
    rows.append([InlineKeyboardButton(text="Закрити", callback_data="subs_close")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_category_keyboard():
    """A reply keyboard that asks the user to choose a support category."""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Оплата")],
            [KeyboardButton(text="Технічні проблеми")],
            [KeyboardButton(text="Інше")],
            [KeyboardButton(text="Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def support_redirect_keyboard(template_data: str):
    """Build an inline keyboard with a button that opens the support chat."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # For testing, if your support bot is @bookly_beekly, the deep link URL is:
    url = f"https://t.me/bookly_beekly?start={template_data}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Перейти до техпідтримки", url=url)]]
    )


def phone_request_keyboard():
    """Create a keyboard with a button to share phone number."""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поділитися номером телефону", request_contact=True)],
            [KeyboardButton(text="↪️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def verification_code_keyboard():
    """Simple keyboard for when waiting for verification code."""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↪️ Назад")]],
        resize_keyboard=True,
    )


def verification_success_keyboard():
    """Keyboard to show after successful verification."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Повернутися до головного меню", callback_data="return_to_main_menu"
            )]
        ]
    )
