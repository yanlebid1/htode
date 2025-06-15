# services/scraper_service/app/tasks.py

from datetime import datetime, timedelta, timezone
import boto3
import uuid
from redis import Redis
from contextlib import contextmanager

from common.db.session import db_session
from common.utils.unified_request_utils import fetch_ads_flatfy
from common.config import GEO_ID_MAPPING_FOR_INITIAL_RUN, AWS_CONFIG, REDIS_URL
from common.celery_app import celery_app
from common.utils.unified_request_utils import make_request
from common.utils.ad_utils import process_and_insert_ad
from common.db.repositories.subscription_repository import SubscriptionRepository
from common.db.repositories.ad_repository import AdRepository
from common.db.models import Ad
from sqlalchemy import func

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation, LogAggregator

# Import the service logger
from . import logger
# ---------------------------
# Configuration & Initialization
# ---------------------------

redis_client = Redis.from_url(REDIS_URL)


@log_operation("acquire_lock")
def acquire_lock(lock_name, expire_time=3600):
    """
    Acquire a Redis lock with the given name and expiration time.
    """
    lock_key = f"lock:{lock_name}"
    lock_id = str(uuid.uuid4())

    with log_context(logger, lock_name=lock_name, lock_key=lock_key, lock_id=lock_id):
        try:
            # Try to acquire the lock
            acquired = redis_client.set(lock_key, lock_id, ex=expire_time, nx=True)

            if acquired:
                logger.info(f"Lock acquired", extra={
                    'lock_name': lock_name,
                    'lock_id': lock_id,
                    'expire_time': expire_time
                })
                return lock_id
            else:
                logger.info(f"Lock already held", extra={
                    'lock_name': lock_name
                })
                return None

        except Exception as e:
            logger.error(f"Error acquiring lock", exc_info=True, extra={
                'lock_name': lock_name,
                'error_type': type(e).__name__
            })
            return None


@log_operation("release_lock")
def release_lock(lock_name, lock_id):
    """
    Release a Redis lock if it is still held by us.
    """
    lock_key = f"lock:{lock_name}"

    with log_context(logger, lock_name=lock_name, lock_key=lock_key, lock_id=lock_id):
        try:
            # Use a Lua script to atomically check and delete the lock
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            result = redis_client.eval(script, 1, lock_key, lock_id)

            if result:
                logger.info(f"Lock released", extra={
                    'lock_name': lock_name,
                    'lock_id': lock_id
                })
                return True
            else:
                logger.warning(f"Lock not released", extra={
                    'lock_name': lock_name,
                    'lock_id': lock_id,
                    'reason': 'not owned or already expired'
                })
                return False

        except Exception as e:
            logger.error(f"Error releasing lock", exc_info=True, extra={
                'lock_name': lock_name,
                'lock_id': lock_id,
                'error_type': type(e).__name__
            })
            return False


@contextmanager
def redis_lock(lock_name, expire_time=3600):
    """
    Context manager for Redis locks.

    Args:
        lock_name: Name of the lock
        expire_time: Lock expiration time in seconds

    Yields:
        tuple: (acquired, lock_id) where acquired is True if lock was acquired
    """
    lock_key = f"lock:{lock_name}"
    lock_id = str(uuid.uuid4())

    # Try to acquire the lock
    acquired = redis_client.set(lock_key, lock_id, ex=expire_time, nx=True)

    with log_context(logger, lock_name=lock_name, lock_id=lock_id, acquired=acquired):
        if acquired:
            logger.info(f"Acquired lock {lock_name}", extra={'lock_id': lock_id, 'expire_time': expire_time})
        else:
            logger.info(f"Failed to acquire lock {lock_name}", extra={'lock_key': lock_key})

        try:
            yield acquired, lock_id
        finally:
            # Release the lock if we acquired it
            if acquired:
                pipe = redis_client.pipeline()
                pipe.get(lock_key)
                pipe.delete(lock_key)
                key_val, _ = pipe.execute()

                if key_val and key_val.decode() != lock_id:
                    logger.error(f"Lock {lock_key} was stolen",
                                 extra={'expected_id': lock_id, 'found_id': key_val.decode()})
                else:
                    logger.info(f"Released lock {lock_name}", extra={'lock_id': lock_id})


# Initialize boto3 S3 client (using AWS_CONFIG from common/config.py)
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_CONFIG["access_key"],
    aws_secret_access_key=AWS_CONFIG["secret_key"],
    region_name=AWS_CONFIG["region"]
)


