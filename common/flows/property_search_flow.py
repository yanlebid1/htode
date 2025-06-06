# common/flows/property_search_flow.py

import logging
from common.db.operations import (
    update_user_filter,
    get_or_create_user,
    get_db_user_id_by_telegram_id
)
from common.celery_app import celery_app
from common.messaging.unified_flow import MessageFlow, FlowContext, flow_library
from common.utils.logging_config import log_operation, log_context

# Import the flows logger
from . import logger

# Create property search flow
property_search_flow = MessageFlow(
    name="property_search",
    initial_state="start",
    description="Flow for searching properties and setting up subscriptions"
)

# List of available cities (reused across platforms)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


# Helper functions
@log_operation("format_price_range")
def format_price_range(price_min, price_max):
    """Format price range for display"""
    with log_context(logger, price_min=price_min, price_max=price_max):
        if price_min and price_max:
            return f"{price_min}–{price_max} грн."
        elif price_min and not price_max:
            return f"Більше {price_min} грн."
        elif not price_min and price_max:
            return f"До {price_max} грн."
        else:
            return "Не важливо"


@log_operation("format_rooms")
def format_rooms(rooms):
    """Format rooms for display"""
    with log_context(logger, rooms=rooms):
        if not rooms:
            return "Не важливо"
        return ", ".join(map(str, rooms))


@log_operation("get_price_ranges")
def get_price_ranges(city):
    """Get appropriate price ranges based on city size"""
    with log_context(logger, city=city):
        # Group cities by size for price ranges
        big_cities = {'Київ'}
        medium_cities = {'Харків', 'Дніпро', 'Одеса', 'Львів'}

        if city in big_cities:
            return [(0, 15000), (15000, 20000), (20000, 30000), (30000, None)]
        elif city in medium_cities:
            return [(0, 7000), (7000, 10000), (10000, 15000), (15000, None)]
        else:
            return [(0, 5000), (5000, 7000), (7000, 10000), (10000, None)]


# State handlers
@log_operation("start_property_search")
async def start_property_search(context: FlowContext):
    """Start the property search flow by showing property type options"""
    with log_context(logger, user_id=context.user_id, platform=context.platform):
        # Try to get user database ID from platform ID
        user_id = context.user_id
        platform = context.platform

        db_user_id = get_db_user_id_by_telegram_id(user_id, messenger_type=platform)
        if not db_user_id:
            # Create a new user if not found
            db_user_id = get_or_create_user(user_id, messenger_type=platform)

        logger.info("Starting property search flow", extra={
            'user_id': user_id,
            'platform': platform,
            'db_user_id': db_user_id
        })

        # Store user_db_id in flow context for later use
        context.update(user_db_id=db_user_id)

        await context.send_message(
            "Привіт!👋 Я бот з пошуку оголошень.\n"
            "Зі мною легко і швидко знайти квартиру, будинок або кімнату для оренди.\n"
            "У тебе зараз активний безкоштовний період 7 днів.\n"
            "Давайте налаштуємо твої параметри пошуку.\n"
            "Обери те, що тебе цікавить:\n"
        )

        # Send property type options in a platform-appropriate way
        options = [
            {"text": "Квартира", "value": "apartment"},
            {"text": "Будинок", "value": "house"}
        ]

        await context.send_menu(
            text="🏷 Оберіть тип нерухомості:",
            options=options
        )


