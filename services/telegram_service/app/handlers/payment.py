# services/telegram_service/app/handlers/payment.py

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..bot import dp
from common.db.operations import get_user_by_telegram_id
from ..payment.wayforpay import create_payment_form_url
from ..utils.message_utils import delete_message_safe, safe_answer_callback_query

# Import service logger and logging utilities
from .. import logger
from common.utils.logging_config import log_operation, log_context


@dp.message_handler(lambda msg: msg.text == "💳 Оплатити підписку")
@log_operation("payment_handler")
async def payment_handler(message: types.Message):
    """Handle subscription payment request"""
    telegram_id = message.from_user.id

    with log_context(logger, telegram_id=telegram_id, action="payment_request"):
        logger.info(
            "Payment request initiated",
            extra={"telegram_id": telegram_id, "username": message.from_user.username},
        )

        user = get_user_by_telegram_id(str(telegram_id))
        db_user_id = user.id if user else None

        if not db_user_id:
            logger.warning(
                "User not found for payment request", extra={"telegram_id": telegram_id}
            )
            await message.answer(
                "Спочатку потрібно зареєструватися. Використайте команду /start."
            )
            return

        logger.info(
            "Presenting payment options",
            extra={"telegram_id": telegram_id, "db_user_id": db_user_id},
        )

        # Create payment keyboard with options
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("1 тиждень - 49 грн", callback_data="pay_49_1week"),
            InlineKeyboardButton("2 тижні - 60 грн", callback_data="pay_60_2weeks"),
        )
        keyboard.add(
            InlineKeyboardButton("1 місяць - 99 грн", callback_data="pay_99_1month")
        )
        keyboard.add(InlineKeyboardButton("↪️ Назад", callback_data="payment_back"))

        bot_msg = await message.answer(
            "Оберіть тарифний план для оплати підписки:", reply_markup=keyboard
        )
        PAY_TRIGGER[telegram_id] = {
            "trigger_id": message.message_id,
            "bot_id": bot_msg.message_id if bot_msg else None,
        }
        logger.info(
            "Payment options presented successfully",
            extra={"telegram_id": telegram_id, "db_user_id": db_user_id},
        )


@dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
@log_operation("process_payment")
async def process_payment(callback_query: types.CallbackQuery):
    """Process payment button click"""
    telegram_id = callback_query.from_user.id

    with log_context(
        logger, telegram_id=telegram_id, callback_data=callback_query.data
    ):
        # Extract amount and period from callback data
        parts = callback_query.data.split("_")
        amount = float(parts[1])
        period = parts[2]

        logger.info(
            "Processing payment request",
            extra={
                "telegram_id": telegram_id,
                "amount": amount,
                "period": period,
                "callback_data": callback_query.data,
            },
        )

        user = get_user_by_telegram_id(str(telegram_id))
        db_user_id = user.id if user else None

        if not db_user_id:
            logger.warning(
                "User not found during payment processing",
                extra={"telegram_id": telegram_id},
            )
            await callback_query.answer("Користувач не знайдений.")
            return

        logger.info(
            "Creating payment URL",
            extra={
                "telegram_id": telegram_id,
                "db_user_id": db_user_id,
                "amount": amount,
                "period": period,
            },
        )

        try:
            # Create payment URL
            payment_url = await create_payment_form_url(db_user_id, amount, period)

            if not payment_url:
                logger.error(
                    "Failed to create payment URL",
                    extra={
                        "telegram_id": telegram_id,
                        "db_user_id": db_user_id,
                        "amount": amount,
                        "period": period,
                    },
                )
                await callback_query.message.answer(
                    "На жаль, не вдалося створити платіж. Спробуйте пізніше."
                )
                await callback_query.answer()
                return

            logger.info(
                "Payment URL created successfully",
                extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "amount": amount,
                    "period": period,
                    "has_payment_url": bool(payment_url),
                },
            )

            # Send payment link
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Оплатити", url=payment_url))

            await callback_query.message.answer(
                f"Для оплати підписки на {period} натисніть кнопку нижче:",
                reply_markup=keyboard,
            )
            await callback_query.answer()

            logger.info(
                "Payment link sent to user",
                extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "amount": amount,
                    "period": period,
                },
            )

        except Exception as e:
            logger.error(
                "Error during payment processing",
                exc_info=True,
                extra={
                    "telegram_id": telegram_id,
                    "db_user_id": db_user_id,
                    "amount": amount,
                    "period": period,
                    "error": str(e),
                },
            )
            await callback_query.message.answer(
                "Виникла помилка при створенні платежу. Спробуйте пізніше."
            )
            await callback_query.answer()


# store trigger ids for payment menu
PAY_TRIGGER = {}


@dp.callback_query_handler(lambda c: c.data == "payment_back")
@log_operation("payment_back_handler")
async def payment_back_handler(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id

    info = PAY_TRIGGER.pop(telegram_id, None)
    if info:
        if info.get("bot_id"):
            await delete_message_safe(telegram_id, info["bot_id"])
        if info.get("trigger_id"):
            await delete_message_safe(telegram_id, info["trigger_id"])

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await safe_answer_callback_query(callback_query.id)
