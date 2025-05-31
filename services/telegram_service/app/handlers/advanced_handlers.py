# services/telegram_service/app/handlers/advanced_handlers.py

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import ParseMode, MediaGroup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified
from ..bot import dp, bot
from ..states.basis_states import FilterStates
from ..keyboards import floor_keyboard, edit_parameters_keyboard, city_keyboard
from common.db.operations import get_extra_images

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context


@dp.callback_query_handler(lambda c: c.data == "advanced_search", state=FilterStates.waiting_for_confirmation)
@log_operation("advanced_search")
async def advanced_search_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        await show_advanced_options(callback_query.message, state)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "return_to_advanced_menu", state="*")
@log_operation("return_to_advanced_menu")
async def return_to_advanced_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # Remove the inline keyboard message to keep chat clean
        try:
            await callback_query.message.delete()
        except Exception:
            pass

        user_state = await state.get_data()
        if user_state.get("current_edit"):
            await callback_query.message.answer(
                "Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )
            await state.update_data(current_edit=None, city_panel_msg_id=None, rooms_panel_msg_id=None, price_panel_msg_id=None)
        else:
            await show_advanced_options(callback_query.message, state)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor_max", state="*")
@log_operation("edit_floor_max")
async def edit_floor_max_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        keyboard = InlineKeyboardMarkup(row_width=5)
        floors = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for f in floors:
            keyboard.insert(InlineKeyboardButton(str(f), callback_data=f"floor_max_{f}"))
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="return_to_advanced_menu"))

        await callback_query.message.answer("Виберіть максимальний поверх:", reply_markup=keyboard)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("floor_max_"), state="*")
@log_operation("set_floor_max")
async def set_floor_max(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # parse the chosen floor
        chosen_floor = int(callback_query.data.split("_")[2])  # "floor_max_6" -> 6
        await state.update_data(floor_max=chosen_floor)

        logger.info("Floor max set", extra={"user_id": user_id, "floor_max": chosen_floor})
        await callback_query.message.answer(f"Максимальний поверх тепер {chosen_floor}.")
        # Optionally show advanced menu again
        await show_advanced_options(callback_query.message, state)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_is_not_first_floor", state="*")
@log_operation("edit_is_not_first_floor")
async def edit_is_not_first_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Так", callback_data="is_not_first_floor_yes"))
        keyboard.add(InlineKeyboardButton("Ні", callback_data="is_not_first_floor_no"))
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="return_to_advanced_menu"))

        await callback_query.message.answer("Чи виключати перший поверх?", reply_markup=keyboard)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("is_not_first_floor_"), state="*")
@log_operation("set_is_not_first_floor")
async def set_is_not_first_floor(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # either "yes" or "no"
        value = callback_query.data.split("_")[-1]  # yes / no
        # The actual param for flatfy would be `is_not_first_floor=yes` or `no`
        await state.update_data(is_not_first_floor=value)

        text = "Виключаю перший поверх" if value == "yes" else "Перший поверх дозволений"
        logger.info("First floor exclusion set", extra={"user_id": user_id, "is_not_first_floor": value})
        await callback_query.message.answer(text)
        await show_advanced_options(callback_query.message, state)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_last_floor", state="*")
@log_operation("edit_last_floor")
async def edit_last_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Так", callback_data="last_floor_yes"),
            InlineKeyboardButton("Ні", callback_data="last_floor_no")
        )
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="return_to_advanced_menu"))

        await callback_query.message.answer("Виключати останній поверх?", reply_markup=keyboard)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("last_floor_"), state="*")
@log_operation("set_last_floor")
async def set_last_floor(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        value = callback_query.data.split("_")[-1]  # yes / no
        await state.update_data(last_floor=value)

        text = "Виключаю останній поверх" if value == "no" else "Тільки останній поверх"
        logger.info("Last floor preference set", extra={"user_id": user_id, "last_floor": value})
        await callback_query.message.answer(f"last_floor={value}")
        await show_advanced_options(callback_query.message, state)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "pets_allowed", state="*")
