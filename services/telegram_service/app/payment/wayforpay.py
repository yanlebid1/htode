# services/telegram_service/app/payment/wayforpay.py

import hashlib
import time
import os
import hmac
from typing import Dict, Any, Optional
import aiohttp

from common.db.models import Payment
from common.db.repositories import PaymentRepository
from common.db.session import db_session

# Import service logger
from .. import logger
from common.utils.logging_config import log_operation, log_context

# Replace it with your actual merchant credentials from WayForPay
MERCHANT_ACCOUNT = os.getenv("WAYFORPAY_MERCHANT_LOGIN")
MERCHANT_SECRET = os.getenv("WAYFORPAY_MERCHANT_SECRET")
API_URL = "https://api.wayforpay.com/api"


@log_operation("generate_signature")
def generate_signature(data: Dict[str, Any]) -> str:
    """Generate HMAC signature for WayForPay API"""
    with log_context(logger, merchant_account=MERCHANT_ACCOUNT):
        logger.debug("Generating signature", extra={"data_keys": list(data.keys())})

        keys = sorted(data.keys())
        values = [str(data[key]) for key in keys]
        string = ";".join(values)

        signature = hmac.new(
            MERCHANT_SECRET.encode("utf-8"), string.encode("utf-8"), hashlib.md5
        ).hexdigest()

        logger.debug("Signature generated", extra={"signature_length": len(signature)})

        return signature


@log_operation("create_payment_request")
def create_payment_request(
    user_id: int, amount: float, order_id: str, product_name: str
) -> Dict[str, Any]:
    """Create payment request data for WayForPay"""
    with log_context(logger, user_id=user_id, order_id=order_id):
        logger.info(
            "Creating payment request",
            extra={
                "user_id": user_id,
                "amount": amount,
                "order_id": order_id,
                "product_name": product_name,
            },
        )

        order_date = int(time.time())

        data = {
            "merchantAccount": MERCHANT_ACCOUNT,
            "merchantDomainName": "yourdomain.com",  # Your domain
            "merchantTransactionType": "CHARGE",
            "merchantTransactionSecureType": "AUTO",
            "orderReference": order_id,
            "orderDate": order_date,
            "amount": amount,
            "currency": "UAH",
            "productName": [product_name],
            "productCount": [1],
            "productPrice": [amount],
            "clientFirstName": f"User{user_id}",
            "clientLastName": "",
            "clientEmail": "",  # You can add user email if available
            "clientPhone": "",  # You can add user phone if available
            "language": "UA",
            "returnUrl": "https://t.me/YourBotUsername",  # Your bot URL
            "serviceUrl": "https://yourdomain.com/payment/callback",  # Your server callback URL
        }

        data["merchantSignature"] = generate_signature(data)

        logger.debug(
            "Payment request created",
            extra={"user_id": user_id, "order_id": order_id, "order_date": order_date},
        )

        return data


@log_operation("create_payment_form_url")
async def create_payment_form_url(
    user_id: int, amount: float, period: str = "1 month"
) -> Optional[str]:
    """
    Create payment URL for the user

    Args:
        user_id: Telegram user ID
        amount: Payment amount in UAH
        period: Subscription period

    Returns:
        Payment form URL or None if failed
    """
    with log_context(logger, user_id=user_id, amount=amount, period=period):
        try:
            order_id = f"sub_{user_id}_{int(time.time())}"
            product_name = f"Subscription for {period}"

            logger.info(
                "Creating payment URL",
                extra={
                    "user_id": user_id,
                    "amount": amount,
                    "period": period,
                    "order_id": order_id,
                },
            )

            # Create payment data
            payment_data = create_payment_request(
                user_id, amount, order_id, product_name
            )

            # Send request asynchronously
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.debug(
                    "Sending request to WayForPay",
                    extra={"url": f"{API_URL}/payment", "order_id": order_id},
                )

                async with session.post(
                    f"{API_URL}/payment", json=payment_data
                ) as resp:
                    status = resp.status
                    logger.debug(
                        "WayForPay response received",
                        extra={"status_code": status, "order_id": order_id},
                    )

                    if status == 200:
                        result = await resp.json()

                        if result.get("reason") == "ok":
                            # Store order in database for callback handling
                            store_payment_order(user_id, order_id, amount, period)
                            invoice_url = result.get("invoiceUrl")

                            logger.info(
                                "Payment URL created successfully",
                                extra={
                                    "user_id": user_id,
                                    "order_id": order_id,
                                    "has_invoice_url": bool(invoice_url),
                                },
                            )

                            return invoice_url

                    logger.error(
                        "Payment creation failed",
                        extra={
                            "user_id": user_id,
                            "order_id": order_id,
                            "response_status": status,
                        },
                    )
                    return None

        except Exception as e:
            logger.error(
                "Error creating payment",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "amount": amount,
                    "period": period,
                    "error": str(e),
                },
            )
            return None


