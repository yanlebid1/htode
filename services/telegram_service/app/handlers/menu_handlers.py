# services/telegram_service/app/handlers/menu_handlers.py
import decimal

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from common.db.session import db_session
from common.utils.cache import redis_cache
from ..bot import dp
from ..states.basis_states import FilterStates
from common.db.operations import update_user_filter, start_free_subscription_of_user, get_db_user_id_by_telegram_id, \
    get_or_create_user, Ad, add_subscription as add_user_subscription
from common.db.database import execute_query
from common.config import GEO_ID_MAPPING, get_key_by_value, build_ad_text
from common.celery_app import celery_app
from common.utils.ad_utils import get_ad_images
from ..utils.message_utils import (
    safe_send_message, safe_answer_callback_query, delete_message_safe
)
from ..keyboards import (
    main_menu_keyboard,
    how_to_use_keyboard,
    tech_support_keyboard,
    edit_parameters_keyboard
)

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context

# Stores ids of trigger messages (how it works)
TRIGGER_INFO = {}
# Stores last sent main-menu message id per user so we can delete it before sending a new one
MAIN_MENU_MESSAGES = {}


@dp.message_handler(commands=['menu'])
@log_operation("show_main_menu")
async def show_main_menu(message: types.Message):
    """
    Sends the main menu keyboard when the user uses /menu.
    """
    user_id = message.from_user.id
    with log_context(logger, user_id=user_id, command="menu"):
        logger.info("Showing main menu", extra={
            "user_id": user_id,
            "username": message.from_user.username
        })

        await send_main_menu(user_id)