@log_operation("handle_property_type")
async def handle_property_type(context: FlowContext):
    """Handle property type selection"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        message = context.message.lower()

        # Map common inputs to property type
        property_mapping = {
            "apartment": "apartment",
            "house": "house",
            "квартира": "apartment",
            "будинок": "house",
            "1": "apartment",
            "2": "house"
        }

        if message in property_mapping:
            property_type = property_mapping[message]
            logger.info("Property type selected", extra={
                'property_type': property_type,
                'user_id': context.user_id
            })

            # Store the selected property type
            context.update(property_type=property_type)

            # Move to city selection
            await context.send_message("🏙️ Оберіть місто:")

            # Create menu options for cities
            city_options = []
            for city in AVAILABLE_CITIES[:10]:  # Limit to first 10 cities to avoid too many options
                city_options.append({"text": city, "value": city})

            # Add option to enter a custom city
            city_options.append({"text": "Інше місто", "value": "other_city"})

            await context.send_menu(
                text="Оберіть місто зі списку або введіть назву:",
                options=city_options
            )
        else:
            logger.warning("Invalid property type input", extra={
                'user_id': context.user_id,
                'message': message
            })
            # Invalid input
            await context.send_message(
                "Невідомий тип нерухомості. Будь ласка, оберіть 'Квартира' або 'Будинок'."
            )


@log_operation("handle_city")
async def handle_city(context: FlowContext):
    """Handle city selection"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        city = context.message

        # Check if this is a numeric input (for WhatsApp)
        if city.isdigit():
            index = int(city) - 1
            if 0 <= index < len(AVAILABLE_CITIES):
                city = AVAILABLE_CITIES[index]
            else:
                logger.warning("Invalid city index", extra={
                    'user_id': context.user_id,
                    'index': index,
                    'max_index': len(AVAILABLE_CITIES) - 1
                })
                await context.send_message("Невірний номер міста. Будь ласка, оберіть зі списку.")
                return

        # Check if city is valid
        if city == "other_city":
            # Ask for custom city
            logger.debug("User requesting custom city input", extra={'user_id': context.user_id})
            await context.send_message(
                "Будь ласка, введіть назву міста:"
            )
            context.update(awaiting_custom_city=True)
            return

        # Check if city is in the list or handle custom city input
        if context.data.get("awaiting_custom_city") or city in AVAILABLE_CITIES:
            # Store selected city
            context.update(city=city, awaiting_custom_city=False)

            logger.info("City selected", extra={
                'user_id': context.user_id,
                'city': city,
                'was_custom': context.data.get("awaiting_custom_city", False)
            })

            # Move to rooms selection
            await context.send_message(
                "🛏️ Виберіть кількість кімнат:"
            )

            # Create options for rooms
            room_options = []
            for i in range(1, 6):
                room_options.append({"text": f"{i}", "value": f"room_{i}"})

            # Add options for multiple or any rooms
            room_options.append({"text": "Вказати декілька", "value": "multiple_rooms"})
            room_options.append({"text": "Будь-яка кількість", "value": "any_rooms"})

            await context.send_menu(
                text="Оберіть кількість кімнат:",
                options=room_options
            )
        else:
            # Invalid city
            logger.warning("Invalid city input", extra={
                'user_id': context.user_id,
                'city': city
            })
            await context.send_message(
                "Місто не знайдено. Будь ласка, оберіть місто зі списку або введіть коректну назву."
            )