@log_operation("store_payment_order")
def store_payment_order(
    user_id: int, order_id: str, amount: float, period: str
) -> Optional[Payment]:
    """
    Store payment order in database for later verification.
    Updated to use unified Payment model.
    """
    with log_context(logger, user_id=user_id, order_id=order_id):
        try:
            with db_session() as db:
                payment = PaymentRepository.create_payment(
                    db=db,
                    user_id=user_id,
                    order_id=order_id,
                    amount=amount,
                    period=period,
                )

                logger.info(
                    "Payment order stored successfully",
                    extra={
                        "payment_id": payment.id,
                        "user_id": user_id,
                        "order_id": order_id,
                    },
                )

                return payment
        except Exception as e:
            logger.error(
                "Failed to store payment order",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "order_id": order_id,
                    "error_type": type(e).__name__,
                },
            )
            return None


@log_operation("verify_payment_callback")
def verify_payment_callback(callback_data: Dict[str, Any]) -> bool:
    """Verify payment callback from WayForPay"""
    with log_context(logger, order_id=callback_data.get("orderReference")):
        logger.info(
            "Verifying payment callback",
            extra={
                "order_id": callback_data.get("orderReference"),
                "transaction_status": callback_data.get("transactionStatus"),
            },
        )

        # Verify signature
        received_signature = callback_data.get("merchantSignature")
        if not received_signature:
            logger.warning(
                "No signature in callback data",
                extra={"order_id": callback_data.get("orderReference")},
            )
            return False

        # Remove signature from data for calculation
        verification_data = {
            k: v for k, v in callback_data.items() if k != "merchantSignature"
        }

        # Calculate signature
        calculated_signature = generate_signature(verification_data)

        # Compare signatures using timing-safe comparison to prevent timing attacks
        if not hmac.compare_digest(calculated_signature, received_signature):
            logger.warning(
                "Invalid payment signature",
                extra={
                    "order_id": callback_data.get("orderReference"),
                },
            )
            return False

        # Verify merchant account
        if callback_data.get("merchantAccount") != MERCHANT_ACCOUNT:
            logger.warning(
                "Invalid merchant account",
                extra={
                    "order_id": callback_data.get("orderReference"),
                    "received_account": callback_data.get("merchantAccount"),
                    "expected_account": MERCHANT_ACCOUNT,
                },
            )
            return False

        # Verify transaction status
        if callback_data.get("transactionStatus") != "Approved":
            logger.info(
                "Payment not approved",
                extra={
                    "order_id": callback_data.get("orderReference"),
                    "transaction_status": callback_data.get("transactionStatus"),
                },
            )
            return False

        logger.info(
            "Payment callback verified successfully",
            extra={"order_id": callback_data.get("orderReference")},
        )
        return True


@log_operation("process_successful_payment")
def process_successful_payment(
    order_id: str, transaction_details: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Process successful payment and update subscription.
    Updated to use a unified Payment model with transaction details.
    """
    with log_context(logger, order_id=order_id):
        try:
            with db_session() as db:
                # Get payment details
                payment = PaymentRepository.get_payment_by_order_id(db, order_id)

                if not payment:
                    logger.error("Payment not found", extra={"order_id": order_id})
                    return False

                # Update payment status
                updated_payment = PaymentRepository.update_payment_status(
                    db=db,
                    order_id=order_id,
                    status="completed",
                    transaction_id=(
                        transaction_details.get("transaction_id")
                        if transaction_details
                        else None
                    ),
                    card_mask=(
                        transaction_details.get("card_mask")
                        if transaction_details
                        else None
                    ),
                    payment_details=transaction_details,
                )

                if not updated_payment:
                    logger.error(
                        "Failed to update payment status", extra={"order_id": order_id}
                    )
                    return False

                # Update user subscription
                from common.db.operations import enable_subscription_for_user

                enable_subscription_for_user(payment.user_id)

                logger.info(
                    "Payment processed successfully",
                    extra={
                        "order_id": order_id,
                        "user_id": payment.user_id,
                        "amount": payment.amount,
                    },
                )

                return True

        except Exception as e:
            logger.error(
                "Error processing payment",
                exc_info=True,
                extra={"order_id": order_id, "error_type": type(e).__name__},
            )
            return False
