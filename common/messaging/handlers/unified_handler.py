# common/messaging/handlers/unified_handler.py

from typing import Dict, Any, List, Union

from common.db.operations import (
    get_subscription_data_for_user,
    get_subscription_until_for_user,
    update_user_filter,
    add_favorite_ad,
    remove_favorite_ad,
    list_favorites,
)
from common.config import GEO_ID_MAPPING
from common.messaging.unified_platform_utils import safe_send_message, safe_send_menu
from common.messaging.unified_platform_utils import resolve_user_id

from common.messaging.handlers import logger
from common.utils.logging_config import log_operation, log_context


@log_operation("handle_main_menu")
async def handle_main_menu(user_id: Union[str, int], platform: str = None):
    """
    Show the main menu across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        options = [
            {"text": "📝 Мої підписки", "value": "my_subscriptions"},
            {"text": "❤️ Обрані", "value": "favorites"},
            {"text": "🤔 Як це працює?", "value": "how_it_works"},
            {"text": "💳 Оплатити підписку", "value": "payment"},
            {"text": "🧑‍💻 Техпідтримка", "value": "support"},
            {"text": "📱 Номер телефону", "value": "phone_verification"},
        ]

        await safe_send_menu(
            user_id=user_id, text="Головне меню:", options=options, platform=platform
        )
        logger.debug("Main menu sent", extra={"user_id": user_id, "platform": platform})
        return True


@log_operation("handle_how_it_works")
async def handle_how_it_works(user_id: Union[str, int], platform: str = None):
    """
    Show help information across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        text = (
            "Як використовувати:\n\n"
            "1. Налаштуйте параметри фільтра.\n"
            "2. Увімкніть передплату.\n"
            "3. Отримуйте сповіщення.\n\n"
            "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
        )

        options = [{"text": "↪️ Назад", "value": "back_to_menu"}]

        await safe_send_menu(
            user_id=user_id, text=text, options=options, platform=platform
        )
        logger.debug(
            "Help information sent", extra={"user_id": user_id, "platform": platform}
        )
        return True