@log_operation("handle_rooms")
async def handle_rooms(context: FlowContext):
    """Handle rooms selection"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        message = context.message
        selected_rooms = context.data.get('rooms', [])

        if message == "any_rooms":
            # User selected any number of rooms
            context.update(rooms=None)
            logger.info("Rooms selected: any", extra={'user_id': context.user_id})

            # Move to price selection
            await show_price_options(context)
        elif message == "multiple_rooms":
            # User wants to select multiple rooms
            logger.debug("User wants to select multiple rooms", extra={'user_id': context.user_id})
            await context.send_message(
                "Введіть кількість кімнат через кому (наприклад: 1,2,3):"
            )
            context.update(awaiting_multiple_rooms=True)
        elif message.startswith("room_"):
            # User selected a single room
            try:
                room_number = int(message.split("_")[1])
                context.update(rooms=[room_number])
                logger.info("Single room selected", extra={
                    'user_id': context.user_id,
                    'room_number': room_number
                })

                # Move to price selection
                await show_price_options(context)
            except (ValueError, IndexError):
                logger.error("Invalid room format", extra={
                    'user_id': context.user_id,
                    'message': message
                })
                await context.send_message("Невірний формат вибору кімнат.")
        elif context.data.get("awaiting_multiple_rooms"):
            # User is entering multiple rooms
            try:
                # Parse room numbers from text
                parts = message.replace(",", " ").split()
                room_numbers = [int(part) for part in parts if part.isdigit() and 1 <= int(part) <= 5]

                if not room_numbers:
                    raise ValueError("No valid room numbers")

                # Store selected rooms
                context.update(rooms=room_numbers, awaiting_multiple_rooms=False)
                logger.info("Multiple rooms selected", extra={
                    'user_id': context.user_id,
                    'rooms': room_numbers
                })

                # Move to price selection
                await show_price_options(context)
            except ValueError:
                logger.warning("Invalid room input format", extra={
                    'user_id': context.user_id,
                    'message': message
                })
                await context.send_message(
                    "Невірний формат. Введіть числа від 1 до 5, розділені комами."
                )
        else:
            # Try to parse direct number input
            if message.isdigit() and 1 <= int(message) <= 5:
                context.update(rooms=[int(message)])
                logger.info("Direct room number input", extra={
                    'user_id': context.user_id,
                    'room_number': int(message)
                })

                # Move to price selection
                await show_price_options(context)
            else:
                logger.warning("Unknown room selection", extra={
                    'user_id': context.user_id,
                    'message': message
                })
                await context.send_message(
                    "Невідомий вибір кімнат. Будь ласка, використовуйте запропоновані варіанти."
                )


@log_operation("show_price_options")
async def show_price_options(context: FlowContext):
    """Show price range options"""
    with log_context(logger, user_id=context.user_id):
        city = context.data.get("city", "Київ")

        # Get price ranges based on city
        price_ranges = get_price_ranges(city)
        logger.debug("Showing price options", extra={
            'user_id': context.user_id,
            'city': city,
            'ranges_count': len(price_ranges)
        })

        # Create options for price ranges
        price_options = []
        for i, (low, high) in enumerate(price_ranges):
            if high is None:
                label = f"Більше {low} грн."
                value = f"price_{low}_any"
            else:
                if low == 0:
                    label = f"До {high} грн."
                else:
                    label = f"{low}-{high} грн."
                value = f"price_{low}_{high}"

            price_options.append({"text": label, "value": value})

        # Add option for custom price range
        price_options.append({"text": "Вказати свій діапазон", "value": "custom_price"})

        await context.send_menu(
            text="💰 Виберіть діапазон цін (грн):",
            options=price_options
        )


@log_operation("handle_price")
async def handle_price(context: FlowContext):
    """Handle price range selection"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        message = context.message

        if message == "custom_price":
            # User wants to enter custom price range
            logger.debug("User requesting custom price input", extra={'user_id': context.user_id})
            await context.send_message(
                "Введіть мінімальну та максимальну ціну через дефіс (наприклад: 5000-12000).\n"
                "Для встановлення тільки мінімальної ціни, введіть: 5000+\n"
                "Для встановлення тільки максимальної ціни, введіть: -12000"
            )
            context.update(awaiting_custom_price=True)
        elif message.startswith("price_"):
            # User selected predefined price range
            parts = message.split("_")

            try:
                low = int(parts[1])
                high = None if parts[2] == "any" else int(parts[2])

                # Store selected price range
                context.update(
                    price_min=low if low > 0 else None,
                    price_max=high,
                    awaiting_custom_price=False
                )

                logger.info("Price range selected", extra={
                    'user_id': context.user_id,
                    'price_min': low if low > 0 else None,
                    'price_max': high
                })

                # Show confirmation
                await show_confirmation(context)
            except (ValueError, IndexError):
                logger.error("Invalid price format", extra={
                    'user_id': context.user_id,
                    'message': message
                })
                await context.send_message("Невірний формат діапазону цін.")
        elif context.data.get("awaiting_custom_price"):
            # User is entering custom price range
            try:
                # Parse custom price range
                if "+" in message:
                    # Only minimum price
                    min_price = int(message.replace("+", "").strip())
                    max_price = None
                elif message.startswith("-"):
                    # Only maximum price
                    min_price = None
                    max_price = int(message.replace("-", "").strip())
                elif "-" in message:
                    # Both min and max
                    parts = message.split("-")
                    min_price = int(parts[0].strip()) if parts[0].strip() else None
                    max_price = int(parts[1].strip()) if parts[1].strip() else None
                else:
                    # Try to parse as single number (assume it's max)
                    max_price = int(message.strip())
                    min_price = None

                # Store custom price range
                context.update(
                    price_min=min_price,
                    price_max=max_price,
                    awaiting_custom_price=False
                )

                logger.info("Custom price range set", extra={
                    'user_id': context.user_id,
                    'price_min': min_price,
                    'price_max': max_price
                })

                # Show confirmation
                await show_confirmation(context)
            except ValueError:
                logger.warning("Invalid custom price format", extra={
                    'user_id': context.user_id,
                    'message': message
                })
                await context.send_message(
                    "Невірний формат. Введіть числа в форматі min-max, min+, або -max."
                )
        else:
            # Try to parse direct numeric input (for WhatsApp)
            if message.isdigit():
                index = int(message) - 1
                city = context.data.get("city", "Київ")
                price_ranges = get_price_ranges(city)

                if 0 <= index < len(price_ranges):
                    low, high = price_ranges[index]
                    context.update(
                        price_min=low if low > 0 else None,
                        price_max=high
                    )
                    logger.info("Price range selected by index", extra={
                        'user_id': context.user_id,
                        'index': index,
                        'price_min': low if low > 0 else None,
                        'price_max': high
                    })
                    await show_confirmation(context)
                    return

            # If we get here, it's an invalid input
            logger.warning("Unknown price input format", extra={
                'user_id': context.user_id,
                'message': message
            })
            await context.send_message(
                "Невідомий формат діапазону цін. Використовуйте запропоновані варіанти."
            )