# ---------------------------
# Celery Tasks and Scraper Functions
# ---------------------------

@celery_app.task(name="scraper_service.app.tasks.fetch_new_ads")
@log_operation("fetch_new_ads")
def fetch_new_ads() -> None:
    with log_context(logger, task="fetch_new_ads", service="scraper"):
        try:
            with db_session() as db:
                active_cities = SubscriptionRepository.get_active_cities(db)

                if not active_cities:
                    logger.info("No subscribed cities found", extra={'cities_count': 0})
                    return

                aggregator = LogAggregator(logger, "fetch_new_ads")

                for city in active_cities:
                    with log_context(logger, city_id=city):
                        try:
                            ads_processed = _scrape_ads_for_city(city)
                            aggregator.add_item(
                                {'city_id': city, 'ads_processed': ads_processed},
                                success=True
                            )
                        except Exception as e:
                            aggregator.add_error(str(e), {'city_id': city})
                            logger.error(f"Failed to scrape city {city}", exc_info=True, extra={'city_id': city})

                aggregator.log_summary()

        except Exception as e:
            logger.error("Failed to fetch new ads", exc_info=True, extra={'error_type': type(e).__name__})
            raise


@log_operation("scrape_city")
def _scrape_ads_for_city(geo_id: int) -> int:
    """
    Scrapes ads for a given city (geo_id) and returns the count of processed ads
    """
    total_processed = 0
    property_types = {'apartment': 2}
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with log_context(logger, geo_id=geo_id, operation="scrape_city"):
        for property_type, section_id in property_types.items():
            page = 1

            with log_context(logger, property_type=property_type, section_id=section_id):
                aggregator = LogAggregator(logger, f"scrape_city_{geo_id}_{property_type}")

                while True:
                    try:
                        ads = _scrape_ads_from_page(geo_id, section_id, page)
                        if not ads:
                            logger.debug(f"No more ads on page {page}", extra={'page': page, 'geo_id': geo_id})
                            break

                        found_new = False
                        for ad in ads:
                            inserted_id = _insert_ad_if_new(ad, geo_id, property_type, cutoff_time)
                            if inserted_id:
                                found_new = True
                                total_processed += 1
                                aggregator.add_item({'ad_id': inserted_id}, success=True)

                        if not found_new:
                            logger.info(f"No new ads found on page {page}", extra={'page': page, 'geo_id': geo_id})
                            break
                        page += 1

                    except Exception as e:
                        logger.error(f"Error scraping page {page}", exc_info=True, extra={
                            'page': page,
                            'geo_id': geo_id,
                            'property_type': property_type,
                            'error_type': type(e).__name__
                        })
                        break

                aggregator.log_summary()

    return total_processed


@log_operation("scrape_ads_page")
def _scrape_ads_from_page(geo_id: int, section_id: int, page: int) -> list:
    """
    Scrapes ads from a single page based on provided parameters.
    """
    base_url = "https://flatfy.ua/api/realties"
    params = {
        "currency": "UAH",
        "geo_id": geo_id,
        "group_collapse": 1,
        "has_eoselia": "false",
        "is_without_fee": "false",
        "lang": "uk",
        "page": page,
        "price_sqm_currency": "UAH",
        "section_id": section_id,
        "sort": "insert_time"
    }

    with log_context(logger, geo_id=geo_id, section_id=section_id, page=page):
        try:
            logger.debug(f"Scraping page from Flatfy API", extra={
                'url': base_url,
                'params': params
            })

            response = make_request(
                url=base_url,
                method='get',
                params=params,
                timeout=15,
                retries=5
            )

            if not response:
                logger.warning("No response from Flatfy API", extra={
                    'geo_id': geo_id,
                    'section_id': section_id,
                    'page': page
                })
                return []

            data = response.json()
            ads = data.get("data", [])

            logger.info(f"Successfully scraped page", extra={
                'ads_count': len(ads),
                'geo_id': geo_id,
                'page': page
            })

            return ads

        except Exception as e:
            logger.error(f"Failed to scrape page", exc_info=True, extra={
                'geo_id': geo_id,
                'section_id': section_id,
                'page': page,
                'error_type': type(e).__name__
            })
            return []