@log_operation("handle_subscription_info")
async def handle_subscription_info(user_id: Union[str, int], platform: str = None):
    """
    Display subscription details across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        try:
            # Get database user ID
            db_user_id, _, _ = resolve_user_id(user_id, platform)

            if not db_user_id:
                logger.warning(
                    "Failed to resolve user ID",
                    extra={"user_id": user_id, "platform": platform},
                )
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося визначити вашого користувача.",
                    platform=platform,
                )
                return False

            # Get subscription data
            sub_data = get_subscription_data_for_user(db_user_id)
            subscription_until = get_subscription_until_for_user(db_user_id, free=True)
            if not subscription_until:
                subscription_until = get_subscription_until_for_user(
                    db_user_id, free=False
                )

            if not sub_data:
                logger.info(
                    "No active subscription found",
                    extra={
                        "user_id": user_id,
                        "db_user_id": db_user_id,
                        "platform": platform,
                    },
                )
                await safe_send_message(
                    user_id, "У вас немає активної підписки.", platform=platform
                )
                return True

            # Format subscription details
            city = GEO_ID_MAPPING.get(sub_data["city"])
            mapping_property = {"apartment": "Квартира", "house": "Будинок"}
            ua_lang_property_type = mapping_property.get(sub_data["property_type"], "")

            rooms_list = sub_data["rooms_count"]
            rooms = []
            for el in rooms_list:
                rooms.append(str(el))
            rooms = "-".join(rooms)

            text = (
                f"Деталі підписки:\n"
                f"  - Місто: {city}\n"
                f"  - Тип нерухомості: {ua_lang_property_type}\n"
                f"  - К-сть кімнат: {rooms}\n"
                f"  - Ціна: {str(sub_data['price_min'])} - {str(sub_data['price_max'])} грн.\n\n"
                f"Підписка спливає {subscription_until}\n"
            )

            options = [
                {"text": "🛑 Відключити", "value": "disable_subscription"},
                {"text": "✅ Включити", "value": "enable_subscription"},
                {"text": "✏️ Редагувати", "value": "edit_subscription"},
                {"text": "↪️ Назад", "value": "back_to_menu"},
            ]

            await safe_send_menu(
                user_id=user_id, text=text, options=options, platform=platform
            )

            logger.info(
                "Subscription info displayed",
                extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id,
                    "platform": platform,
                    "has_active_subscription": True,
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Error displaying subscription info",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("handle_favorites")
async def handle_favorites(user_id: Union[str, int], platform: str = None):
    """
    Handle favorite listings across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        try:
            # Get database user ID
            db_user_id, _, _ = resolve_user_id(user_id, platform)

            if not db_user_id:
                logger.warning(
                    "Failed to resolve user ID",
                    extra={"user_id": user_id, "platform": platform},
                )
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося визначити вашого користувача.",
                    platform=platform,
                )
                return False

            # Get favorites
            favorites = list_favorites(db_user_id)

            if not favorites:
                logger.info(
                    "No favorites found",
                    extra={
                        "user_id": user_id,
                        "db_user_id": db_user_id,
                        "platform": platform,
                    },
                )
                await safe_send_message(
                    user_id, "У вас немає обраних оголошень.", platform=platform
                )
                return True

            logger.info(
                "Retrieved favorites",
                extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id,
                    "platform": platform,
                    "favorites_count": len(favorites),
                },
            )
            # Let the platform-specific handler show the favorites since the UI is very different
            # Just return the data
            return favorites

        except Exception as e:
            logger.error(
                "Error handling favorites",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("handle_property_type_selection")
async def handle_property_type_selection(
    user_id: Union[str, int], platform: str = None
):
    """
    Show property type selection across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        options = [
            {"text": "Квартира", "value": "property_type_apartment"},
            {"text": "Будинок", "value": "property_type_house"},
        ]

        await safe_send_menu(
            user_id=user_id,
            text="🏷 Оберіть тип нерухомості:",
            options=options,
            platform=platform,
        )

        logger.debug(
            "Property type selection menu sent",
            extra={"user_id": user_id, "platform": platform, "options": len(options)},
        )
        return True


@log_operation("handle_city_selection")
async def handle_city_selection(
    user_id: Union[str, int], platform: str = None, cities: List[str] = None
):
    """
    Show city selection across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        platform: Optional platform identifier
        cities: Optional list of available cities
    """
    with log_context(logger, user_id=user_id, platform=platform):
        if not cities:
            # Default list of cities
            cities = [
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

        # Create options for the menu
        options = [{"text": city, "value": f"city_{city.lower()}"} for city in cities]

        await safe_send_menu(
            user_id=user_id, text="🏙️ Оберіть місто:", options=options, platform=platform
        )

        logger.debug(
            "City selection menu sent",
            extra={
                "user_id": user_id,
                "platform": platform,
                "cities_count": len(cities),
            },
        )
        return True


@log_operation("handle_rooms_selection")
async def handle_rooms_selection(
    user_id: Union[str, int], selected_rooms: List[int] = None, platform: str = None
):
    """
    Show room selection across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        selected_rooms: Optional list of already selected rooms
        platform: Optional platform identifier
    """
    with log_context(
        logger, user_id=user_id, platform=platform, selected_rooms=selected_rooms
    ):
        if selected_rooms is None:
            selected_rooms = []

        # Create options for room selection
        options = []
        for room in range(1, 6):
            text = f"✅ {room}" if room in selected_rooms else f"{room}"
            options.append({"text": text, "value": f"room_{room}"})

        # Add additional options
        options.append({"text": "Далі", "value": "rooms_done"})
        options.append({"text": "Пропустити", "value": "rooms_any"})

        await safe_send_menu(
            user_id=user_id,
            text="🛏️ Виберіть кількість кімнат (можна обрати декілька):",
            options=options,
            platform=platform,
        )

        logger.debug(
            "Room selection menu sent",
            extra={
                "user_id": user_id,
                "platform": platform,
                "selected_rooms": selected_rooms,
                "options_count": len(options),
            },
        )
        return True


@log_operation("handle_price_selection")
async def handle_price_selection(
    user_id: Union[str, int], city: str, platform: str = None
):
    """
    Show price selection across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        city: City name for appropriate price ranges
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, city=city, platform=platform):
        # Define price ranges based on city
        big_cities = {"Київ"}
        medium_cities = {"Харків", "Дніпро", "Одеса", "Львів"}

        if city in big_cities:
            price_ranges = [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
        elif city in medium_cities:
            price_ranges = [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
        else:
            price_ranges = [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]

        # Create options from price ranges
        options = []
        for low, high in price_ranges:
            if high is None:
                label = f"Більше {low} грн."
                value = f"price_{low}_any"
            else:
                if low == 0:
                    label = f"До {high} грн."
                else:
                    label = f"{low}-{high} грн."
                value = f"price_{low}_{high}"

            options.append({"text": label, "value": value})

        await safe_send_menu(
            user_id=user_id,
            text="💰 Виберіть діапазон цін (грн):",
            options=options,
            platform=platform,
        )

        logger.debug(
            "Price selection menu sent",
            extra={
                "user_id": user_id,
                "city": city,
                "platform": platform,
                "price_ranges_count": len(price_ranges),
            },
        )
        return True


@log_operation("handle_subscription_confirmation")
async def handle_subscription_confirmation(
    user_id: Union[str, int], user_data: Dict[str, Any], platform: str = None
):
    """
    Show subscription confirmation across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        user_data: Dictionary with user's filter data
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        try:
            # Format the data for display
            property_type = user_data.get("property_type", "")
            mapping_property = {"apartment": "Квартира", "house": "Будинок"}
            ua_lang_property_type = mapping_property.get(property_type, "")

            city = user_data.get("city", "")
            rooms = (
                ", ".join(map(str, user_data.get("rooms", [])))
                if user_data.get("rooms")
                else "Не важливо"
            )

            price_min = user_data.get("price_min")
            price_max = user_data.get("price_max")
            if price_min and price_max:
                price_range = f"{price_min}-{price_max}"
            elif price_min and not price_max:
                price_range = f"Більше {price_min}"
            elif not price_min and price_max:
                price_range = f"До {price_max}"
            else:
                price_range = "Не важливо"

            summary = (
                f"**Обрані параметри пошуку:**\n"
                f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
                f"🏙️ Місто: {city}\n"
                f"🛏️ Кількість кімнат: {rooms}\n"
                f"💰 Діапазон цін: {price_range} грн.\n"
            )

            # Create options for the confirmation
            options = [
                {"text": "Розширений пошук", "value": "advanced_search"},
                {"text": "Редагувати", "value": "edit_parameters"},
                {"text": "Підписатися", "value": "subscribe"},
            ]

            await safe_send_menu(
                user_id=user_id, text=summary, options=options, platform=platform
            )

            logger.info(
                "Subscription confirmation displayed",
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "property_type": property_type,
                    "city": city,
                    "rooms": rooms,
                    "price_range": price_range,
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Error showing subscription confirmation",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            return False


@log_operation("process_subscription")
async def process_subscription(
    user_id: Union[str, int], user_data: Dict[str, Any], platform: str = None
):
    """
    Process subscription submission across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        user_data: Dictionary with user's filter data
        platform: Optional platform identifier
    """
    with log_context(logger, user_id=user_id, platform=platform):
        try:
            # Get database user ID
            db_user_id, _, _ = resolve_user_id(user_id, platform)

            if not db_user_id:
                logger.warning(
                    "Failed to resolve user ID",
                    extra={"user_id": user_id, "platform": platform},
                )
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося визначити вашого користувача.",
                    platform=platform,
                )
                return False

            # Prepare filters
            filters = {
                "property_type": user_data.get("property_type"),
                "city": user_data.get("city"),
                "rooms": user_data.get("rooms"),
                "price_min": user_data.get("price_min"),
                "price_max": user_data.get("price_max"),
            }

            # Save to database
            update_user_filter(db_user_id, filters)

            # Send confirmation message
            await safe_send_message(
                user_id=user_id,
                text="Ви успішно підписалися на пошук оголошень!",
                platform=platform,
            )

            # Send additional message about notifications
            await safe_send_message(
                user_id=user_id,
                text="Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!",
                platform=platform,
            )

            logger.info(
                "Subscription processed successfully",
                extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id,
                    "platform": platform,
                    "filters": filters,
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Error updating user filters",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            await safe_send_message(
                user_id=user_id,
                text="Помилка при збереженні фільтрів. Спробуйте ще раз.",
                platform=platform,
            )
            return False


@log_operation("handle_favorite_action")
async def handle_favorite_action(
    user_id: Union[str, int], action: str, ad_id: int, platform: str = None
):
    """
    Handle adding or removing favorite ads across all messaging platforms.

    Args:
        user_id: User's platform-specific ID or database ID
        action: Action to perform ('add' or 'remove')
        ad_id: ID of the ad
        platform: Optional platform identifier
    """
    with log_context(
        logger, user_id=user_id, action=action, ad_id=ad_id, platform=platform
    ):
        try:
            # Get database user ID
            db_user_id, _, _ = resolve_user_id(user_id, platform)

            if not db_user_id:
                logger.warning(
                    "Failed to resolve user ID",
                    extra={"user_id": user_id, "platform": platform},
                )
                await safe_send_message(
                    user_id,
                    "Помилка: Не вдалося визначити вашого користувача.",
                    platform=platform,
                )
                return False

            if action == "add":
                add_favorite_ad(db_user_id, ad_id)
                await safe_send_message(
                    user_id, "Оголошення додано до обраних!", platform=platform
                )
                logger.info(
                    "Ad added to favorites",
                    extra={
                        "user_id": user_id,
                        "db_user_id": db_user_id,
                        "ad_id": ad_id,
                        "platform": platform,
                    },
                )
            elif action == "remove":
                remove_favorite_ad(db_user_id, ad_id)
                await safe_send_message(
                    user_id, "Оголошення видалено з обраних!", platform=platform
                )
                logger.info(
                    "Ad removed from favorites",
                    extra={
                        "user_id": user_id,
                        "db_user_id": db_user_id,
                        "ad_id": ad_id,
                        "platform": platform,
                    },
                )

            return True

        except Exception as e:
            logger.error(
                "Error handling favorite action",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "action": action,
                    "ad_id": ad_id,
                    "platform": platform,
                    "error_type": type(e).__name__,
                },
            )
            await safe_send_message(user_id, f"Помилка: {str(e)}", platform=platform)
            return False
