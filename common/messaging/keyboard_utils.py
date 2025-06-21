# common/messaging/keyboard_utils.py

from typing import List, Any
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger

# City data for reference
AVAILABLE_CITIES = [
    "Івано-Франківськ",
    "Вінниця",
    "Дніпро",
    "Житомир",
    "Запоріжжя",
    "Київ",
    "Кропивницький",
    "Луцьк",
    "Львів",
    "Миколаїв",
    "Одеса",
    "Полтава",
    "Рівне",
    "Суми",
    "Тернопіль",
    "Ужгород",
    "Харків",
    "Херсон",
    "Хмельницький",
    "Черкаси",
    "Чернівці",
]

CITY_GROUPS = {
    "big_cities": {"Київ"},
    "medium_cities": {"Харків", "Дніпро", "Одеса", "Львів"},
    "small_cities": set(AVAILABLE_CITIES)
    - {"Київ", "Харків", "Дніпро", "Одеса", "Львів"},
}


@log_operation("get_price_ranges")
def get_price_ranges(city: str) -> List[tuple]:
    """
    Returns price ranges for the given city.

    Args:
        city: City name

    Returns:
        List of (min_price, max_price) tuples
    """
    with log_context(logger, city=city):
        if city in CITY_GROUPS["big_cities"]:
            # up to 15000, 15000–20000, 20000–30000, more than 30000
            ranges = [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
        elif city in CITY_GROUPS["medium_cities"]:
            # up to 7000, 7000–10000, 10000–15000, more than 15000
            ranges = [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
        else:
            # Default to "smaller" city intervals
            # up to 5000, 5000–7000, 7000–10000, more than 10000
            ranges = [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]

        logger.debug(
            "Got price ranges",
            extra={
                "city": city,
                "ranges_count": len(ranges),
                "city_group": (
                    "big"
                    if city in CITY_GROUPS["big_cities"]
                    else "medium" if city in CITY_GROUPS["medium_cities"] else "small"
                ),
            },
        )

        return ranges


class KeyboardFactory:
    """
    Factory class for creating platform-specific keyboards with a unified interface.

    Provides methods to generate keyboards for various scenarios:
    - Main menu
    - Property type selection
    - City selection
    - Room selection
    - Price range selection
    - Subscription confirmation
    - Edit parameters
    """

    @staticmethod
    @log_operation("create_keyboard")
    def create_keyboard(platform: str, keyboard_type: str, **kwargs) -> Any:
        """
        Create a platform-specific keyboard.

        Args:
            platform: Platform name ('telegram',)
            keyboard_type: Type of keyboard to create
            **kwargs: Additional parameters for specific keyboard types

        Returns:
            Platform-specific keyboard object
        """
        with log_context(logger, platform=platform, keyboard_type=keyboard_type):
            try:
                if platform == "telegram":
                    result = TelegramKeyboardFactory.create_keyboard(
                        keyboard_type, **kwargs
                    )
                else:
                    logger.warning(
                        "Unsupported platform", extra={"platform": platform}
                    )
                    return None

                logger.debug(
                    "Keyboard created successfully",
                    extra={
                        "platform": platform,
                        "keyboard_type": keyboard_type,
                        "has_result": bool(result),
                    },
                )

                return result
            except Exception as e:
                logger.error(
                    "Error creating keyboard",
                    exc_info=True,
                    extra={
                        "platform": platform,
                        "keyboard_type": keyboard_type,
                        "error_type": type(e).__name__,
                    },
                )
                return None


class TelegramKeyboardFactory:
    """Factory for Telegram-specific keyboards"""

    @classmethod
    @log_operation("create_telegram_keyboard")
    def create_keyboard(cls, keyboard_type: str, **kwargs) -> Any:
        """Create a Telegram keyboard based on type"""

        with log_context(logger, keyboard_type=keyboard_type):
            if keyboard_type == "main_menu":
                return cls.create_main_menu_keyboard()
            elif keyboard_type == "property_type":
                return cls.create_property_type_keyboard()
            elif keyboard_type == "city":
                cities = kwargs.get("cities", AVAILABLE_CITIES)
                page = kwargs.get("page", 0)
                show_back = kwargs.get("show_back", False)
                show_save = kwargs.get("show_save", False)
                selected_city = kwargs.get("selected_city", None)
                return cls.create_city_keyboard(
                    cities, page, show_back, show_save, selected_city
                )
            elif keyboard_type == "rooms":
                selected_rooms = kwargs.get("selected_rooms", [])
                show_back = kwargs.get("show_back", False)
                show_save = kwargs.get("show_save", False)
                return cls.create_rooms_keyboard(selected_rooms, show_back, show_save)
            elif keyboard_type == "price":
                city = kwargs.get("city", "Київ")
                return cls.create_price_keyboard(city)
            elif keyboard_type == "confirmation":
                return cls.create_confirmation_keyboard()
            elif keyboard_type == "edit_parameters":
                return cls.create_edit_parameters_keyboard()
            elif keyboard_type == "floor":
                floor_opts = kwargs.get("floor_opts", None)
                show_back = kwargs.get("show_back", False)
                return cls.create_floor_keyboard(floor_opts, show_back)
            else:
                logger.warning(
                    "Unknown keyboard type for Telegram",
                    extra={"keyboard_type": keyboard_type},
                )
                return None

    @staticmethod
    @log_operation("create_main_menu_keyboard")
    def create_main_menu_keyboard():
        """Create the main menu keyboard for Telegram"""
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row(KeyboardButton("📝 Мої підписки"), KeyboardButton("❤️ Обрані"))
        keyboard.row(
            KeyboardButton("🤔 Як це працює?"), KeyboardButton("💳 Оплатити підписку")
        )
        keyboard.row(
            KeyboardButton("🧑‍💻 Техпідтримка"),
            KeyboardButton("📱 Додати номер телефону"),
        )

        logger.debug("Created Telegram main menu keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_property_type_keyboard")
    def create_property_type_keyboard():
        """Create keyboard for property type selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Квартира", callback_data="property_type_apartment"),
            InlineKeyboardButton("Будинок", callback_data="property_type_house"),
        )

        logger.debug("Created Telegram property type keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_city_keyboard")
    def create_city_keyboard(
        cities, page=0, show_back=False, show_save=False, selected_city=None
    ):
        """Create keyboard for city selection with pagination (3x2 grid, 6 per page)"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        per_page = 6
        row_width = 3
        start = page * per_page
        end = start + per_page
        page_cities = cities[start:end]
        keyboard = InlineKeyboardMarkup(row_width=row_width)
        # Add cities in 3x2 grid
        for idx in range(0, len(page_cities), row_width):
            row = []
            for city in page_cities[idx : idx + row_width]:
                label = f"✅ {city}" if city == selected_city else city
                row.append(InlineKeyboardButton(label, callback_data=f"city_{city}"))
            keyboard.row(*row)
        # Pagination controls
        total_pages = (len(cities) - 1) // per_page + 1
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton("⬅️", callback_data=f"city_page_{page-1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton("➡️", callback_data=f"city_page_{page+1}")
            )
        if nav_buttons:
            keyboard.row(*nav_buttons)

        # Save / Back rows (for edit mode)
        if show_save:
            keyboard.row(InlineKeyboardButton("💾 Зберегти", callback_data="city_save"))
        if show_back:
            keyboard.row(InlineKeyboardButton("↪️ Назад", callback_data="cancel_edit"))

        return keyboard

    @staticmethod
    @log_operation("create_rooms_keyboard")
    def create_rooms_keyboard(selected_rooms=None, show_back=False, show_save=False):
        """Create keyboard for room selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        if selected_rooms is None:
            selected_rooms = []

        with log_context(logger, selected_rooms=selected_rooms):
            keyboard = InlineKeyboardMarkup(row_width=3)
            for rooms in range(1, 6):
                label = "5+" if rooms == 5 else str(rooms)
                if rooms in selected_rooms:
                    button_text = f"✅ {label}"
                else:
                    button_text = label
                keyboard.insert(
                    InlineKeyboardButton(button_text, callback_data=f"rooms_{rooms}")
                )

            if show_save:
                keyboard.add(
                    InlineKeyboardButton("💾 Зберегти", callback_data="rooms_save")
                )
            else:
                keyboard.add(InlineKeyboardButton("Далі", callback_data="rooms_done"))

            if show_back:
                keyboard.add(
                    InlineKeyboardButton("↪️ Назад", callback_data="cancel_edit")
                )

            logger.debug(
                "Created Telegram rooms keyboard",
                extra={"selected_count": len(selected_rooms)},
            )
            return keyboard

    @staticmethod
    @log_operation("create_price_keyboard")
    def create_price_keyboard(city):
        """Create keyboard for price range selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        with log_context(logger, city=city):
            intervals = get_price_ranges(city)
            keyboard = InlineKeyboardMarkup(row_width=2)
            for low, high in intervals:
                if high is None:
                    label = f"Більше {low}"
                    callback_data = f"price_{low}_any"
                else:
                    # E.g. "0-5000 UAH", "5000-7000 UAH"
                    if low == 0:
                        label = f"До {high}"  # "up to X"
                    else:
                        label = f"{low}-{high}"
                    callback_data = f"price_{low}_{high}"

                keyboard.insert(
                    InlineKeyboardButton(label, callback_data=callback_data)
                )

            logger.debug(
                "Created Telegram price keyboard",
                extra={"city": city, "intervals_count": len(intervals)},
            )
            return keyboard

    @staticmethod
    @log_operation("create_confirmation_keyboard")
    def create_confirmation_keyboard():
        """Create keyboard for subscription confirmation"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Розширений пошук", callback_data="advanced_search"),
            InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
            InlineKeyboardButton("Підписатися", callback_data="subscribe"),
        )

        logger.debug("Created Telegram confirmation keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_edit_parameters_keyboard")
    def create_edit_parameters_keyboard():
        """Create keyboard for parameter editing"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Місто", callback_data="edit_city"),
            InlineKeyboardButton("Кількість кімнат", callback_data="edit_rooms"),
            InlineKeyboardButton("З тваринами?", callback_data="pets_allowed"),
            InlineKeyboardButton("Від власника?", callback_data="without_broker"),
            InlineKeyboardButton("Поверх", callback_data="edit_floor"),
            InlineKeyboardButton("↪️ Назад", callback_data="cancel_edit"),
        )

        logger.debug("Created Telegram edit parameters keyboard")
        return keyboard

    @staticmethod
    @log_operation("create_floor_keyboard")
    def create_floor_keyboard(floor_opts=None, show_back=False):
        """Create keyboard for floor selection"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        if floor_opts is None:
            floor_opts = {
                "not_first": False,
                "not_last": False,
                "floor_max_6": False,
                "floor_max_10": False,
                "floor_max_17": False,
                "only_last": False,
            }

        with log_context(logger, floor_opts=floor_opts):

            def mark(label, active):
                return f"{'✅ ' if active else ''}{label}"

            kb = InlineKeyboardMarkup(row_width=2)
            kb.insert(
                InlineKeyboardButton(
                    mark("Не перший", floor_opts["not_first"]),
                    callback_data="toggle_floor_not_first",
                )
            )
            kb.insert(
                InlineKeyboardButton(
                    mark("Не останній", floor_opts["not_last"]),
                    callback_data="toggle_floor_not_last",
                )
            )

            kb.add(
                InlineKeyboardButton(
                    mark("До 6 поверху", floor_opts.get("floor_max_6", False)),
                    callback_data="toggle_floor_6",
                )
            )
            kb.insert(
                InlineKeyboardButton(
                    mark("До 10 поверху", floor_opts.get("floor_max_10", False)),
                    callback_data="toggle_floor_10",
                )
            )
            kb.insert(
                InlineKeyboardButton(
                    mark("До 17 поверху", floor_opts.get("floor_max_17", False)),
                    callback_data="toggle_floor_17",
                )
            )

            kb.add(
                InlineKeyboardButton(
                    mark("Останній", floor_opts.get("only_last", False)),
                    callback_data="toggle_floor_only_last",
                )
            )

            # add Back / Done buttons
            if show_back:
                kb.add(InlineKeyboardButton("↪️ Назад", callback_data="cancel_edit"))
            kb.add(InlineKeyboardButton("💾 Зберегти", callback_data="floor_done"))

            logger.debug("Created Telegram floor keyboard")
            return kb
