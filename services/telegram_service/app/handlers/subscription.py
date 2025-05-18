# services/telegram_service/app/handlers/subscription.py

from aiogram import types

from common.db.session import db_session
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.user_repository import UserRepository
from common.db.models.subscription import UserFilter
from common.utils.cache_managers import SubscriptionCacheManager, UserCacheManager
from common.utils.cache import get_entity_cache_key

from ..bot import dp, bot
from common.config import GEO_ID_MAPPING
from ..keyboards import (
    main_menu_keyboard,
    subscription_menu_keyboard, make_subscriptions_page_kb
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context


@dp.callback_query_handler(lambda c: c.data.startswith("sub_open:"))
@log_operation("handle_sub_open")
async def handle_sub_open(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, sub_id_str, page_str = callback_query.data.split(":")
        sub_id = int(sub_id_str)
        page = int(page_str)

        logger.info("Opening subscription details", extra={
            "telegram_id": telegram_id,
            "sub_id": sub_id,
            "page": page
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found", extra={
                    "telegram_id": telegram_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Get subscription details
            sub = db.query(UserFilter).filter(
                UserFilter.id == sub_id,
                UserFilter.user_id == db_user_id
            ).first()

            if not sub:
                logger.warning("Subscription not found", extra={
                    "telegram_id": telegram_id,
                    "sub_id": sub_id,
                    "db_user_id": db_user_id
                })
                await callback_query.answer("Підписка не знайдена.")
                return

            # Convert to dict for consistency with rest of function
            sub_dict = {
                'id': sub.id,
                'user_id': sub.user_id,
                'property_type': sub.property_type,
                'city': sub.city,
                'rooms_count': sub.rooms_count,
                'price_min': sub.price_min,
                'price_max': sub.price_max,
                'is_paused': sub.is_paused
            }

            logger.info("Subscription details retrieved", extra={
                "telegram_id": telegram_id,
                "sub_id": sub_id,
                "db_user_id": db_user_id,
                "is_paused": sub_dict['is_paused'],
                "sub_data": sub_dict  # Log the full subscription data for debugging
            })

            # Format the property type (apartment/house)
            mapping_property = {"apartment": "квартира", "house": "будинок"}
            ua_lang_property_type = mapping_property.get(sub_dict['property_type'], "")

            # Handle city display - use a default if not found in mapping
            city_code = sub_dict['city']
            city_name = GEO_ID_MAPPING.get(city_code, "Невідомо")
            if city_name is None:  # Explicitly check for None value
                city_name = f"Невідомо ({city_code})" if city_code else "Невідомо"

            # Format rooms display
            rooms_display = "Не вказано"
            if sub_dict['rooms_count']:
                if isinstance(sub_dict['rooms_count'], list):
                    rooms_list = [str(room) for room in sub_dict['rooms_count'] if room is not None]
                    if rooms_list:
                        rooms_display = ", ".join(rooms_list) + " кімн."
                else:
                    rooms_display = f"{sub_dict['rooms_count']} кімн."

            # Format price display
            price_min = sub_dict['price_min'] or "Не вказано"
            price_max = sub_dict['price_max'] or "∞"
            price_display = f"{price_min} - {price_max} грн."

            # Status display
            active = '✅ Активна' if not sub_dict['is_paused'] else '⏸️ Зупинена'

            # Build text with all information
            text = (
                f"Підписка #{sub_id}\n"
                f"🏷 Тип нерухомості: {ua_lang_property_type}\n"
                f"🏙️ Місто: {city_name}\n"
                f"🛏️ Кімнати: {rooms_display}\n"
                f"💰 Ціна: {price_display}\n"
                f"{active}"
            )

            # Build an inline keyboard with Pause/Resume, Delete, Edit, Back
            kb = InlineKeyboardMarkup()
            if sub_dict["is_paused"]:
                kb.add(InlineKeyboardButton("Відновити", callback_data=f"sub_resume:{sub_id}:{page}"))
            else:
                kb.add(InlineKeyboardButton("Зупинити", callback_data=f"sub_pause:{sub_id}:{page}"))

            kb.add(
                InlineKeyboardButton("Видалити", callback_data=f"sub_delete:{sub_id}:{page}"),
                InlineKeyboardButton("Редагувати", callback_data=f"sub_edit:{sub_id}:{page}"),
            )
            # "Back to list"
            kb.add(InlineKeyboardButton("<< Назад", callback_data=f"subs_page:{page}"))

            await callback_query.message.edit_text(text, reply_markup=kb)
            await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sub_pause:"))
@log_operation("handle_sub_pause")
async def handle_sub_pause(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, sub_id_str, page_str = callback_query.data.split(":")
        sub_id = int(sub_id_str)
        page = int(page_str)

        logger.info("Pausing subscription", extra={
            "telegram_id": telegram_id,
            "sub_id": sub_id,
            "page": page
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found for pause operation", extra={
                    "telegram_id": telegram_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Update subscription
            subscription = db.query(UserFilter).filter(
                UserFilter.id == sub_id,
                UserFilter.user_id == db_user_id
            ).first()

            if subscription:
                subscription.is_paused = True
                db.commit()

                logger.info("Subscription paused successfully", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })

                # Invalidate cache using cache managers
                SubscriptionCacheManager.invalidate_all(db_user_id, sub_id)
                UserCacheManager.invalidate_all(db_user_id)

                await callback_query.answer("Підписку призупинено.")
            else:
                logger.warning("Subscription not found for pause", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })
                await callback_query.answer("Підписка не знайдена.")
                return

        # Re-open subscription detail
        await handle_sub_open(callback_query)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_resume:"))
@log_operation("handle_sub_resume")
async def handle_sub_resume(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, sub_id_str, page_str = callback_query.data.split(":")
        sub_id = int(sub_id_str)
        page = int(page_str)

        logger.info("Resuming subscription", extra={
            "telegram_id": telegram_id,
            "sub_id": sub_id,
            "page": page
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found for resume operation", extra={
                    "telegram_id": telegram_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Use repository method
            success = SubscriptionRepository.enable_subscription_by_id(db, sub_id, db_user_id)
            if success:
                logger.info("Subscription resumed successfully", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })

                # Invalidate cache using cache managers
                SubscriptionCacheManager.invalidate_all(db_user_id, sub_id)
                UserCacheManager.invalidate_all(db_user_id)

                await callback_query.answer("Підписку поновлено.")
            else:
                logger.warning("Subscription not found for resume", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })
                await callback_query.answer("Підписка не знайдена.")
                return

        # Re-open subscription detail
        await handle_sub_open(callback_query)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_delete:"))
@log_operation("handle_sub_delete")
async def handle_sub_delete(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, sub_id_str, page_str = callback_query.data.split(":")
        sub_id = int(sub_id_str)
        page = int(page_str)

        logger.info("Deleting subscription", extra={
            "telegram_id": telegram_id,
            "sub_id": sub_id,
            "page": page
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found for delete operation", extra={
                    "telegram_id": telegram_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Use repository method to remove subscription
            success = SubscriptionRepository.remove_subscription(db, sub_id, db_user_id)

            if success:
                logger.info("Subscription deleted successfully", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })

                # Invalidate caches using cache managers
                SubscriptionCacheManager.invalidate_all(db_user_id, sub_id)
                UserCacheManager.invalidate_all(db_user_id)

                await callback_query.answer("Підписку видалено.")
            else:
                logger.warning("Subscription not found for delete", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "sub_id": sub_id
                })
                await callback_query.answer("Підписка не знайдена.")
                return

        # Return to the list view
        await handle_subs_page(callback_query)


@dp.callback_query_handler(lambda c: c.data.startswith("sub_edit:"))
@log_operation("handle_sub_edit")
async def handle_sub_edit(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, sub_id_str, page_str = callback_query.data.split(":")
        sub_id = int(sub_id_str)
        page = int(page_str)

        logger.info("Edit subscription requested", extra={
            "telegram_id": telegram_id,
            "sub_id": sub_id,
            "page": page
        })

        # Possibly begin an FSM to ask user new city, price, etc.
        await callback_query.answer("У майбутньому тут можна відредагувати дані.")


@dp.callback_query_handler(lambda c: c.data.startswith("subs_page:"))
@log_operation("handle_subs_page")
async def handle_subs_page(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    with log_context(logger, telegram_id=telegram_id, callback_data=callback_query.data):
        _, page_str = callback_query.data.split(":")
        page = int(page_str)

        logger.info("Showing subscriptions page", extra={
            "telegram_id": telegram_id,
            "page": page
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found for page view", extra={
                    "telegram_id": telegram_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Get subscription count and paginated list
            total = SubscriptionRepository.count_subscriptions(db, db_user_id)

            logger.info("Retrieving subscriptions", extra={
                "telegram_id": telegram_id,
                "db_user_id": db_user_id,
                "total_subscriptions": total,
                "page": page
            })

            # Try to get subscriptions from the cache first
            cache_key = get_entity_cache_key("user_subscriptions_paginated", db_user_id, f"{page}:5")
            cached_subs = SubscriptionCacheManager.get(cache_key)

            if cached_subs:
                subs = cached_subs
                logger.info("Subscriptions retrieved from cache", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "page": page,
                    "count": len(subs)
                })
            else:
                # Not in cache, get from a database
                subs = SubscriptionRepository.list_subscriptions_paginated(db, db_user_id, page)
                logger.info("Subscriptions retrieved from database", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "page": page,
                    "count": len(subs)
                })

        # Create keyboard
        kb = make_subscriptions_page_kb(db_user_id, page, subs, total)

        await callback_query.message.edit_text("Ваші підписки:", reply_markup=kb)
        await callback_query.answer()


@dp.message_handler(lambda msg: msg.text and msg.text.strip() == "📝 Мої підписки")
@log_operation("show_subscriptions_menu")
async def show_subscriptions_menu(message: types.Message):
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id):
        logger.info("User requested subscriptions menu", extra={
            "telegram_id": telegram_id,
            "message_text": message.text
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(telegram_id), "telegram")
            if not user:
                logger.warning("User not found for subscriptions menu", extra={
                    "telegram_id": telegram_id
                })
                await message.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Get subscription count and first page
            total = SubscriptionRepository.count_subscriptions(db, db_user_id)

            logger.info("Subscription count retrieved", extra={
                "telegram_id": telegram_id,
                "db_user_id": db_user_id,
                "total_subscriptions": total
            })

        if total == 0:
            logger.info("No subscriptions found", extra={
                "telegram_id": telegram_id,
                "db_user_id": db_user_id
            })
            await message.answer("У вас немає підписок.", reply_markup=main_menu_keyboard())
            return

        with db_session() as db:
            page = 0

            # Try to get from the cache first
            cache_key = get_entity_cache_key("user_subscriptions_paginated", db_user_id, f"{page}:5")
            cached_subs = SubscriptionCacheManager.get(cache_key)

            if cached_subs:
                subs = cached_subs
                logger.info("Initial subscriptions page from cache", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "count": len(subs)
                })
            else:
                # Not in cache, get from a database
                subs = SubscriptionRepository.list_subscriptions_paginated(db, db_user_id, page)
                logger.info("Initial subscriptions page from database", extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "count": len(subs)
                })

        # Create keyboard
        kb = make_subscriptions_page_kb(db_user_id, page, subs, total)
        await message.answer("Ваші підписки:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == 'menu_my_subscription')
@log_operation("my_subscription_handler")
async def my_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("User clicked my subscription menu", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for subscription menu", extra={
                    "user_id": user_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Try to get subscription data from cache first
            cached_subscription = SubscriptionCacheManager.get_user_subscriptions(db_user_id)

            if cached_subscription:
                subscription_data = cached_subscription
                logger.info("Subscription data retrieved from cache", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
            else:
                # Not in cache, get from database
                subscription_data = SubscriptionRepository.get_subscription_data(db, db_user_id)
                logger.info("Subscription data retrieved from database", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

            # Try to get subscription expiration date from cache
            cache_key_sub_until = get_entity_cache_key("user_subscription", db_user_id, "free")
            cached_until = UserCacheManager.get(cache_key_sub_until)

            if cached_until:
                subscription_until = cached_until
                logger.info("Subscription expiration from cache", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
            else:
                # Not in cache, get from database
                subscription_until = UserRepository.get_subscription_until(db, db_user_id)
                logger.info("Subscription expiration from database", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

            if not subscription_data:
                logger.info("No active subscription found", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await callback_query.message.answer("У вас немає активної підписки.")
                return

            city = GEO_ID_MAPPING.get(subscription_data['city'])
            mapping_property = {"apartment": "Квартира", "house": "Будинок"}
            ua_lang_property_type = mapping_property.get(subscription_data['property_type'], "")

            text = f"""Деталі підписки:
         - 🏙️ Місто: {city}
         - 🏷 Тип нерухомості: {ua_lang_property_type}
         - 🛏️ Кількість кімнат: {subscription_data['rooms_count']}
         - 💰 Ціна: {str(subscription_data['price_min'])}-{str(subscription_data['price_max'])} грн.

         Підписка спливає {subscription_until}
         """
            await bot.send_message(
                chat_id=callback_query.message.chat.id,
                text=text,
                reply_markup=subscription_menu_keyboard()
            )


@dp.callback_query_handler(lambda c: c.data == 'subs_disable')
@log_operation("disable_subscription_handler")
async def disable_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("Disabling subscription", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for disable operation", extra={
                    "user_id": user_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Disable subscription
            success = SubscriptionRepository.disable_subscription(db, db_user_id)

            if success:
                logger.info("Subscription disabled successfully", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

                # Invalidate cache
                SubscriptionCacheManager.invalidate_all(db_user_id)

                await bot.send_message(
                    chat_id=callback_query.message.chat.id,
                    text="Ваша підписка відключена.",
                    reply_markup=main_menu_keyboard()
                )
            else:
                logger.warning("Subscription not found for disable", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await callback_query.answer("Підписка не знайдена.")


@dp.callback_query_handler(lambda c: c.data == 'subs_enable')
@log_operation("enable_subscription_handler")
async def enable_subscription_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("Enabling subscription", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for enable operation", extra={
                    "user_id": user_id
                })
                await callback_query.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Enable subscription
            success = SubscriptionRepository.enable_subscription(db, db_user_id)

            if success:
                logger.info("Subscription enabled successfully", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

                # Invalidate cache
                SubscriptionCacheManager.invalidate_all(db_user_id)

                await bot.send_message(
                    chat_id=callback_query.message.chat.id,
                    text="Ваша підписка включена.",
                    reply_markup=main_menu_keyboard()
                )
            else:
                logger.warning("Subscription not found for enable", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await callback_query.answer("Підписка не знайдена.")


@dp.message_handler(lambda msg: msg.text == "🛑 Відключити")
@log_operation("handle_disable_subscription")
async def handle_disable_subscription(message: types.Message):
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("User requested to disable subscription", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for disable request", extra={
                    "user_id": user_id
                })
                await message.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Disable subscription
            success = SubscriptionRepository.disable_subscription(db, db_user_id)

            if success:
                logger.info("Subscription disabled via message", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

                # Invalidate cache
                SubscriptionCacheManager.invalidate_all(db_user_id)

                await message.answer(
                    "Ваша підписка відключена.",
                    reply_markup=main_menu_keyboard()
                )
            else:
                logger.warning("Subscription not found for disable via message", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await message.answer("Підписка не знайдена.")


@dp.message_handler(lambda msg: msg.text == "✅ Включити")
@log_operation("handle_enable_subscription")
async def handle_enable_subscription(message: types.Message):
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("User requested to enable subscription", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for enable request", extra={
                    "user_id": user_id
                })
                await message.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            # Enable subscription
            success = SubscriptionRepository.enable_subscription(db, db_user_id)

            if success:
                logger.info("Subscription enabled via message", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

                # Invalidate cache
                SubscriptionCacheManager.invalidate_all(db_user_id)

                await message.answer(
                    "Ваша підписка включена на безкоштовний період (або на платний, якщо ви вже оплачували).",
                    reply_markup=main_menu_keyboard()
                )
            else:
                logger.warning("Subscription not found for enable via message", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await message.answer("Підписка не знайдена.")


@dp.message_handler(lambda msg: msg.text == "📝 Моя підписка")
@log_operation("handle_my_subscription")
async def handle_my_subscription(message: types.Message):
    """
    Show subscription details & sub-menu keyboard.
    """
    user_id = message.from_user.id

    with log_context(logger, user_id=user_id):
        logger.info("User requested subscription details", extra={
            "user_id": user_id
        })

        with db_session() as db:
            # Get database user ID
            user = UserRepository.get_by_messenger_id(db, str(user_id), "telegram")
            if not user:
                logger.warning("User not found for subscription details", extra={
                    "user_id": user_id
                })
                await message.answer("Користувач не знайдений.")
                return

            db_user_id = user.id

            logger.info("Retrieved user info", extra={
                "user_id": user_id,
                "db_user_id": db_user_id
            })

            # Try to get subscription data from cache first
            cached_data = SubscriptionCacheManager.get_user_subscriptions(db_user_id)

            if cached_data:
                sub_data = cached_data
                logger.info("Subscription data from cache", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
            else:
                # Not in cache, get from database
                sub_data = SubscriptionRepository.get_subscription_data(db, db_user_id)
                logger.info("Subscription data from database", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })

            # Try to get subscription until date from cache
            cache_key_until = get_entity_cache_key("user_subscription", db_user_id, "free")
            subscription_until = UserCacheManager.get(cache_key_until)

            if not subscription_until:
                # Try paid subscription if free is not available
                cache_key_until = get_entity_cache_key("user_subscription", db_user_id, "paid")
                subscription_until = UserCacheManager.get(cache_key_until)

                if not subscription_until:
                    # Not in cache, get from database
                    subscription_until = UserRepository.get_subscription_until(db, db_user_id, free=True)

                    if not subscription_until:
                        subscription_until = UserRepository.get_subscription_until(db, db_user_id, free=False)
                    logger.info("Subscription expiration from database", extra={
                        "user_id": user_id,
                        "db_user_id": db_user_id
                    })

            if not sub_data:
                logger.info("No active subscription data", extra={
                    "user_id": user_id,
                    "db_user_id": db_user_id
                })
                await message.answer("У вас немає активної підписки.")
                return

            city = GEO_ID_MAPPING.get(sub_data['city'])
            mapping_property = {"apartment": "Квартира", "house": "Будинок"}
            ua_lang_property_type = mapping_property.get(sub_data['property_type'], "")

            rooms_list = sub_data['rooms_count']
            rooms = []
            for el in rooms_list:
                rooms.append(str(el))
            rooms = '-'.join(rooms)

            text = (
                f"Деталі підписки:\n"
                f"  - Місто: {city}\n"
                f"  - Тип нерухомості: {ua_lang_property_type}\n"
                f"  - К-сть кімнат: {rooms}\n"
                f"  - Ціна: {str(sub_data['price_min'])} - {str(sub_data['price_max'])} грн.\n\n"
                f"Підписка спливає {subscription_until}\n"
            )

        await message.answer(
            text,
            reply_markup=subscription_menu_keyboard()
        )