@log_operation("edit_pets_allowed")
async def edit_pets_allowed_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        await state.update_data(current_edit="pets_allowed")

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Так", callback_data="pets_allowed_yes"),
            InlineKeyboardButton("Ні", callback_data="pets_allowed_no"),
        )
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="return_to_advanced_menu"))

        await callback_query.message.answer("🐶🐈🐹 Чи дозволено з тваринами?", reply_markup=keyboard)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("pets_allowed_"), state="*")
@log_operation("set_pets_allowed")
async def set_pets_allowed(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        value = callback_query.data.split("_")[-1]  # yes / no / some
        mapped_values = {'yes': 'Так', 'no': 'Ні'}
        ua_lang_value = mapped_values.get(value)
        await state.update_data(pets_allowed_full=value)

        logger.info("Pet preference set", extra={"user_id": user_id, "pets_allowed": value})

        # Delete selection panel
        try:
            await callback_query.message.delete()
        except Exception:
            pass

        await callback_query.message.answer(f'Обрано: "{ua_lang_value}"')

        current_edit = (await state.get_data()).get("current_edit")
        if current_edit == "pets_allowed":
            await callback_query.message.answer(
                "Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )
            await state.update_data(current_edit=None)
        else:
            await show_advanced_options(callback_query.message, state)

        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "without_broker", state="*")
@log_operation("edit_without_broker")
async def edit_without_broker_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # Mark that we are in edit flow so Back returns to edit menu
        await state.update_data(current_edit="without_broker")

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Від власника", callback_data="without_broker_owner"),
            InlineKeyboardButton("Усі оголошення", callback_data="without_broker_all")
        )
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="return_to_advanced_menu"))

        await callback_query.message.answer("Виберіть вид оголошень:", reply_markup=keyboard)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("without_broker_"), state="*")
@log_operation("set_without_broker")
async def set_without_broker(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        choice = callback_query.data.split("_")[-1]  # "owner" or "all"
        if choice == "owner":
            await state.update_data(without_broker="owner")
            text = "Тільки від власника"
        else:
            await state.update_data(without_broker=None)  # or just remove param
            text = "Усі оголошення"

        logger.info("Broker preference set", extra={"user_id": user_id, "without_broker": choice})

        # Delete the selection panel to keep chat clean
        try:
            await callback_query.message.delete()
        except Exception:
            pass

        await callback_query.message.answer(f'Обрано: "{text}"')

        # Determine if we are in edit flow
        current_edit = (await state.get_data()).get("current_edit")
        if current_edit == "without_broker":
            await callback_query.message.answer(
                "Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )
            await state.update_data(current_edit=None)
        else:
            # advanced flow
            await show_advanced_options(callback_query.message, state)

        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "advanced_done", state="*")
@log_operation("advanced_done")
async def advanced_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        user_data = await state.get_data()
        summary = build_full_summary(user_data)

        from aiogram.utils.markdown import escape_md
        summary_escaped = escape_md(summary)

        # A new keyboard that shows "Редагувати" or "Підписатися"
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Редагувати", callback_data="edit_parameters"),
            InlineKeyboardButton("Підписатися", callback_data="subscribe"),
        )

        logger.info("Advanced settings completed", extra={"user_id": user_id})
        await callback_query.message.answer(summary_escaped, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "edit_floor", state="*")
@log_operation("edit_floor")
async def edit_floor_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        await state.update_data(current_edit="floor")

        user_data = await state.get_data()
        floor_opts = user_data.get("floor_opts", {
            "not_first": False,
            "not_last": False,
            "floor_max_6": False,
            "floor_max_10": False,
            "floor_max_17": False,
            "only_last": False
        })
        await state.update_data(floor_opts=floor_opts)

        kb = floor_keyboard(floor_opts)
        await callback_query.message.answer("🏢 Налаштуйте поверх:", reply_markup=kb)
        await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("toggle_floor_"), state="*")