@dp.callback_query_handler(lambda c: c.data == 'edit_parameters')
@log_operation("edit_parameters")
async def edit_parameters(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handles 'edit_parameters' callback - shows parameter editing menu
    """
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("User requested parameter editing", extra={
            "user_id": user_id
        })

        await safe_send_message(
            chat_id=callback_query.from_user.id,
            text="Оберіть параметр для редагування:",
            reply_markup=edit_parameters_keyboard()
        )
        await safe_answer_callback_query(callback_query.id)


@dp.message_handler(lambda msg: msg.text == "✏️ Редагувати")
@log_operation("handle_edit_button")
async def handle_edit_button(message: types.Message):
    """
    Handles the "Edit" button press from keyboard
    """
    user_id = message.from_user.id
    with log_context(logger, user_id=user_id, button_text=message.text):
        logger.info("Edit button pressed", extra={
            "user_id": user_id
        })

        await safe_send_message(
            chat_id=message.from_user.id,
            text="Оберіть параметр для редагування:",
            reply_markup=edit_parameters_keyboard()
        )


@dp.callback_query_handler(lambda c: c.data == 'subs_back')
@log_operation("subscription_back_handler")
async def subscription_back_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("Returning to main menu from subscription", extra={
            "user_id": user_id
        })

        await send_main_menu(callback_query.message.chat.id)
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == 'menu_how_to_use')
@log_operation("how_to_use_handler")
async def how_to_use_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("Showing how to use information", extra={
            "user_id": user_id
        })

        text = (
            "Як використовувати:\n\n"
            "1. Налаштуйте параметри фільтра.\n"
            "2. Увімкніть передплату.\n"
            "3. Отримуйте сповіщення.\n\n"
            "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
        )
        bot_msg = await safe_send_message(
            chat_id=callback_query.message.chat.id,
            text=text,
            reply_markup=how_to_use_keyboard()
        )
        await safe_answer_callback_query(callback_query.id)

        # store trigger and bot msg ids
        TRIGGER_INFO[user_id] = {
            'trigger_id': callback_query.message.message_id,
            'bot_id': bot_msg.message_id if bot_msg else None
        }


@dp.callback_query_handler(lambda c: c.data == 'contact_support')
@log_operation("contact_support_handler")
async def contact_support_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("User wants to contact support", extra={
            "user_id": user_id
        })

        # If you want them to message an admin directly, you can provide a link or instructions.
        # Or you can set up a separate "Support chat" logic. For simplicity:
        await safe_send_message(
            chat_id=callback_query.message.chat.id,
            text="Напишіть своє питання, і наша служба підтримки відповість вам найближчим часом..."
        )
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == 'menu_tech_support')
@log_operation("menu_tech_support_handler")
async def menu_tech_support_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("Showing tech support menu", extra={
            "user_id": user_id
        })

        # Same as above or you can show a new keyboard
        await safe_send_message(
            chat_id=callback_query.message.chat.id,
            text="Звернення до техпідтримки. Будь ласка, введіть своє питання.",
            reply_markup=tech_support_keyboard()
        )
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data == 'main_menu')
@log_operation("back_to_main_menu_handler")
async def back_to_main_menu_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id, callback_data=callback_query.data):
        logger.info("Returning to main menu", extra={
            "user_id": user_id
        })

        await send_main_menu(user_id)
        await safe_answer_callback_query(callback_query.id)


@dp.callback_query_handler(Text(startswith="subscribe"), state=FilterStates.waiting_for_confirmation)
@log_operation("subscribe")
async def subscribe(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    user_db_id = user_data.get('user_db_id')
    telegram_id = user_data.get('telegram_id')

    if not telegram_id:
        telegram_id = callback_query.from_user.id
        await state.update_data(telegram_id=telegram_id)

    with log_context(logger, telegram_id=telegram_id, user_db_id=user_db_id):
        logger.info("Subscribe handler started", extra={
            "user_db_id": user_db_id,
            "telegram_id": telegram_id,
            "user_data": user_data
        })

        if not user_db_id:
            # If user_db_id is not in state, try to get it directly from DB
            logger.warning("user_db_id not found in state, trying to retrieve from DB", extra={
                "telegram_id": telegram_id
            })
            user_db_id = get_db_user_id_by_telegram_id(telegram_id)

            if not user_db_id:
                # Still no user_db_id, create the user
                logger.warning("User not found in DB, creating new user", extra={
                    "telegram_id": telegram_id
                })
                user_db_id = get_or_create_user(telegram_id)
                await state.update_data(user_db_id=user_db_id)

        if not user_db_id:
            logger.error("Failed to get or create user", extra={
                "telegram_id": telegram_id
            })
            await safe_send_message(
                chat_id=callback_query.from_user.id,
                text="Помилка: Не вдалося створити профіль користувача."
            )
            await safe_answer_callback_query(callback_query.id)
            return

        # Verify user exists in database before proceeding
        check_sql = "SELECT id FROM users WHERE id = %s"
        user_exists = execute_query(check_sql, [user_db_id], fetchone=True)
        if not user_exists:
            logger.error("User ID does not exist in database", extra={
                "user_db_id": user_db_id,
                "telegram_id": telegram_id
            })
            # Try to create user again
            user_db_id = get_or_create_user(telegram_id)
            await state.update_data(user_db_id=user_db_id)

            # Verify again
            user_exists = execute_query(check_sql, [user_db_id], fetchone=True)
            if not user_exists:
                logger.error("Failed to create user even after retry", extra={
                    "telegram_id": telegram_id
                })
                await safe_send_message(
                    chat_id=callback_query.from_user.id,
                    text="Помилка: Не вдалося створити профіль користувача."
                )
                await safe_answer_callback_query(callback_query.id)
                return

        # Перетворимо дані для збереження
        filters = {
            'property_type': user_data.get('property_type'),
            'city': user_data.get('city'),
            'rooms': user_data.get('rooms'),  # Список або None
            'price_min': user_data.get('price_min'),
            'price_max': user_data.get('price_max'),
        }

        logger.info('Preparing to save filters', extra={
            "user_db_id": user_db_id,
            "filters": filters
        })

        # Збереження фільтрів у базі даних
        try:
            # Convert city name to geo_id
            city_name = filters.get('city')
            geo_id = get_key_by_value(city_name, GEO_ID_MAPPING) if city_name else None

            add_user_subscription(
                user_db_id,
                filters.get('property_type'),
                geo_id,
                filters.get('rooms'),
                filters.get('price_min'),
                filters.get('price_max')
            )
            logger.info('Subscription added successfully', extra={
                "user_db_id": user_db_id
            })
            start_free_subscription_of_user(user_db_id)
            logger.info('Free subscription started', extra={
                "user_db_id": user_db_id
            })
        except Exception as e:
            logger.error("Error updating user filters", exc_info=True, extra={
                "user_db_id": user_db_id,
                "filters": filters,
                "error": str(e)
            })
            await safe_send_message(
                chat_id=telegram_id,
                text="Помилка при збереженні фільтрів. Спробуйте ще раз."
            )
            await safe_answer_callback_query(callback_query.id)
            return

        # 1) Let user know subscription is set
        await safe_send_message(
            chat_id=telegram_id,
            text="Ви успішно підписалися на пошук оголошень!"
        )

        # 2) Now do the multi-step check in local DB
        logger.info('Starting to fetch ads for period', extra={
            "user_db_id": user_db_id
        })
        final_ads = []
        for days_limit in [1, 3, 7, 14, 30]:
            ads = fetch_ads_for_period(filters, days_limit, limit=3)
            logger.info(f"Fetched ads for {days_limit} days", extra={
                "user_db_id": user_db_id,
                "days_limit": days_limit,
                "ads_count": len(ads)
            })
            if len(ads) >= 1:
                final_ads = ads
                # We found enough ads => break out
                break

        if final_ads:
            # We found >=3 ads in last days_limit
            message_ending = 'день' if days_limit == 1 else 'днів'
            await safe_send_message(
                chat_id=telegram_id,
                text=f"Ось вам актуальні оголошення за останні {days_limit} {message_ending}:"
            )

            # Send them (as 3 separate messages, or combine them)
            for ad in final_ads:
                s3_image_links = get_ad_images(ad)[0] if get_ad_images(ad) else None
                text = build_ad_text(ad)
                resource_url = ad.get("resource_url")
                ad_external_id = ad.get("external_id")
                ad_id = ad.get("id")

                logger.info(f"Sending ad to user", extra={
                    "user_db_id": user_db_id,
                    "telegram_id": telegram_id,
                    "ad_id": ad_id,
                    "ad_external_id": ad_external_id
                })

                # Now dispatch the Celery task:
                args_for_celery = [telegram_id, text, s3_image_links, resource_url, ad_id, ad_external_id]
                logger.info(f"Dispatching celery task", extra={
                    "user_db_id": user_db_id,
                    "task_name": "send_ad_with_extra_buttons",
                    "telegram_id": telegram_id,
                    "ad_id": ad_id
                })
                celery_app.send_task(
                    "common.messaging.tasks.send_ad_with_extra_buttons",
                    args=args_for_celery,
                    kwargs={"platform": "telegram"}
                )
        else:
            # We never found 3 ads even in last 30 days
            logger.info("No ads found for user filters", extra={
                "user_db_id": user_db_id,
                "filters": filters
            })
            await safe_send_message(
                chat_id=telegram_id,
                text="Ваші параметри фільтру настільки унікальні, що майже немає оголошень навіть за останній місяць.\n"
                     "Спробуйте розширити параметри пошуку або зачекайте. Ми сповістимо, щойно з'являться нові оголошення."
            )

        # 4) End the state
        await state.finish()
        await safe_answer_callback_query(callback_query.id)

        # 5) Optional: send a task to do further real-time scraping or notification
        logger.info("Dispatching notification task", extra={
            "user_db_id": user_db_id,
            "telegram_id": telegram_id
        })
        celery_app.send_task(
            'notifier_service.app.tasks.notify_user_with_ads',
            args=[telegram_id, filters]
        )

        await safe_send_message(
            chat_id=telegram_id,
            text="Ми будемо надсилати вам нові оголошення, щойно вони з'являтимуться!",
            reply_markup=main_menu_keyboard()
        )


@dp.callback_query_handler(lambda c: c.data == "unsubscribe", state="*")
@log_operation("unsubscribe_callback")
async def unsubscribe_callback(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    with log_context(logger, user_id=user_id):
        logger.info("User unsubscribing", extra={
            "user_id": user_id
        })

        # In DB, set user subscription inactive or remove user_filters
        sql = "UPDATE users SET subscription_until = NOW() WHERE telegram_id = %s"
        try:
            execute_query(sql, [user_id])
            logger.info("User subscription deactivated", extra={
                "user_id": user_id
            })
        except Exception as e:
            logger.error("Error deactivating subscription", exc_info=True, extra={
                "user_id": user_id,
                "error": str(e)
            })

        await safe_send_message(
            chat_id=user_id,
            text="Ви відписалися від розсилки оголошень."
        )
        await safe_answer_callback_query(callback_query.id)


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='cancel', ignore_case=True), state='*')
@log_operation("cancel_handler")
async def cancel_handler(message: types.Message, state: FSMContext):
    """Дозволяє користувачеві скасувати будь-яку дію"""
    user_id = message.from_user.id
    with log_context(logger, user_id=user_id):
        current_state = await state.get_state()
        if current_state is None:
            logger.info("Cancel called but no state active", extra={
                "user_id": user_id
            })
            return

        logger.info("Cancelling current action", extra={
            "user_id": user_id,
            "current_state": current_state
        })

        await state.finish()
        await safe_send_message(
            chat_id=message.from_user.id,
            text='Дія скасована.',
            reply_markup=types.ReplyKeyboardRemove()
        )


@redis_cache("ads_period", ttl=300)  # 5 minute cache
@log_operation("fetch_ads_for_period")
def fetch_ads_for_period(filters, days, limit=3):
    """
    Query your local ads table, matching the user's filters,
    for ads from the last `days` days. Return up to `limit` ads.
    """
    with log_context(logger, filters=filters, days=days, limit=limit):
        try:
            with db_session() as db:
                # Start building the query
                query = db.query(Ad)

                # Apply filters
                city = filters.get('city')
                if city:
                    geo_id = get_key_by_value(city, GEO_ID_MAPPING)
                    if geo_id:
                        query = query.filter(Ad.city == geo_id)

                if filters.get('property_type'):
                    query = query.filter(Ad.property_type == filters['property_type'])

                if filters.get('rooms') is not None:
                    query = query.filter(Ad.rooms_count.in_(filters['rooms']))

                if filters.get('price_min') is not None:
                    query = query.filter(Ad.price >= filters['price_min'])

                if filters.get('price_max') is not None:
                    query = query.filter(Ad.price <= filters['price_max'])

                # Add time window
                from datetime import datetime, timedelta
                cutoff_date = datetime.now() - timedelta(days=days)
                query = query.filter(Ad.insert_time >= cutoff_date)

                # Order and limit
                query = query.order_by(Ad.insert_time.desc()).limit(limit)

                # Execute query
                ads = query.all()

                # Convert to dictionaries
                result = []
                for ad in ads:
                    ad_dict = {
                        'id': ad.id,
                        'external_id': ad.external_id,
                        'property_type': ad.property_type,
                        'city': ad.city,
                        'address': ad.address,
                        'price': float(ad.price) if isinstance(ad.price, decimal.Decimal) else ad.price,
                        'square_feet': float(ad.square_feet) if isinstance(ad.square_feet,
                                                                           decimal.Decimal) else ad.square_feet,
                        'rooms_count': ad.rooms_count,
                        'floor': ad.floor,
                        'total_floors': ad.total_floors,
                        'insert_time': ad.insert_time.isoformat() if ad.insert_time else None,
                        'description': ad.description,
                        'resource_url': ad.resource_url
                    }
                    result.append(ad_dict)

                logger.info("Ads fetched successfully", extra={
                    "ads_count": len(result),
                    "days": days,
                    "filters": filters
                })
                return result
        except Exception as e:
            logger.error("Error fetching ads for period", exc_info=True, extra={
                "filters": filters,
                "days": days,
                "error": str(e)
            })
            return []


@dp.message_handler(lambda msg: msg.text == "🤔 Як це працює?")
@log_operation("handle_how_to_use")
async def handle_how_to_use(message: types.Message):
    user_id = message.from_user.id
    with log_context(logger, user_id=user_id):
        logger.info("User requested how-to-use info", extra={
            "user_id": user_id
        })

        text = (
            "Як використовувати:\n\n"
            "1. Налаштуйте параметри фільтра.\n"
            "2. Увімкніть передплату.\n"
            "3. Отримуйте сповіщення.\n\n"
            "Якщо у вас є додаткові питання, зверніться до служби підтримки!"
        )
        bot_msg = await safe_send_message(
            chat_id=message.from_user.id,
            text=text,
            reply_markup=how_to_use_keyboard()
        )

        # store trigger and bot msg ids
        TRIGGER_INFO[user_id] = {
            'trigger_id': message.message_id,
            'bot_id': bot_msg.message_id if bot_msg else None
        }


@dp.message_handler(lambda msg: msg.text == "↪️ Назад", state="*")
@log_operation("handle_back")
async def handle_back(message: types.Message, state: FSMContext):
    """
    Universal handler for the "↪️ Назад" button.

    1. Closes any active FSM state.
    2. Cleans up messages stored by different sub-flows (TRIGGER_INFO or Phone Verification BACK_INFO).
    3. Returns the user to the main menu.
    """

    user_id = message.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("User pressed back button", extra={
            "user_id": user_id,
            "fsm_state": await state.get_state()
        })

        # 1) Finish any active FSM state so further handlers are reset
        current_state = await state.get_state()
        if current_state:
            try:
                await state.finish()
                logger.debug("FSM state finished", extra={"user_id": user_id, "old_state": current_state})
            except Exception as e:
                logger.warning("Could not finish FSM state", exc_info=True, extra={
                    "user_id": user_id,
                    "error": str(e)
                })

        # 2) Try to remove any messages stored in TRIGGER_INFO (how-it-works flow)
        info = TRIGGER_INFO.pop(user_id, None)
        if info:
            if info.get('bot_id'):
                await delete_message_safe(user_id, info['bot_id'])
            if info.get('trigger_id'):
                await delete_message_safe(user_id, info['trigger_id'])

        # 3) Try to remove any messages stored during phone verification (BACK_INFO)
        try:
            from .phone_verification import BACK_INFO  # imported lazily to avoid circular deps
            p_info = BACK_INFO.pop(user_id, None)
            if p_info:
                if p_info.get('bot_id'):
                    await delete_message_safe(user_id, p_info['bot_id'])
                if p_info.get('trigger_id'):
                    await delete_message_safe(user_id, p_info['trigger_id'])
        except Exception as e:
            # Ignore if module not imported yet
            logger.debug("BACK_INFO not available or error cleaning", extra={"error": str(e)})

        # 4) Delete the pressed "Back" message itself if possible
        try:
            await delete_message_safe(user_id, message.message_id)
        except Exception:
            pass

        # 5) Show the main menu again
        await send_main_menu(user_id)


@dp.message_handler(lambda msg: msg.text == "➕ Додати підписку")
@log_operation("add_subscription_prompt")
async def add_subscription_prompt(message: types.Message):
    """
    Handles the text button for adding a new subscription
    """
    user_id = message.from_user.id
    with log_context(logger, user_id=user_id):
        logger.info("User wants to add subscription", extra={
            "user_id": user_id
        })

        await safe_send_message(
            chat_id=message.from_user.id,
            text="Оберіть параметр для редагування:",
            reply_markup=edit_parameters_keyboard()
        )


# ---- Helper -------------------------------------------------------------
async def send_main_menu(chat_id: int):
    """Send the main menu, removing the previous menu message if it exists."""
    # Delete previous main-menu message for this user (if any)
    prev_menu_id = MAIN_MENU_MESSAGES.get(chat_id)
    if prev_menu_id:
        try:
            await delete_message_safe(chat_id, prev_menu_id)
        except Exception:
            pass  # It's okay if the message was already deleted

    # Send a fresh main menu message
    msg = await safe_send_message(
        chat_id=chat_id,
        text="Головне меню:",
        reply_markup=main_menu_keyboard()
    )

    # Store its id so we can remove it next time
    if msg:
        MAIN_MENU_MESSAGES[chat_id] = msg.message_id

    return msg
