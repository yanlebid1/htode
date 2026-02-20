# common/config.py
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Load .env file if it exists
load_dotenv()

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "myuser"),
    "password": os.getenv("DB_PASS", "mypass"),
    "dbname": os.getenv("DB_NAME", "mydb"),
}

# PgBouncer override — route DB traffic through the connection pooler
DB_CONFIG["host"] = os.getenv("DB_PGBOUNCER_HOST", DB_CONFIG["host"])

# AWS Configuration
AWS_CONFIG = {
    "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
    "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
    "region": os.getenv("AWS_DEFAULT_REGION", "eu-west-1"),
    "s3_bucket": os.getenv("AWS_S3_BUCKET", "htodebucket"),
    "s3_prefix": os.getenv("AWS_S3_BUCKET_PREFIX", "ads-images/"),
    "cloudfront_domain": os.getenv("CLOUDFRONT_DOMAIN"),
}

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# TODO: I receive an error while passing token for bot creating. Nonetype is received for some reason. Check logs.

# WebApp Configuration - Use internal Docker network if not provided
WEBAPP_URL = "https://c3df-178-150-42-6.ngrok-free.app"
# os.getenv("WEBAPP_URL", "https://8b74-178-150-42-6.ngrok-free.app")

# Geo ID Mappings
GEO_ID_MAPPING = {
    10012684: "Львів",
    10006463: "Дніпро",
    10003908: "Вінниця",
    10007252: "Житомир",
    10007846: "Запоріжжя",
    10008717: "Івано-Франківськ",
    10016589: "Одеса",
    10009580: "Київ",
    514141: "Київ (передмістя)",
    10011240: "Кропивницький",
    10012656: "Луцьк",
    10013982: "Миколаїв",
    10018885: "Полтава",
    10019894: "Рівне",
    10022820: "Суми",
    10023304: "Тернопіль",
    10023968: "Ужгород",
    10024345: "Харків",
    10024395: "Херсон",
    10024474: "Хмельницький",
    10025145: "Черкаси",
    10025207: "Чернівці",
    10025209: "Чернігів",
}

# For initial run
GEO_ID_MAPPING_FOR_INITIAL_RUN = {10012684: "Львів"}


def get_key_by_value(value: str, geo_id_mapping: Dict[int, str]) -> Optional[int]:
    """Get geo ID by city name"""
    return next((k for k, v in geo_id_mapping.items() if v == value), None)


def build_ad_text(ad_row: Dict[str, Any], markdown: bool = False) -> str:
    """Build a formatted text for an ad listing.

    Args:
        ad_row: Dictionary with ad data. Supports both DB-style keys (city as geo_id)
                and pre-resolved city names (city as string).
        markdown: If True, wrap values in Telegram Markdown bold (*value*).

    Returns:
        Formatted ad text string.
    """
    # Resolve city: if it's an int (geo_id), look up the name; otherwise use as-is
    city_raw = ad_row.get("city")
    if isinstance(city_raw, int):
        city_name = GEO_ID_MAPPING.get(city_raw, "Невідомо")
    else:
        city_name = city_raw or "Невідомо"

    price = int(ad_row.get("price", 0))
    address = ad_row.get("address", "Не вказано")
    rooms_count = ad_row.get("rooms_count", "?")
    square_feet = ad_row.get("square_feet", "?")
    floor = ad_row.get("floor", "?")
    total_floors = ad_row.get("total_floors", "?")

    if markdown:
        text = (
            f"💰 Ціна: *{price}* грн.\n"
            f"🏙️ Місто: *{city_name}*\n"
            f"📍 Адреса: *{address}*\n"
            f"🛏️ Кіл-сть кімнат: *{rooms_count}*\n"
            f"📐 Площа: *{square_feet}* кв.м.\n"
            f"🏢 Поверх: *{floor}* з *{total_floors}*\n"
        )
    else:
        text = (
            f"💰 Ціна: {price} грн.\n"
            f"🏙️ Місто: {city_name}\n"
            f"📍 Адреса: {address}\n"
            f"🛏️ Кіл-сть кімнат: {rooms_count}\n"
            f"📐 Площа: {square_feet} кв.м.\n"
            f"🏢 Поверх: {floor} из {total_floors}\n"
        )
    return text
