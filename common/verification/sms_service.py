# common/verification/sms_service.py

import os
from common.utils.logging_config import log_operation, log_context

# Import the common verification logger
from . import logger

# Environment variables for SMS service configuration
SMS_SERVICE_ENABLED = os.getenv("SMS_SERVICE_ENABLED", "false").lower() == "true"
SMS_SERVICE_PROVIDER = os.getenv("SMS_SERVICE_PROVIDER", "twilio")  # Options: twilio, nexmo, test
SMS_SERVICE_DEBUG = os.getenv("SMS_SERVICE_DEBUG", "false").lower() == "true"

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Nexmo (Vonage) credentials
NEXMO_API_KEY = os.getenv("NEXMO_API_KEY")
NEXMO_API_SECRET = os.getenv("NEXMO_API_SECRET")
NEXMO_BRAND_NAME = os.getenv("NEXMO_BRAND_NAME", "ReEstateFinder")


@log_operation("send_verification_code")
def send_verification_code(phone_number: str, code: str) -> bool:
    """
    Send a verification code to the specified phone number.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    with log_context(logger, phone_number=phone_number, provider=SMS_SERVICE_PROVIDER, enabled=SMS_SERVICE_ENABLED):
        if not SMS_SERVICE_ENABLED:
            # If SMS service is disabled, log the code for testing
            logger.info("SMS Service DISABLED", extra={
                'phone_number': phone_number,
                'code': code,
                'action': 'would_send'
            })
            return True

        # Choose the SMS provider
        if SMS_SERVICE_PROVIDER == "twilio":
            return _send_via_twilio(phone_number, code)
        elif SMS_SERVICE_PROVIDER == "nexmo":
            return _send_via_nexmo(phone_number, code)
        elif SMS_SERVICE_PROVIDER == "test":
            return _send_via_test(phone_number, code)
        else:
            logger.error("Unknown SMS provider", extra={
                'provider': SMS_SERVICE_PROVIDER,
                'phone_number': phone_number
            })
            return False


@log_operation("send_via_twilio")
def _send_via_twilio(phone_number: str, code: str) -> bool:
    """
    Send a verification code using Twilio.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    with log_context(logger, phone_number=phone_number, provider='twilio'):
        try:
            from twilio.rest import Client

            # Check for required credentials
            if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
                logger.error("Missing Twilio credentials", extra={
                    'has_account_sid': bool(TWILIO_ACCOUNT_SID),
                    'has_auth_token': bool(TWILIO_AUTH_TOKEN),
                    'has_phone_number': bool(TWILIO_PHONE_NUMBER)
                })
                return False

            # Initialize Twilio client
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

            # Prepare the message
            message_text = f"Your RealEstateFinder verification code: {code}"

            # Send the message
            message = client.messages.create(
                body=message_text,
                from_=TWILIO_PHONE_NUMBER,
                to=phone_number
            )

            logger.info("Sent verification code via Twilio", extra={
                'phone_number': phone_number,
                'message_sid': message.sid,
                'from_number': TWILIO_PHONE_NUMBER
            })
            return True

        except ImportError:
            logger.error("Twilio package not installed", extra={
                'phone_number': phone_number
            })
            return False
        except Exception as e:
            logger.error("Failed to send SMS via Twilio", exc_info=True, extra={
                'phone_number': phone_number,
                'error_type': type(e).__name__
            })
            return False


@log_operation("send_via_nexmo")
def _send_via_nexmo(phone_number: str, code: str) -> bool:
    """
    Send a verification code using Nexmo (Vonage).

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    with log_context(logger, phone_number=phone_number, provider='nexmo'):
        try:
            import vonage

            # Check for required credentials
            if not all([NEXMO_API_KEY, NEXMO_API_SECRET]):
                logger.error("Missing Nexmo credentials", extra={
                    'has_api_key': bool(NEXMO_API_KEY),
                    'has_api_secret': bool(NEXMO_API_SECRET)
                })
                return False

            # Initialize Nexmo client
            client = vonage.Client(key=NEXMO_API_KEY, secret=NEXMO_API_SECRET)
            sms = vonage.Sms(client)

            # Prepare the message
            message_text = f"Your RealEstateFinder verification code: {code}"

            # Send the message
            response = sms.send_message({
                'from': NEXMO_BRAND_NAME,
                'to': phone_number,
                'text': message_text
            })

            # Check the response
            if response["messages"][0]["status"] == "0":
                logger.info("Sent verification code via Nexmo", extra={
                    'phone_number': phone_number,
                    'message_id': response["messages"][0].get("message-id"),
                    'from_name': NEXMO_BRAND_NAME
                })
                return True
            else:
                error = response["messages"][0]["error-text"]
                logger.error("Failed to send SMS via Nexmo", extra={
                    'phone_number': phone_number,
                    'error': error,
                    'status': response["messages"][0]["status"]
                })
                return False

        except ImportError:
            logger.error("Vonage package not installed", extra={
                'phone_number': phone_number
            })
            return False
        except Exception as e:
            logger.error("Failed to send SMS via Nexmo", exc_info=True, extra={
                'phone_number': phone_number,
                'error_type': type(e).__name__
            })
            return False


@log_operation("send_via_test")
def _send_via_test(phone_number: str, code: str) -> bool:
    """
    Test SMS provider that just logs the message.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        Always returns True
    """
    with log_context(logger, phone_number=phone_number, provider='test', debug=SMS_SERVICE_DEBUG):
        message_text = f"Your RealEstateFinder verification code: {code}"
        logger.info("TEST SMS", extra={
            'phone_number': phone_number,
            'message': message_text,
            'code': code,
            'action': 'would_send'
        })

        # Store the code in a file if in debug mode
        if SMS_SERVICE_DEBUG:
            try:
                filename = f"sms_code_{phone_number.replace('+', '')}.txt"
                with open(filename, "w") as f:
                    f.write(code)
                logger.debug("Wrote code to debug file", extra={
                    'phone_number': phone_number,
                    'filename': filename
                })
            except Exception as e:
                logger.error("Failed to write debug SMS code to file", exc_info=True, extra={
                    'phone_number': phone_number,
                    'error_type': type(e).__name__
                })

        return True