@log_operation("toggle_floor")
async def toggle_floor_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # e.g. toggle_floor_not_first, toggle_floor_only_last, toggle_floor_6 ...
        choice = callback_query.data.split("_", 2)[-1]  # "not_first", "not_last", "only_last", "6", "10", "17"
        user_data = await state.get_data()
        floor_opts = user_data.get("floor_opts", {
            "not_first": False,
            "not_last": False,
            "floor_max_6": False,
            "floor_max_10": False,
            "floor_max_17": False,
            "only_last": False
        })

        current_val = floor_opts.get(choice, False)
        new_val = not current_val
        floor_opts[choice] = new_val

        # Contradictions
        if choice == "only_last" and new_val is True:
            floor_opts["not_last"] = False
        if choice == "not_last" and new_val is True:
            floor_opts["only_last"] = False

        if choice in ["6", "10", "17"] and new_val is True:
            for other in ["6", "10", "17"]:
                if other != choice:
                    floor_opts[f"floor_max_{other}"] = False

        await state.update_data(floor_opts=floor_opts)

        kb = floor_keyboard(floor_opts)

        logger.info("Floor option toggled", extra={
            "user_id": user_id,
            "choice": choice,
            "new_value": new_val
        })

        try:
            await callback_query.message.edit_text(
                "🏢 Налаштуйте поверх:",
                reply_markup=kb
            )
        except MessageNotModified:
            await callback_query.answer("Немає змін.")

        await callback_query.answer()


def floor_opts_key(num_str):
    return f"floor_max_{num_str}"


@dp.callback_query_handler(lambda c: c.data == "floor_done", state="*")
@log_operation("floor_done")
async def floor_done_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        user_data = await state.get_data()
        floor_opts = user_data.get("floor_opts", {})

        # Convert toggles to final fields
        advanced_data = {}

        if floor_opts.get("not_first"):
            advanced_data["is_not_first_floor"] = "yes"
        else:
            advanced_data["is_not_first_floor"] = None

        if floor_opts.get("only_last"):
            advanced_data["last_floor"] = "yes"
        elif floor_opts.get("not_last"):
            advanced_data["last_floor"] = "no"
        else:
            advanced_data["last_floor"] = None

        if floor_opts.get("floor_max_6"):
            advanced_data["floor_max"] = 6
        elif floor_opts.get("floor_max_10"):
            advanced_data["floor_max"] = 10
        elif floor_opts.get("floor_max_17"):
            advanced_data["floor_max"] = 17
        else:
            advanced_data["floor_max"] = None

        # Save to state
        await state.update_data(**advanced_data)

        logger.info("Floor settings finalized", extra={
            "user_id": user_id,
            "floor_settings": advanced_data
        })

        # Delete panel message
        try:
            await callback_query.message.delete()
        except Exception:
            pass

        # Build summary text of floor settings
        summary_parts = []
        if advanced_data.get("is_not_first_floor") == "yes":
            summary_parts.append("Не перший поверх")
        if advanced_data.get("last_floor") == "no":
            summary_parts.append("Не останній поверх")
        if advanced_data.get("last_floor") == "yes":
            summary_parts.append("Тільки останній поверх")
        if advanced_data.get("floor_max"):
            summary_parts.append(f"Поверхи до {advanced_data['floor_max']}")

        summary_text = "; ".join(summary_parts) if summary_parts else "Без обмежень по поверху"
        await callback_query.message.answer(f"🏢 {summary_text}")

        current_edit = (await state.get_data()).get("current_edit")
        if current_edit == "floor":
            await callback_query.message.answer(
                "Оберіть параметр для редагування:",
                reply_markup=edit_parameters_keyboard()
            )
            await state.update_data(current_edit=None)
        else:
            await show_advanced_options(callback_query.message, state)

        await callback_query.answer()


