# services/webapps/mini_webapp.py

import os
import json
import hashlib
import hmac
from typing import Optional

from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from common.db.session import db_session
from common.db.repositories.payment_repository import PaymentRepository
from common.db.repositories.user_repository import UserRepository
from common.utils.secrets import get_secret
from datetime import datetime, timedelta, timezone

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Get environment variables
MERCHANT_ACCOUNT = os.getenv("WAYFORPAY_MERCHANT_LOGIN")
MERCHANT_SECRET = get_secret("wayforpay_secret", fallback_env="WAYFORPAY_MERCHANT_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

from common.utils.logging_config import setup_logging
from common.utils.log_management import setup_file_logging

# Initialize service-wide logger
logger = setup_logging("webapps_service", log_level="INFO", log_format="text")

# Add file logging if we're in production
if os.getenv("ENVIRONMENT", "development") == "production":
    setup_file_logging(
        logger,
        log_dir="/app/logs/webapps_service",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=5,
        when="d",
        interval=1,
    )

# Initialize FastAPI app
app = FastAPI(
    title="Real Estate Mini Web Apps",
    description="Mini web applications for Telegram and other messaging platforms",
    version="1.0.0",
)

# Initialize templates
templates = Jinja2Templates(directory="templates")

logger.info("FastAPI app initialized for webapps service")


# Define Pydantic models for request validation
class PaymentCallback(BaseModel):
    orderReference: str
    transactionStatus: str
    amount: float
    authCode: Optional[str] = None
    cardPan: Optional[str] = None
    merchantSignature: str


class GalleryQuery(BaseModel):
    images: str = Field(..., description="Comma-separated list of image URLs")


class PhoneQuery(BaseModel):
    numbers: str = Field(..., description="Comma-separated list of phone numbers")


def validate_telegram_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData using HMAC-SHA256.

    Per Telegram docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    1. Parse the init_data query string into key-value pairs
    2. Sort by key, excluding 'hash'
    3. Create data_check_string as "key=value\n..." lines
    4. secret_key = HMAC-SHA256("WebAppData", bot_token)
    5. Verify hash == HMAC-SHA256(secret_key, data_check_string)
    """
    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_TOKEN not configured, cannot validate initData")
        return False

    try:
        from urllib.parse import parse_qs

        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return False

        # Build data_check_string: sorted key=value pairs, excluding 'hash'
        data_pairs = []
        for key, values in parsed.items():
            if key == "hash":
                continue
            data_pairs.append((key, values[0]))
        data_pairs.sort(key=lambda x: x[0])
        data_check_string = "\n".join(f"{k}={v}" for k, v in data_pairs)

        # secret_key = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            b"WebAppData", TELEGRAM_TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()

        # calculated_hash = HMAC-SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(calculated_hash, received_hash)
    except Exception:
        logger.error("Error validating Telegram initData", exc_info=True)
        return False


# HTML templates as strings (if you don't have a templates directory)
GALLERY_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8" />
  <title>Фотогалерея</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 15px;
    }
    h2 {
      margin-bottom: 10px;
    }
    /* The images display at maximum width */
    .gallery-img {
      width: 100%;         /* Full width of container */
      max-width: 100%;     /* No overflow horizontally */
      margin-bottom: 20px;
      cursor: zoom-in;     /* Indicate clickable zoom */
    }
    /* The Modal (background overlay) */
    .modal {
      display: none;       /* Hidden by default */
      position: fixed;     /* Stay in place */
      z-index: 9999;       /* On top */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      overflow: auto;
      background-color: rgba(0,0,0,0.8); /* black w/ opacity */
    }
    /* Modal Image styling */
    .modal-content {
      display: block;
      margin: auto;
      max-width: 90%;
      max-height: 90%;
      box-shadow: 0 0 10px #000;
    }
    /* Close button (top-right) */
    .close {
      position: absolute;
      top: 30px;
      right: 45px;
      color: #fff;
      font-size: 40px;
      font-weight: bold;
      cursor: pointer;
    }
    .close:hover,
    .close:focus {
      color: #bbb;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <h2>Фотогалерея</h2>
  <div id="gallery"></div>

  <!-- The Modal -->
  <div id="myModal" class="modal">
    <span class="close" id="closeBtn">&times;</span>
    <img class="modal-content" id="modalImg">
  </div>

  <script>
    const galleryDiv = document.getElementById("gallery");
    if (!window.Telegram || !window.Telegram.WebApp) {
      galleryDiv.textContent = "Ця сторінка доступна лише через Telegram.";
    } else {
      function isValidImageUrl(url) {
        try {
          const parsed = new URL(url);
          return parsed.protocol === "https:" || parsed.protocol === "http:";
        } catch {
          return false;
        }
      }

      const urlParams = new URLSearchParams(window.location.search);
      const imagesParam = urlParams.get("images"); // e.g. "https://...,https://..."
      if (imagesParam) {
        const imgArray = imagesParam.split(",");
        imgArray.forEach(url => {
          const trimmedUrl = url.trim();
          // Validate URL scheme to prevent javascript: and data: XSS
          if (!isValidImageUrl(trimmedUrl)) return;
          const img = document.createElement("img");
          img.src = trimmedUrl;
          img.className = "gallery-img";
          // On click => open modal
          img.onclick = function() {
            openModal(trimmedUrl);
          };
          galleryDiv.appendChild(img);
        });
      } else {
        galleryDiv.textContent = "Немає зображень.";
      }

      // Modal logic
      const modal = document.getElementById("myModal");
      const modalImg = document.getElementById("modalImg");
      const closeBtn = document.getElementById("closeBtn");

      function openModal(imageUrl) {
        modal.style.display = "block";
        modalImg.src = imageUrl;
      }

      closeBtn.onclick = function() {
        modal.style.display = "none";
      };

      // Close the modal if user clicks outside the image
      window.onclick = function(event) {
        if (event.target === modal) {
          modal.style.display = "none";
        }
      }
    }
  </script>
</body>
</html>
"""

PHONE_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <title>Телефони</title>
  <style>
    body {
      background: #FFF;    /* White page background */
      color: #000;         /* Black default text */
      margin: 15px;
      font-family: Arial, sans-serif;
    }
    h2 {
      margin-bottom: 10px;
    }
    .phone-list {
      /* If you want to control max width of the entire content */
      max-width: 600px;
      margin: 0 auto;    /* Center horizontally */
    }
    /* Each phone link is a block with white background, black text */
    a.phone-link {
      display: block;
      background: #FFF;   /* White background for each link */
      color: #000;        /* Black text */
      text-decoration: none;
      font-size: 20px;    /* Adjust as needed */
      padding: 10px;
      border: 1px solid #AAA;
      border-radius: 4px;
      margin: 10px 0;
      width: 100%;
      box-sizing: border-box; /* So padding doesn't exceed width */
    }
    a.phone-link:hover {
      background: #f9f9f9; /* Slight hover effect */
    }
  </style>
</head>
<body>
  <h2>Телефони</h2>
  <div class="phone-list" id="phone-list"></div>
  <script>
    const phoneDiv = document.getElementById("phone-list");
    if (!window.Telegram || !window.Telegram.WebApp) {
      phoneDiv.textContent = "Ця сторінка доступна лише через Telegram.";
    } else {
      const urlParams = new URLSearchParams(window.location.search);
      const numbersParam = urlParams.get("numbers"); // e.g. "380999999999,380971234567"

      if (numbersParam) {
        const phoneArray = numbersParam.split(",");
        phoneArray.forEach(num => {
          const link = document.createElement("a");
          link.href = "tel:" + num.trim();   // Tapping opens dialer
          link.className = "phone-link";
          link.textContent = num.trim();
          phoneDiv.appendChild(link);
        });
      } else {
        phoneDiv.textContent = "Немає телефонів.";
      }
    }
  </script>
</body>
</html>
"""


@log_operation("verify_wayforpay_signature")
def verify_wayforpay_signature(data: dict) -> bool:
    """Verify WayForPay callback signature"""
    with log_context(logger, operation="signature_verification"):
        if not MERCHANT_SECRET:
            logger.error("Missing WAYFORPAY_MERCHANT_SECRET environment variable")
            return False

        # Extract the signature from the data
        received_signature = data.get("merchantSignature")
        if not received_signature:
            logger.error("Missing merchantSignature in callback data")
            return False

        # Remove the signature from the data
        verification_data = {k: v for k, v in data.items() if k != "merchantSignature"}

        # Sort parameters by key
        keys = sorted(verification_data.keys())
        values = [str(verification_data[key]) for key in keys]
        string_to_sign = ";".join(values)

        # Generate signature
        calculated_signature = hmac.new(
            MERCHANT_SECRET.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.md5
        ).hexdigest()

        # Compare signatures using timing-safe comparison to prevent timing attacks
        if not hmac.compare_digest(calculated_signature, received_signature):
            logger.error(
                "Invalid signature",
                extra={
                    "order_id": data.get("orderReference"),
                },
            )
            return False

        # Verify merchant account
        if data.get("merchantAccount") != MERCHANT_ACCOUNT:
            logger.error(
                "Invalid merchant account",
                extra={
                    "expected": MERCHANT_ACCOUNT,
                    "received": data.get("merchantAccount"),
                },
            )
            return False

        logger.info(
            "Signature verified successfully",
            extra={"merchant_account": MERCHANT_ACCOUNT},
        )
        return True


@app.get("/gallery", response_class=HTMLResponse)
@log_operation("gallery_route")
async def gallery_route(images: str = Query(None, max_length=10000)):
    """Gallery mini-app for viewing images"""
    with log_context(logger, endpoint="gallery"):
        image_count = len(images.split(",")) if images else 0
        if image_count > 50:
            raise HTTPException(status_code=400, detail="Too many images (max 50)")
        logger.info(
            "Gallery page requested",
            extra={
                "has_images": bool(images),
                "image_count": image_count,
            },
        )
        return GALLERY_HTML


@app.get("/phones", response_class=HTMLResponse)
@log_operation("phones_route")
async def phones_route(numbers: str = Query(None, max_length=2000)):
    """Phone numbers mini-app for viewing and calling"""
    with log_context(logger, endpoint="phones"):
        number_count = len(numbers.split(",")) if numbers else 0
        if number_count > 20:
            raise HTTPException(status_code=400, detail="Too many numbers (max 20)")
        logger.info(
            "Phones page requested",
            extra={
                "has_numbers": bool(numbers),
                "number_count": number_count,
            },
        )
        return PHONE_HTML


@app.get("/health")
@log_operation("health_check")
async def health_check():
    """Simple health check endpoint for monitoring"""
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.post("/payment/callback")
@log_operation("payment_callback")
async def payment_callback(payload: PaymentCallback, background_tasks: BackgroundTasks):
    """
    Handle WayForPay payment callbacks with enhanced security and user notifications
    """
    try:
        # Convert Pydantic model to dict
        callback_data = payload.dict()

        with log_context(logger, order_reference=callback_data.get("orderReference")):
            logger.info(
                "Received payment callback",
                extra={
                    "order_reference": callback_data.get("orderReference"),
                    "transaction_status": callback_data.get("transactionStatus"),
                    "amount": callback_data.get("amount"),
                },
            )

            # Verify the signature and merchant account
            if not verify_wayforpay_signature(callback_data):
                logger.error("Payment signature verification failed")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Signature verification failed",
                    },
                )

            # Get order reference
            order_id = callback_data.get("orderReference")
            if not order_id:
                logger.error("Missing orderReference in callback")
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "Missing order reference"},
                )

            # Get transaction status
            transaction_status = callback_data.get("transactionStatus")
            if transaction_status != "Approved":
                logger.info(
                    "Payment not approved",
                    extra={"order_id": order_id, "status": transaction_status},
                )

                # Update payment status in database as a background task
                background_tasks.add_task(
                    update_non_approved_payment_status,
                    order_id,
                    transaction_status,
                    callback_data,
                )

                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "acknowledged",
                        "message": "Non-approved status noted",
                    },
                )

            # Process the approved payment in a background task
            logger.info("Processing approved payment", extra={"order_id": order_id})

            background_tasks.add_task(process_approved_payment, order_id, callback_data)

            # Return success response with expected format for WayForPay
            return JSONResponse(
                status_code=200,
                content={
                    "orderReference": order_id,
                    "status": "accept",
                    "time": int(datetime.now(timezone.utc).timestamp()),
                },
            )

    except Exception as e:
        logger.error(
            "Error in payment callback",
            exc_info=True,
            extra={
                "error_type": type(e).__name__,
                "order_id": (
                    callback_data.get("orderReference")
                    if "callback_data" in locals()
                    else None
                ),
            },
        )
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"},
        )


@log_operation("update_non_approved_payment_status")
async def update_non_approved_payment_status(
    order_id: str, transaction_status: str, callback_data: dict
):
    """Update database with non-approved payment status"""
    with log_context(logger, order_id=order_id, status=transaction_status):
        try:
            from common.db.database import execute_query

            logger.info(
                "Updating non-approved payment status",
                extra={"order_id": order_id, "status": transaction_status},
            )

            sql_update = """
                         UPDATE payment_orders
                         SET status = %s
                         WHERE order_id = %s \
                         """
            execute_query(sql_update, [transaction_status.lower(), order_id])

            # Store in payment history
            sql_history = """
                          INSERT INTO payment_history
                          (user_id, order_id, amount, subscription_period, status, transaction_id, card_mask, \
                           payment_details)
                          SELECT user_id, \
                                 order_id, \
                                 amount, \
                                 period, \
                                 %s, \
                                 %s, \
                                 %s, \
                                 %s
                          FROM payment_orders
                          WHERE order_id = %s \
                          """
            execute_query(
                sql_history,
                [
                    transaction_status.lower(),
                    callback_data.get("authCode", ""),
                    callback_data.get("cardPan", ""),
                    json.dumps(callback_data),
                    order_id,
                ],
            )

            logger.info(
                "Successfully updated non-approved payment status",
                extra={"order_id": order_id, "status": transaction_status},
            )
        except Exception as e:
            logger.error(
                "Error updating non-approved payment status",
                exc_info=True,
                extra={
                    "order_id": order_id,
                    "status": transaction_status,
                    "error_type": type(e).__name__,
                },
            )


@log_operation("process_approved_payment")
async def process_approved_payment(order_id: str, callback_data: dict):
    """Process approved payment and update subscription"""
    with log_context(logger, order_id=order_id):
        try:
            with db_session() as db:
                # Get order details from database using repository
                payment_order = PaymentRepository.get_order_by_id(db, order_id)

                if not payment_order:
                    logger.error("Order not found", extra={"order_id": order_id})
                    return

                user_id = payment_order.user_id
                period = payment_order.period
                amount = payment_order.amount

                logger.info(
                    "Processing payment for user",
                    extra={
                        "order_id": order_id,
                        "user_id": user_id,
                        "period": period,
                        "amount": amount,
                    },
                )

                # Determine subscription duration in days
                period_days = 30  # Default to 30 days
                if period == "3months":
                    period_days = 90
                elif period == "6months":
                    period_days = 180
                elif period == "12months":
                    period_days = 365

                # Update payment status
                payment_order.status = "completed"
                payment_order.updated_at = datetime.now(timezone.utc)
                db.commit()

                logger.info(
                    "Payment status updated to completed", extra={"order_id": order_id}
                )

                # Create payment history entry
                payment_history_data = {
                    "user_id": user_id,
                    "order_id": order_id,
                    "amount": amount,
                    "subscription_period": period,
                    "status": "completed",
                    "transaction_id": callback_data.get("authCode", ""),
                    "card_mask": callback_data.get("cardPan", ""),
                    "payment_details": str(callback_data),
                }

                PaymentRepository.create_payment_history(db, payment_history_data)

                logger.info(
                    "Payment history created",
                    extra={"order_id": order_id, "user_id": user_id},
                )

                # Get the user
                user = UserRepository.get_by_id(db, user_id)

                # Update subscription end date
                if user.subscription_until and user.subscription_until > datetime.now(timezone.utc):
                    # Extend existing subscription
                    user.subscription_until = user.subscription_until + timedelta(
                        days=period_days
                    )
                else:
                    # Set new subscription
                    user.subscription_until = datetime.now(timezone.utc) + timedelta(
                        days=period_days
                    )

                db.commit()

                logger.info(
                    "Updated subscription end date",
                    extra={
                        "user_id": user_id,
                        "subscription_until": user.subscription_until.isoformat(),
                        "period_days": period_days,
                    },
                )

                # Format the date for notification
                sub_date = user.subscription_until.strftime("%d.%m.%Y")

                # Determine which messenger to use
                messenger_type = None
                messenger_id = None
                task_name = None

                if user.telegram_id:
                    messenger_type = "telegram"
                    messenger_id = user.telegram_id
                    task_name = (
                        "telegram_service.app.tasks.send_subscription_notification"
                    )

                if messenger_type and messenger_id and task_name:
                    # Send success notification via Celery task
                    from common.celery_app import celery_app

                    celery_app.send_task(
                        task_name,
                        args=[
                            messenger_id,
                            "payment_success",
                            {
                                "order_id": order_id,
                                "amount": amount,
                                "subscription_until": sub_date,
                            },
                        ],
                    )
                    logger.info(
                        "Payment notification sent",
                        extra={
                            "messenger_type": messenger_type,
                            "messenger_id": messenger_id,
                            "user_id": user_id,
                        },
                    )
                else:
                    logger.warning(
                        "No messenger available for payment notification",
                        extra={"user_id": user_id},
                    )

        except Exception as e:
            logger.error(
                "Error processing payment",
                exc_info=True,
                extra={"order_id": order_id, "error_type": type(e).__name__},
            )


@app.on_event("startup")
async def startup_event():
    """Log startup event"""
    logger.info(
        "Webapps service starting up",
        extra={"app_title": app.title, "app_version": app.version},
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event"""
    logger.info("Webapps service shutting down")


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "Starting mini web apps service with FastAPI...",
        extra={"host": "0.0.0.0", "port": 8080},
    )
    uvicorn.run("mini_webapp:app", host="0.0.0.0", port=8080, reload=False)