@log_operation("show_confirmation")
async def show_confirmation(context: FlowContext):
    """Show subscription confirmation"""
    with log_context(logger, user_id=context.user_id):
        # Get all parameters
        property_type = context.data.get("property_type", "")
        city = context.data.get("city", "")
        rooms = context.data.get("rooms", [])
        price_min = context.data.get("price_min")
        price_max = context.data.get("price_max")

        logger.debug("Showing confirmation", extra={
            'user_id': context.user_id,
            'property_type': property_type,
            'city': city,
            'rooms': rooms,
            'price_min': price_min,
            'price_max': price_max
        })

        # Format for display
        mapping_property = {"apartment": "Квартира", "house": "Будинок"}
        ua_lang_property_type = mapping_property.get(property_type, "")

        rooms_display = format_rooms(rooms)
        price_range = format_price_range(price_min, price_max)

        summary = (
            "*Обрані параметри пошуку:*\n\n"
            f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
            f"🏙️ Місто: {city}\n"
            f"🛏️ Кількість кімнат: {rooms_display}\n"
            f"💰 Діапазон цін: {price_range}\n\n"
        )

        # Create confirmation options
        options = [
            {"text": "Підписатися", "value": "confirm_subscription"},
            {"text": "Редагувати", "value": "edit_parameters"},
            {"text": "Скасувати", "value": "cancel_subscription"}
        ]

        await context.send_message(summary)
        await context.send_menu(
            text="Підтвердіть вибір або змініть параметри:",
            options=options
        )