@log_operation("insert_ad_if_new")
def _insert_ad_if_new(ad_data: dict, geo_id: int, property_type: str, cutoff_time: datetime) -> int:
    """
    Checks if an ad is new and inserts it into the database.
    """
    with db_session() as db:
        # Get external ID
        ad_unique_id = str(ad_data.get("id", ""))

        with log_context(logger, ad_id=ad_unique_id, geo_id=geo_id):
            if not ad_unique_id:
                logger.warning("Ad missing ID, skipping", extra={'ad_data': ad_data})
                return None

            # Check recency
            last_update_time_str = ad_data.get("download_time")
            if last_update_time_str:
                try:
                    last_update_time = datetime.fromisoformat(last_update_time_str)

                    if last_update_time < cutoff_time:
                        logger.debug(f"Ad too old, skipping", extra={
                            'ad_id': ad_unique_id,
                            'update_time': last_update_time_str,
                            'cutoff_time': cutoff_time.isoformat()
                        })
                        return None

                except ValueError as e:
                    logger.warning(f"Invalid date format in ad data", extra={
                        'ad_id': ad_unique_id,
                        'date_str': last_update_time_str,
                        'error': str(e)
                    })
                    return None

            # Check if the ad already exists
            existing_ad = AdRepository.get_by_external_id(db, ad_unique_id)
            if existing_ad:
                logger.debug(f"Ad already exists", extra={'ad_id': ad_unique_id})
                return None

            # Insert new ad
            logger.info(f"Inserting new ad", extra={
                'ad_id': ad_unique_id,
                'property_type': property_type,
                'geo_id': geo_id
            })

            return process_and_insert_ad(ad_data, property_type, geo_id)


@celery_app.task(name="scraper_service.app.tasks.handle_new_records")
@log_operation("handle_new_records")
def handle_new_records(ad_ids: list) -> None:
    """Handler for newly inserted ad IDs."""
    with log_context(logger, ad_ids_count=len(ad_ids)):
        logger.info(f"Processing new ad records", extra={'ad_ids': ad_ids[:10]})  # Log first 10 IDs

        if not ad_ids:
            logger.info("No ad IDs to process", extra={'action': 'skip'})
            return

        try:
            with db_session() as db:
                new_ads = []

                for ad_id in ad_ids:
                    try:
                        ad = AdRepository.get_full_ad_data(db, ad_id)
                        if ad:
                            new_ads.append(ad)
                        else:
                            logger.warning(f"Ad not found in database", extra={'ad_id': ad_id})
                    except Exception as e:
                        logger.error(f"Error fetching ad data", exc_info=True, extra={
                            'ad_id': ad_id,
                            'error_type': type(e).__name__
                        })

                if not new_ads:
                    logger.info("No valid ads found", extra={'ad_ids': ad_ids})
                    return

                # Dispatch to notifier service
                celery_app.send_task("notifier_service.app.tasks.sort_and_notify_new_ads", args=[new_ads])

                logger.info("Dispatched ads to notifier", extra={
                    'ads_count': len(new_ads),
                    'task': 'sort_and_notify_new_ads'
                })

        except Exception as e:
            logger.error(f"Error handling new records", exc_info=True, extra={
                'ad_ids_count': len(ad_ids),
                'error_type': type(e).__name__
            })


@log_operation("check_initial_load")
def is_initial_load_done() -> bool:
    """Checks if the initial ad load has been completed."""
    try:
        with db_session() as db:
            count = db.query(func.count(Ad.id)).scalar()
            logger.info(f"Checking initial load status", extra={'ad_count': count})
            return count > 0

    except Exception as e:
        logger.error(f"Error checking initial load status", exc_info=True, extra={
            'error_type': type(e).__name__
        })
        return False  # Safer to return False if we can't determine


@celery_app.task(name="scraper_service.app.tasks.initial_30_day_scrape")
@log_operation("initial_30_day_scrape")
def initial_30_day_scrape() -> None:
    if is_initial_load_done():
        logger.info("Initial load already completed", extra={'action': 'skip'})
        return

    with redis_lock("initial_scrape", expire_time=3600) as (acquired, lock_id):
        if not acquired:
            logger.info("Initial scrape already in progress", extra={'action': 'skip'})
            return

        with log_context(logger, lock_id=lock_id, operation="initial_scrape"):
            aggregator = LogAggregator(logger, "initial_30_day_scrape")

            for city_id, city_name in GEO_ID_MAPPING_FOR_INITIAL_RUN.items():
                with log_context(logger, city_id=city_id, city_name=city_name):
                    try:
                        logger.info(f"Starting scrape for city", extra={'city_id': city_id, 'city_name': city_name})
                        ads_count = scrape_30_days_for_city(city_id)
                        aggregator.add_item(
                            {'city_id': city_id, 'city_name': city_name, 'ads_count': ads_count}
                        )
                    except Exception as e:
                        aggregator.add_error(str(e), {'city_id': city_id})
                        logger.error(f"Failed to scrape city", exc_info=True, extra={
                            'city_id': city_id,
                            'city_name': city_name,
                            'error_type': type(e).__name__
                        })

            aggregator.log_summary()