@log_operation("show_advanced_options")
async def show_advanced_options(message: types.Message, state: FSMContext):
    with log_context(logger, chat_id=message.chat.id):
        # Build a keyboard for advanced fields
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("Поверх", callback_data="edit_floor"),
        )
        keyboard.add(
            InlineKeyboardButton("З тваринами?", callback_data="pets_allowed"),
        )
        keyboard.add(
            InlineKeyboardButton("Від власника?", callback_data="without_broker"),
        )
        # "Готово" -> return to summary
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="advanced_done"))

        await message.answer("Оберіть параметр для зміни:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("view_photos:"))
@log_operation("handle_view_photos")
async def handle_view_photos(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        # Expect callback_data "view_photos:<resource_url>"
        try:
            _, resource_url = callback_query.data.split("view_photos:")
            extra_images = get_extra_images(resource_url)

            if extra_images:
                media = MediaGroup()
                for i, url in enumerate(extra_images):
                    if i == 0:
                        media.attach_photo(url, caption="Додаткові фото:")
                    else:
                        media.attach_photo(url)
                await bot.send_media_group(chat_id=callback_query.from_user.id, media=media)
                logger.info("Extra photos sent", extra={
                    "user_id": user_id,
                    "resource_url": resource_url,
                    "photos_count": len(extra_images)
                })
            else:
                logger.info("No extra photos found", extra={
                    "user_id": user_id,
                    "resource_url": resource_url
                })
                await callback_query.answer("Немає додаткових фото.", show_alert=True)
        except Exception as e:
            logger.error("Error handling view photos", exc_info=True, extra={
                "user_id": user_id,
                "callback_data": callback_query.data,
                "error": str(e)
            })
            await callback_query.answer("Помилка при завантаженні фото.", show_alert=True)


def build_full_summary(data: dict) -> str:
    # property_type_apartment, property_type_house, property_type_room
    mapping_property = {"apartment": "Квартира", "house": "Будинок"}
    property_type = data.get("property_type", "")
    ua_lang_property_type = mapping_property.get(property_type, "")

    city = data.get("city", "")
    rooms = data.get("rooms", [])  # list
    price_min = data.get("price_min", "")
    price_max = data.get("price_max", "")

    floor_max = data.get("floor_max")
    is_not_first_floor = data.get("is_not_first_floor")
    last_floor = data.get("last_floor")
    pets_allowed_full = data.get("pets_allowed_full")
    without_broker = data.get("without_broker")

    # build lines
    lines = []
    lines.append(f"🏷 Тип нерухомості: {ua_lang_property_type}")
    lines.append(f"🏙️ Місто: {city}")
    lines.append(f"🛏️ Кількість кімнат: {', '.join('5+' if int(r)==5 else str(r) for r in rooms) if rooms else 'Не важливо'}")

    # Price range
    if price_min and price_max:
        price_range = f"від {price_min} до {price_max}"
        lines.append(f"💰 Ціновий діапазон: {price_range} грн")
    elif price_min and not price_max:
        lines.append(f"від {price_min} грн")
    elif price_max and not price_min:
        lines.append(f"до {price_max} грн")
    else:
        lines.append("💰 Ціна: не важливо")

    # ADVANCED
    if floor_max:
        lines.append(f"🏢 Поверхи до: {floor_max}")
    if is_not_first_floor == "yes":
        lines.append("🏢 Не перший поверх")
    elif is_not_first_floor == "no":
        lines.append("🏢 Перший поверх дозволений")

    if last_floor == "yes":
        lines.append("🏢 Тільки останній поверх")
    elif last_floor == "no":
        lines.append("🏢 Не останній поверх")

    if pets_allowed_full:
        lines.append("🐶🐈🐹 Дозволено з тваринами")

    if without_broker == "owner":
        lines.append("😎 Тільки від власника")

    return "**Поточні параметри пошуку**\n" + "\n".join(lines)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('city_page_'), state=FilterStates.waiting_for_city)
@log_operation("handle_city_pagination")
async def handle_city_pagination(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        _, page = callback_query.data.split('city_page_')
        page = int(page)
        kb_city = city_keyboard(AVAILABLE_CITIES, page=page)
        # if in edit flow add back button
        if (await state.get_data()).get("current_edit") == "city":
            kb_city.add(InlineKeyboardButton("↪️ Назад", callback_data="cancel_edit"))

        await safe_edit_message(
            chat_id=user_id,
            message_id=callback_query.message.message_id,
            text="🏙️ Оберіть місто:",
            reply_markup=kb_city
        )