@log_operation("handle_confirmation")
async def handle_confirmation(context: FlowContext):
    """Handle subscription confirmation"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        message = context.message

        if message == "confirm_subscription":
            logger.info("User confirmed subscription", extra={'user_id': context.user_id})
            # Save subscription
            await save_subscription(context)
        elif message == "edit_parameters":
            logger.info("User wants to edit parameters", extra={'user_id': context.user_id})
            # Show parameter editing options
            await show_edit_options(context)
        elif message == "cancel_subscription":
            logger.info("User canceled subscription", extra={'user_id': context.user_id})
            # Cancel subscription
            await context.send_message("Налаштування підписки скасовано.")
            # End the flow
            await flow_library.end_active_flow(context.user_id, context.platform)
        else:
            logger.warning("Unknown confirmation action", extra={
                'user_id': context.user_id,
                'message': message
            })
            # Unknown command
            await context.send_message(
                "Будь ласка, виберіть один з варіантів: Підписатися, Редагувати, або Скасувати."
            )


@log_operation("show_edit_options")
async def show_edit_options(context: FlowContext):
    """Show parameter editing options"""
    with log_context(logger, user_id=context.user_id):
        logger.debug("Showing edit options", extra={'user_id': context.user_id})

        options = [
            {"text": "Тип нерухомості", "value": "edit_property_type"},
            {"text": "Місто", "value": "edit_city"},
            {"text": "Кількість кімнат", "value": "edit_rooms"},
            {"text": "Діапазон цін", "value": "edit_price"},
            {"text": "Повернутися", "value": "back_to_confirmation"}
        ]

        await context.send_menu(
            text="Оберіть параметр для редагування:",
            options=options
        )


@log_operation("handle_edit_selection")
async def handle_edit_selection(context: FlowContext):
    """Handle edit parameter selection"""
    with log_context(logger, user_id=context.user_id, message=context.message):
        message = context.message

        logger.info("User editing parameter", extra={
            'user_id': context.user_id,
            'parameter': message
        })

        if message == "edit_property_type":
            # Back to property type selection
            await start_property_search(context)
        elif message == "edit_city":
            # Back to city selection
            await context.send_message("🏙️ Оберіть місто:")

            # Get available cities
            city_options = []
            for city in AVAILABLE_CITIES[:10]:
                city_options.append({"text": city, "value": city})

            # Add option to enter a custom city
            city_options.append({"text": "Інше місто", "value": "other_city"})

            await context.send_menu(
                text="Оберіть місто зі списку або введіть назву:",
                options=city_options
            )
        elif message == "edit_rooms":
            # Back to rooms selection
            await context.send_message(
                "🛏️ Виберіть кількість кімнат:"
            )

            # Create options for rooms
            room_options = []
            for i in range(1, 6):
                room_options.append({"text": f"{i}", "value": f"room_{i}"})

            # Add options for multiple or any rooms
            room_options.append({"text": "Вказати декілька", "value": "multiple_rooms"})
            room_options.append({"text": "Будь-яка кількість", "value": "any_rooms"})

            await context.send_menu(
                text="Оберіть кількість кімнат:",
                options=room_options
            )
        elif message == "edit_price":
            # Back to price selection
            await show_price_options(context)
        elif message == "back_to_confirmation":
            # Back to confirmation
            await show_confirmation(context)
        else:
            logger.warning("Unknown edit option", extra={
                'user_id': context.user_id,
                'message': message
            })
            # Unknown option
            await context.send_message(
                "Невідомий параметр. Будь ласка, виберіть один з запропонованих варіантів."
            )
            await show_edit_options(context)


@log_operation("save_subscription")
async def save_subscription(context: FlowContext):
    """Save subscription to database"""
    with log_context(logger, user_id=context.user_id):
        # Get all parameters
        property_type = context.data.get("property_type")
        city = context.data.get("city")
        rooms = context.data.get("rooms")
        price_min = context.data.get("price_min")
        price_max = context.data.get("price_max")

        # Get user database ID
        user_db_id = context.data.get("user_db_id")

        if not user_db_id:
            user_db_id = get_db_user_id_by_telegram_id(context.user_id, messenger_type=context.platform)

        if not user_db_id:
            user_db_id = get_or_create_user(context.user_id, messenger_type=context.platform)
            context.update(user_db_id=user_db_id)

        if not user_db_id:
            logger.error("Failed to determine user ID", extra={'platform_id': context.user_id})
            await context.send_message("Помилка: Не вдалося визначити вашого користувача.")
            return

        # Prepare filters for database
        filters = {
            'property_type': property_type,
            'city': city,
            'rooms': rooms,
            'price_min': price_min,
            'price_max': price_max,
        }

        try:
            logger.info("Saving subscription", extra={
                'user_db_id': user_db_id,
                'filters': filters
            })

            # Save to database
            update_user_filter(user_db_id, filters)

            # Send confirmation
            await context.send_message(
                "✅ Ви успішно підписалися на пошук оголошень!\n\n"
                "Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!"
            )

            # Optional: trigger notification task
            celery_app.send_task(
                'notifier_service.app.tasks.notify_user_with_ads',
                args=[user_db_id, filters]
            )

            logger.info("Subscription saved successfully", extra={
                'user_db_id': user_db_id,
                'filters': filters
            })

            # End the flow
            await flow_library.end_active_flow(context.user_id, context.platform)
        except Exception as e:
            logger.error("Error saving subscription", exc_info=True, extra={
                'user_db_id': user_db_id,
                'filters': filters,
                'error_type': type(e).__name__
            })
            await context.send_message(
                "❌ Помилка при збереженні підписки. Будь ласка, спробуйте ще раз."
            )


# Add states to the flow
property_search_flow.add_state("start", start_property_search)
property_search_flow.add_state("property_type", handle_property_type)
property_search_flow.add_state("city", handle_city)
property_search_flow.add_state("rooms", handle_rooms)
property_search_flow.add_state("price", handle_price)
property_search_flow.add_state("confirmation", handle_confirmation)
property_search_flow.add_state("edit", handle_edit_selection)

# Add transitions
property_search_flow.add_transition("start", "property_type")
property_search_flow.add_transition("property_type", "city")
property_search_flow.add_transition("city", "rooms")
property_search_flow.add_transition("rooms", "price")
property_search_flow.add_transition("price", "confirmation")
property_search_flow.add_transition("confirmation", "edit", lambda msg: msg == "edit_parameters")
property_search_flow.add_transition("edit", "start", lambda msg: msg == "edit_property_type")
property_search_flow.add_transition("edit", "city", lambda msg: msg == "edit_city")
property_search_flow.add_transition("edit", "rooms", lambda msg: msg == "edit_rooms")
property_search_flow.add_transition("edit", "price", lambda msg: msg == "edit_price")
property_search_flow.add_transition("edit", "confirmation", lambda msg: msg == "back_to_confirmation")


# Error handler
@log_operation("property_search_error_handler")
async def property_search_error_handler(context, exception):
    """Handle errors in the property search flow"""
    with log_context(logger, user_id=context.user_id, error_type=type(exception).__name__):
        logger.error("Error in property search flow", exc_info=True, extra={
            'user_id': context.user_id,
            'platform': context.platform,
            'current_state': context.data,
            'error_message': str(exception)
        })

        await context.send_message(
            "⚠️ Сталася помилка при обробці вашого запиту. Будь ласка, спробуйте ще раз."
        )

        # Try to recover by returning to confirmation if possible
        if "property_type" in context.data and "city" in context.data:
            await show_confirmation(context)
        else:
            # Start over if we don't have enough data
            await flow_library.end_active_flow(context.user_id, context.platform)
            await flow_library.start_flow("property_search", context.user_id, context.platform)


property_search_flow.set_error_handler(property_search_error_handler)

# Register the flow
flow_library.register_flow(property_search_flow)