@log_operation("scrape_30_days")
def scrape_30_days_for_city(geo_id: int) -> int:
    """
    Scrapes ads for the past 30 days for a given city.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=1)
    property_types = {'apartment': 2}  # Extend as needed.
    total_ads_processed = 0

    with log_context(logger, geo_id=geo_id, cutoff_date=cutoff_date.isoformat()):
        for property_type, section_id in property_types.items():
            page_number = 1
            ads_qty = 0

            with log_context(logger, property_type=property_type, section_id=section_id):
                aggregator = LogAggregator(logger, f"scrape_30_days_{geo_id}_{property_type}")

                while True:
                    if ads_qty > 10:
                        logger.info(f"Reached ad limit for initial scrape", extra={
                            'ads_qty': ads_qty,
                            'limit': 10
                        })
                        break

                    try:
                        data = fetch_ads_flatfy(geo_id=geo_id, page=page_number, section_id=section_id)

                        if not data:
                            logger.info(f"No more data on page", extra={'page': page_number})
                            break

                        any_newer = False
                        for ad in data:
                            try:
                                ad_time = parse_date(ad["insert_time"])

                                if ad_time >= cutoff_date:
                                    ads_qty += 1
                                    insert_ad(ad, property_type, geo_id)
                                    any_newer = True
                                    aggregator.add_item({'ad_id': ad.get('id')}, success=True)
                                else:
                                    logger.debug(f"Ad older than cutoff", extra={
                                        'ad_id': ad.get('id'),
                                        'ad_time': ad_time.isoformat(),
                                        'cutoff': cutoff_date.isoformat()
                                    })
                                    any_newer = False
                                    break

                            except Exception as e:
                                logger.error(f"Error processing ad", exc_info=True, extra={
                                    'ad_id': ad.get('id'),
                                    'error_type': type(e).__name__
                                })
                                aggregator.add_error(str(e), {'ad_id': ad.get('id')})

                        if not any_newer:
                            logger.info(f"No newer ads found", extra={'page': page_number})
                            break

                        page_number += 1

                    except Exception as e:
                        logger.error(f"Error fetching page", exc_info=True, extra={
                            'page': page_number,
                            'error_type': type(e).__name__
                        })
                        break

                aggregator.log_summary()
                total_ads_processed += ads_qty

        return total_ads_processed


@log_operation("parse_date")
def parse_date(date_str: str) -> datetime:
    """
    Parses an ISO-format date string into a timezone-aware datetime object.
    """
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S+00:00").replace(tzinfo=timezone.utc)
        logger.debug(f"Successfully parsed date", extra={
            'input': date_str,
            'output': parsed_date.isoformat()
        })
        return parsed_date
    except ValueError as e:
        logger.error(f"Failed to parse date", exc_info=True, extra={
            'date_str': date_str,
            'error': str(e)
        })
        raise


@log_operation("insert_ad")
def insert_ad(ad_data: dict, property_type: str, geo_id: int) -> int:
    """
    Inserts an ad into the database.
    """
    ad_unique_id = ad_data.get("id")

    with log_context(logger, ad_id=ad_unique_id, property_type=property_type, geo_id=geo_id):
        if not ad_unique_id:
            logger.warning("Ad missing ID, cannot insert", extra={'ad_data': ad_data})
            return None

        # Use the unified ad insertion function
        logger.info("Inserting ad into database", extra={
            'ad_id': ad_unique_id,
            'property_type': property_type,
            'geo_id': geo_id
        })

        try:
            result = process_and_insert_ad(ad_data, property_type, geo_id)

            if result:
                logger.info(f"Successfully inserted ad", extra={
                    'ad_id': ad_unique_id,
                    'db_id': result
                })
            else:
                logger.warning(f"Failed to insert ad", extra={'ad_id': ad_unique_id})

            return result

        except Exception as e:
            logger.error(f"Error inserting ad", exc_info=True, extra={
                'ad_id': ad_unique_id,
                'error_type': type(e).__name__
            })
            return None
