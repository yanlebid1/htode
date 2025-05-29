# services/telegram_service/app/handlers/basic_handlers.py

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import ParseMode
from aiogram.types import InlineKeyboardButton

from ..bot import dp
from ..states.basis_states import FilterStates
from ..keyboards import (
    property_type_keyboard, city_keyboard, rooms_keyboard,
    price_keyboard, confirmation_keyboard,
    edit_parameters_keyboard, floor_keyboard,
    main_menu_keyboard
)
from common.db.operations import get_or_create_user, get_db_user_id_by_telegram_id
from ..utils.message_utils import (
    safe_send_message, safe_answer_callback_query,
    safe_edit_message, delete_message_safe
)

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context

# Список доступних міст (можна отримати з бази даних або конфігурації)
AVAILABLE_CITIES = ['Івано-Франківськ', 'Вінниця', 'Дніпро', 'Житомир', 'Запоріжжя', 'Київ', 'Кропивницький', 'Луцьк',
                    'Львів', 'Миколаїв', 'Одеса', 'Полтава', 'Рівне', 'Суми', 'Тернопіль', 'Ужгород', 'Харків',
                    'Херсон', 'Хмельницький', 'Черкаси', 'Чернівці']


@dp.message_handler(commands=['start'])
@log_operation("start_command")
async def start_command(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id, username=message.from_user.username):
        user_db_id = get_or_create_user(telegram_id)
        logger.info("Start command received", extra={
            "telegram_id": telegram_id,
            "user_db_id": user_db_id,
            "username": message.from_user.username
        })

        # Use safe_send_message to send welcome
        await safe_send_message(
            chat_id=telegram_id,
            text="Привіт!👋 Я бот з пошуку оголошень.\n"
                 "Зі мною легко і швидко знайти квартиру для оренди.\n"
                 "У тебе зараз активний безкоштовний період 7 днів.\n"
                 "Давайте налаштуємо твої параметри пошуку.\n"
                 "Оберіть місто:",
        )
        city_msg = await safe_send_message(
            chat_id=telegram_id,
            text="🏙️ Оберіть місто:",
            reply_markup=city_keyboard(AVAILABLE_CITIES, page=0)
        )
        if city_msg:
            await state.update_data(city_panel_msg_id=city_msg.message_id, city_panel_page=0)
        await FilterStates.waiting_for_city.set()
        logger.info("User started conversation", extra={
            "telegram_id": telegram_id,
            "db_id": user_db_id,
            "new_state": "waiting_for_city"
        })


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_') and not c.data.startswith('city_page_'), state=FilterStates.waiting_for_city)
@log_operation("process_city")
async def process_city(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    city = callback_query.data.split('_', 1)[1]
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')
    city_panel_msg_id = user_data.get('city_panel_msg_id')

    # If we don't have it in state, get it from database
    if not user_db_id:
        user_db_id = get_db_user_id_by_telegram_id(telegram_id)

    with log_context(logger, telegram_id=telegram_id, city=city):
        if city not in AVAILABLE_CITIES:
            logger.warning("Invalid city selected", extra={
                "telegram_id": telegram_id,
                "city": city,
                "available_cities": AVAILABLE_CITIES
            })
            await safe_send_message(
                chat_id=telegram_id,
                text="Будь ласка, оберіть місто зі списку."
            )
            return

        await state.update_data(city=city)
        logger.info("City selected", extra={
            "telegram_id": telegram_id,
            "city": city
        })

        # Check if we are editing city via edit menu
        current_edit = (await state.get_data()).get("current_edit")

        if current_edit == "city":
            # Delete the selection panel message (current callback message)
            await delete_message_safe(telegram_id, callback_query.message.message_id)
            await state.update_data(city_panel_msg_id=None)

            await safe_send_message(
                chat_id=telegram_id,
                text="Місто оновлено."
            )

            await safe_send_message(
                chat_id=telegram_id,
                text="Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )

            await state.update_data(current_edit=None)
            await FilterStates.waiting_for_confirmation.set()
            await safe_answer_callback_query(callback_query.id)
            return

        # Not in edit mode – continue usual flow

        # Delete city selection panel
        if city_panel_msg_id:
            await delete_message_safe(telegram_id, city_panel_msg_id)

        # Show confirmation and proceed
        await safe_send_message(
            chat_id=telegram_id,
            text=f"Місто {city} обрано."
        )
        rooms_msg = await safe_send_message(
            chat_id=telegram_id,
            text="🛏️ Виберіть кількість кімнат (можна обрати декілька):",
            reply_markup=rooms_keyboard(show_back=False, show_save=False)
        )
        if rooms_msg:
            await state.update_data(rooms_panel_msg_id=rooms_msg.message_id)
        await FilterStates.waiting_for_rooms.set()
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rooms_'), state=FilterStates.waiting_for_rooms)
@log_operation("process_rooms")
async def process_rooms(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    data = callback_query.data
    user_data = await state.get_data()
    city = user_data.get('city')
    selected_rooms = user_data.get('rooms', [])

    with log_context(logger, telegram_id=telegram_id, callback_data=data, selected_rooms=selected_rooms):
        # Get the database user ID from state
        user_data = await state.get_data()
        user_db_id = user_data.get('user_db_id')

        # If we don't have it in state, get it from database
        if not user_db_id:
            user_db_id = get_db_user_id_by_telegram_id(telegram_id)

        if data == 'rooms_done':
            if not selected_rooms:
                logger.warning("No rooms selected on done", extra={
                    "telegram_id": telegram_id
                })

                await safe_send_message(
                    chat_id=telegram_id,
                    text="Ви не обрали кількість кімнат."
                )
                return

            logger.info("Rooms selection completed", extra={
                "telegram_id": telegram_id,
                "selected_rooms": selected_rooms
            })

            # Check if we are editing rooms via edit menu or initial flow
            current_edit = (await state.get_data()).get("current_edit")

            if current_edit == "rooms":
                # Delete the rooms keyboard panel message
                await delete_message_safe(telegram_id, callback_query.message.message_id)
                await state.update_data(rooms_panel_msg_id=None)

                await safe_send_message(
                    chat_id=telegram_id,
                    text="Кількість кімнат оновлено."
                )

                await safe_send_message(
                    chat_id=telegram_id,
                    text="Оберіть параметр для редагування:",
                    reply_markup=edit_parameters_keyboard()
                )

                await state.update_data(current_edit=None)
                await FilterStates.waiting_for_confirmation.set()
                await safe_answer_callback_query(callback_query.id)
            else:
                # Delete rooms panel message
                await delete_message_safe(telegram_id, callback_query.message.message_id)
                await state.update_data(rooms_panel_msg_id=None)

                rooms_text = ', '.join('5+' if int(r)==5 else str(r) for r in selected_rooms)
                await safe_send_message(
                    chat_id=telegram_id,
                    text=f"Кількість кімнат: {rooms_text}"
                )

                price_msg = await safe_send_message(
                    chat_id=telegram_id,
                    text="💰 Виберіть діапазон цін (грн):",
                    reply_markup=price_keyboard(city=city)
                )
                if price_msg:
                    await state.update_data(price_panel_msg_id=price_msg.message_id)

                await FilterStates.waiting_for_price.set()
                await safe_answer_callback_query(callback_query.id)

        elif data == 'rooms_any':
            await state.update_data(rooms=None)
            logger.info("Any rooms selected", extra={
                "telegram_id": telegram_id
            })

            # Delete rooms panel
            rooms_panel_msg_id = user_data.get('rooms_panel_msg_id')
            if rooms_panel_msg_id:
                await delete_message_safe(telegram_id, rooms_panel_msg_id)

            await safe_send_message(
                chat_id=telegram_id,
                text="Кількість кімнат: Будь-яка"
            )

            price_msg = await safe_send_message(
                chat_id=telegram_id,
                text="💰 Виберіть діапазон цін (грн):",
                reply_markup=price_keyboard(city=city)
            )
            if price_msg:
                await state.update_data(price_panel_msg_id=price_msg.message_id)
            await FilterStates.waiting_for_price.set()
            await safe_answer_callback_query(callback_query.id)

        elif data.startswith('rooms_'):
            try:
                rooms_number = int(data.split('_')[1])
                if rooms_number in selected_rooms:
                    selected_rooms.remove(rooms_number)
                    logger.info("Room deselected", extra={
                        "telegram_id": telegram_id,
                        "room_number": rooms_number,
                        "selected_rooms": selected_rooms
                    })
                else:
                    selected_rooms.append(rooms_number)
                    logger.info("Room selected", extra={
                        "telegram_id": telegram_id,
                        "room_number": rooms_number,
                        "selected_rooms": selected_rooms
                    })

                await state.update_data(rooms=selected_rooms)

                # Use safe_edit_message_reply_markup instead
                await safe_edit_message(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    text=callback_query.message.text,
                    reply_markup=rooms_keyboard(selected_rooms)
                )
                await safe_answer_callback_query(callback_query.id)
            except (IndexError, ValueError) as e:
                logger.error("Error processing room selection", exc_info=True, extra={
                    "telegram_id": telegram_id,
                    "callback_data": data,
                    "error": str(e)
                })
                await safe_send_message(
                    chat_id=telegram_id,
                    text="Виникла помилка при виборі кількості кімнат."
                )
                await safe_answer_callback_query(callback_query.id)
        else:
            logger.warning("Unknown room command", extra={
                "telegram_id": telegram_id,
                "callback_data": data
            })
            await safe_send_message(
                chat_id=telegram_id,
                text="Невідома команда."
            )
            await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('price_'), state=FilterStates.waiting_for_price)
@log_operation("process_price")
async def process_price(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    # Get the database user ID from state
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')

    # If we don't have it in state, get it from database
    if not user_db_id:
        user_db_id = get_db_user_id_by_telegram_id(telegram_id)

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        # callback_query.data might look like "price_0_5000" or "price_5000_7000" or "price_15000_any"
        parts = callback_query.data.split("_")
        if len(parts) == 3 and parts[2] == "any":
            low = int(parts[1])  # 15000
            high = None
        else:
            low = int(parts[1])
            high = int(parts[2])

        text_range = f"{low}+ грн." if not high else f"{low}–{high} грн."

        logger.info("Price range selected", extra={
            "telegram_id": telegram_id,
            "price_min": low,
            "price_max": high,
            "price_range_text": text_range
        })

        # Check if we are in edit mode
        current_edit = (await state.get_data()).get("current_edit")
        if current_edit == "price":
            # Delete the price keyboard panel message
            await delete_message_safe(telegram_id, callback_query.message.message_id)
            await state.update_data(price_panel_msg_id=None)

            await safe_send_message(
                chat_id=telegram_id,
                text="Діапазон цін оновлено."
            )

            await safe_send_message(
                chat_id=telegram_id,
                text="Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )

            await state.update_data(current_edit=None)
            await FilterStates.waiting_for_confirmation.set()
            await safe_answer_callback_query(callback_query.id)
            return

        # Delete price panel
        price_panel_msg_id = user_data.get('price_panel_msg_id')
        if price_panel_msg_id:
            await delete_message_safe(telegram_id, price_panel_msg_id)

        await safe_send_message(
            chat_id=telegram_id,
            text=f"Ви обрали діапазон: {text_range}"
        )

        await state.update_data(price_min=low, price_max=high)

        # Instead of waiting for a new button press, call the "process_basic_params"
        # function directly, so it shows the summary + confirmation buttons.
        await process_basic_params(callback_query, state)

        # Mark it done, so we are now in waiting_for_confirmation
        # (Inside process_basic_params you set waiting_for_confirmation,
        #  so no need to set it again here.)
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('edit_') and c.data != 'edit_parameters', state=FilterStates.waiting_for_confirmation)
@log_operation("handle_edit")
async def handle_edit(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    edit_field = callback_query.data.split('_', 1)[1]
    user_data = await state.get_data()
    city = user_data.get('city')
    # Get the database user ID from state
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')

    # If we don't have it in state, get it from database
    if not user_db_id:
        user_db_id = get_db_user_id_by_telegram_id(telegram_id)

    with log_context(logger, telegram_id=telegram_id, edit_field=edit_field):
        logger.info("Editing parameter", extra={
            "telegram_id": telegram_id,
            "edit_field": edit_field,
            "current_data": user_data
        })

        # Remove current parameter menu panel
        await delete_message_safe(telegram_id, callback_query.message.message_id)

        # Mark current_edit for following handlers
        await state.update_data(current_edit=edit_field)

        if edit_field == "city":
            edit_mode = (await state.get_data()).get("current_edit") == "city"
            selected_city_value = user_data.get('city')
            kb_city = city_keyboard(AVAILABLE_CITIES, page=0, show_back=edit_mode, show_save=edit_mode, selected_city=selected_city_value)

            city_msg = await safe_send_message(
                chat_id=telegram_id,
                text="🏙️ Оберіть місто:",
                reply_markup=kb_city
            )
            if city_msg:
                await state.update_data(city_panel_msg_id=city_msg.message_id, city_panel_page=0)
            await FilterStates.waiting_for_city.set()
        elif edit_field == "rooms":
            user_data = await state.get_data()
            selected_rooms = user_data.get('rooms', [])
            rooms_msg = await safe_send_message(
                chat_id=telegram_id,
                text="🛏️ Виберіть кількість кімнат (можна вибрати декілька):",
                reply_markup=rooms_keyboard(selected_rooms, show_back=True, show_save=True)
            )
            if rooms_msg:
                await state.update_data(rooms_panel_msg_id=rooms_msg.message_id)
            await FilterStates.waiting_for_rooms.set()
        elif edit_field == "price":
            price_msg = await safe_send_message(
                chat_id=telegram_id,
                text="💰 Виберіть діапазон цін (грн):",
                reply_markup=price_keyboard(city=city)
            )
            if price_msg:
                await state.update_data(price_panel_msg_id=price_msg.message_id)
            await FilterStates.waiting_for_price.set()
        elif edit_field == "floor":
            # call your function to handle floor editing
            await safe_send_message(
                chat_id=telegram_id,
                text="🏢 Налаштуйте поверх:",
                reply_markup=floor_keyboard()
            )
            # optionally change state, etc.
        elif edit_field == "cancel_edit":
            await safe_send_message(
                chat_id=telegram_id,
                text="Редагування скасовано.",
                reply_markup=edit_parameters_keyboard()
            )
            await FilterStates.waiting_for_confirmation.set()
        else:
            logger.warning("Unknown edit parameter", extra={
                "telegram_id": telegram_id,
                "edit_field": edit_field
            })
            await safe_send_message(
                chat_id=telegram_id,
                text="Невідомий параметр редагування."
            )

        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('confirmation_'),
                           state=FilterStates.waiting_for_basic_params)
@log_operation("process_basic_params")
async def process_basic_params(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    # Get the database user ID from state
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')

    # If we don't have it in state, get it from database
    if not user_db_id:
        user_db_id = get_db_user_id_by_telegram_id(telegram_id)

    with log_context(logger, telegram_id=telegram_id):
        # Получение всех данных из состояния
        user_data = await state.get_data()
        property_type = user_data.get('property_type')
        mapping_property = {"apartment": "Квартира", "house": "Будинок"}
        ua_lang_property_type = mapping_property.get(property_type, "")
        if not ua_lang_property_type:
            ua_lang_property_type = "Квартира"  # Default to apartment when unspecified

        city = user_data.get('city')
        rooms = ', '.join('5+' if int(r)==5 else str(r) for r in user_data.get('rooms')) if user_data.get('rooms') else 'Не важливо'

        # Определение диапазона цен
        price_min = user_data.get('price_min')
        price_max = user_data.get('price_max')
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

        logger.info("Showing search parameters summary", extra={
            "telegram_id": telegram_id,
            "property_type": property_type,
            "city": city,
            "rooms": rooms,
            "price_min": price_min,
            "price_max": price_max
        })

        # Екранування спеціальних символів у повідомленні Markdown
        from aiogram.utils.markdown import escape_md
        summary_escaped = escape_md(summary).replace('\\', '')

        await safe_send_message(
            chat_id=telegram_id,
            text=summary_escaped,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=confirmation_keyboard()
        )
        await FilterStates.waiting_for_confirmation.set()
        await safe_answer_callback_query(callback_query.id)


@dp.message_handler(lambda msg: msg.text == "📝 Мої підписки", state=None)
@log_operation("forward_to_subscriptions")
async def forward_to_subscriptions(message: types.Message, state: FSMContext):
    """Forward subscriptions button to the proper handler"""
    from .subscription import show_subscriptions_menu
    logger.info("Forwarding to subscriptions menu", extra={
        "telegram_id": message.from_user.id,
        "message_text": message.text
    })
    await show_subscriptions_menu(message)


@dp.callback_query_handler(Text(startswith="edit_parameters"), state=FilterStates.waiting_for_confirmation)
@log_operation("edit_parameters")
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    # Get the database user ID from state
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')

    # If we don't have it in state, get it from database
    if not user_db_id:
        user_db_id = get_db_user_id_by_telegram_id(telegram_id)

    with log_context(logger, telegram_id=telegram_id):
        logger.info("User requested to edit parameters", extra={
            "telegram_id": telegram_id
        })

        # delete summary panel
        await delete_message_safe(telegram_id, callback_query.message.message_id)

        await safe_send_message(
            chat_id=telegram_id,
            text="Оберіть параметр для редагування:",
            reply_markup=edit_parameters_keyboard()
        )
        await safe_answer_callback_query(callback_query.id)


@dp.message_handler(lambda message: message.text != "❤️ Обрані", content_types=['text'], state=None)
@log_operation("debug_all_messages")
async def debug_all_messages(message: types.Message, state: FSMContext):
    """Debug handler that logs all text messages when not in any state, except favorites"""
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id, message_text=message.text):
        logger.info("Received message without state", extra={
            "telegram_id": telegram_id,
            "message_text": message.text,
            "username": message.from_user.username
        })

        # If the message is /start, try to respond directly
        if message.text == '/start':
            try:
                await start_command(message, state)
            except Exception as e:
                logger.error("Error handling /start in debug handler", exc_info=True, extra={
                    "telegram_id": telegram_id,
                    "error": str(e)
                })
                await message.answer(f"Error in start command: {str(e)}")
        elif message.text == '/menu':
            await show_main_menu(message)
        elif message.text == "📱 Додати номер телефону":
            from .phone_verification import start_phone_verification
            await start_phone_verification(message, state)
        elif message.text == "💳 Оплатити підписку":
            from .payment import payment_handler
            await payment_handler(message)
        elif message.text == "🧑‍💻 Техпідтримка":
            from .support import handle_support_command_telegram
            await handle_support_command_telegram(message, state)


@dp.message_handler(commands=['menu'])
@log_operation("show_main_menu")
async def show_main_menu(message: types.Message):
    """
    Sends the main menu keyboard when the user uses /menu.
    """
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id):
        logger.info("Showing main menu", extra={
            "telegram_id": telegram_id,
            "username": message.from_user.username
        })

        await safe_send_message(
            chat_id=message.from_user.id,
            text="Головне меню:",
            reply_markup=main_menu_keyboard()
        )


@dp.message_handler(lambda msg: msg.text == "❤️ Обрані", state=None)
@log_operation("forward_to_favorites")
async def forward_to_favorites(message: types.Message, state: FSMContext):
    """Forward favorites button to the proper handler"""
    from .favorites import show_favorites_carousel
    await show_favorites_carousel(message, state)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_page_'), state=FilterStates.waiting_for_city)
@log_operation("city_page_navigation")
async def city_page_navigation(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    user_data = await state.get_data()
    page = int(callback_query.data.split('_')[-1])
    msg_id = user_data.get('city_panel_msg_id') or callback_query.message.message_id
    edit_mode = (await state.get_data()).get("current_edit") == "city"
    selected_city_val = user_data.get('city')
    kb_city = city_keyboard(AVAILABLE_CITIES, page=page, show_back=edit_mode, show_save=edit_mode, selected_city=selected_city_val)
    await safe_edit_message(
        chat_id=telegram_id,
        message_id=msg_id,
        text="🏙️ Оберіть місто:",
        reply_markup=kb_city
    )
    await state.update_data(city_panel_page=page, city_panel_msg_id=msg_id)
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_edit", state=[FilterStates.waiting_for_city, FilterStates.waiting_for_rooms])
@log_operation("cancel_edit_any")
async def cancel_edit_any_handler(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    await delete_message_safe(telegram_id, callback_query.message.message_id)
    await safe_send_message(chat_id=telegram_id, text="Оберіть параметр для редагування:", reply_markup=edit_parameters_keyboard())
    await state.update_data(current_edit=None)
    await FilterStates.waiting_for_confirmation.set()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == "city_save", state=FilterStates.waiting_for_city)
@log_operation("city_save")
async def city_save_handler(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    data = await state.get_data()
    city = data.get("city")
    # delete panel
    await delete_message_safe(telegram_id, callback_query.message.message_id)
    await safe_send_message(chat_id=telegram_id, text=f"Місто оновлено: {city}")
    await safe_send_message(chat_id=telegram_id, text="Оберіть параметр для редагування:", reply_markup=edit_parameters_keyboard())
    await state.update_data(current_edit=None)
    await FilterStates.waiting_for_confirmation.set()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == "rooms_save", state=FilterStates.waiting_for_rooms)
@log_operation("rooms_save")
async def rooms_save_handler(callback_query: types.CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    data = await state.get_data()
    rooms = data.get("rooms", [])
    rooms_text = ", ".join("5+" if int(r)==5 else str(r) for r in rooms)
    # delete panel
    await delete_message_safe(telegram_id, callback_query.message.message_id)
    await safe_send_message(chat_id=telegram_id, text=f"Кількість кімнат оновлено: {rooms_text}")
    await safe_send_message(chat_id=telegram_id, text="Оберіть параметр для редагування:", reply_markup=edit_parameters_keyboard())
    await state.update_data(current_edit=None)
    await FilterStates.waiting_for_confirmation.set()
    await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == "cancel_edit", state=FilterStates.waiting_for_confirmation)
@log_operation("cancel_edit_main")
async def cancel_edit_main_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """Back from edit menu to summary panel"""
    telegram_id = callback_query.from_user.id
    # Delete current edit menu message
    await delete_message_safe(telegram_id, callback_query.message.message_id)

    data = await state.get_data()
    # Build summary (reuse logic from process_basic_params)
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    ua_lang_property_type = mapping_property.get(data.get("property_type"), "Квартира")

    city = data.get("city")
    rooms_text = ", ".join("5+" if int(r)==5 else str(r) for r in data.get("rooms", [])) if data.get("rooms") else "Не важливо"
    price_min = data.get("price_min")
    price_max = data.get("price_max")
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
        f"🛏️ Кількість кімнат: {rooms_text}\n"
        f"💰 Діапазон цін: {price_range} грн.\n"
    )
    from aiogram.utils.markdown import escape_md
    await safe_send_message(
        chat_id=telegram_id,
        text=escape_md(summary).replace('\\', ''),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirmation_keyboard()
    )
    await state.update_data(current_edit=None)
    await FilterStates.waiting_for_confirmation.set()
    await safe_answer_callback_query(callback_query.id)
