"""
Currency rate management module for caching and retrieving currency exchange rates.
"""
from decimal import Decimal
import aiohttp
import logging
import asyncio

from typing import Final
from common.utils.cache_managers import BaseCacheManager
from common.utils.cache import CacheTTL
from common.utils.logging_config import log_operation, log_context

# Set up logger
logger = logging.getLogger(__name__)

# Cache key for currency rates
CURRENCY_RATE_CACHE_KEY = "currency:usd_uah_rate"
PRIVAT_URL: Final = (
    "https://api.privatbank.ua/p24api/pubinfo?exchange&json&coursid=11"
)  # :contentReference[oaicite:0]{index=0}
MONO_URL: Final = "https://api.monobank.ua/bank/currency"  # :contentReference[oaicite:1]{index=1}
USD_NUM, UAH_NUM = 840, 980  # ISO-4217 numeric codes


class CurrencyRateManager:
    """Manager for currency rate operations"""

    @staticmethod
    @log_operation("get_usd_uah_rate_cached")
    def get_usd_uah_rate() -> Decimal:
        """
        Get the USD to UAH exchange rate from cache or fetch it if not available.
        
        Returns:
            Decimal: The current USD to UAH exchange rate
        """
        with log_context(logger, cache_key=CURRENCY_RATE_CACHE_KEY):
            # Try to get from cache first
            cached_rate = BaseCacheManager.get(CURRENCY_RATE_CACHE_KEY)

            if cached_rate:
                logger.debug("Using cached USD/UAH rate", extra={
                    'rate': cached_rate,
                    'source': 'cache'
                })
                return Decimal(str(cached_rate))

            # If not in cache, fetch it
            logger.info("Currency rate not found in cache, fetching new rate")
            return CurrencyRateManager.update_rate()

    @staticmethod
    @log_operation("update_usd_uah_rate")
    def update_rate() -> Decimal:
        """
        Fetch the current USD to UAH rate and update the cache.
        
        Returns:
            Decimal: The fetched USD to UAH exchange rate
        """
        with log_context(logger, cache_key=CURRENCY_RATE_CACHE_KEY):
            try:
                # Fetch the current rate using the currency_rate module
                rate = asyncio.run(get_usd_uah_rate())

                # Cache the rate with a long TTL (it will be refreshed by scheduled tasks)
                BaseCacheManager.set(CURRENCY_RATE_CACHE_KEY, str(rate), CacheTTL.LONG)

                logger.info("Updated USD/UAH rate in cache", extra={
                    'rate': str(rate),
                    'source': 'api'
                })

                return rate
            except Exception as e:
                logger.error("Failed to fetch currency rate", exc_info=True, extra={
                    'error_type': type(e).__name__
                })
                # Return a fallback rate in case of failure
                return Decimal('41.00')  # Fallback rate

    @staticmethod
    @log_operation("convert_usd_to_uah")
    def convert_usd_to_uah(amount: Decimal) -> Decimal:
        """
        Convert USD amount to UAH using the cached exchange rate.
        
        Args:
            amount: The amount in USD to convert
            
        Returns:
            Decimal: The equivalent amount in UAH
        """
        rate = CurrencyRateManager.get_usd_uah_rate()
        converted = amount * rate

        logger.debug("Converted USD to UAH", extra={
            'usd_amount': str(amount),
            'uah_amount': str(converted),
            'rate': str(rate)
        })

        return converted

    @staticmethod
    @log_operation("convert_to_uah")
    def convert_to_uah(amount: Decimal, currency: str) -> Decimal:
        """
        Convert the amount from specified currency to UAH.
        
        Args:
            amount: The amount to convert
            currency: The source currency code (e.g., 'USD', 'UAH')
            
        Returns:
            Decimal: The equivalent amount in UAH
        """
        if currency == "UAH":
            return amount
        elif currency == "USD":
            return CurrencyRateManager.convert_usd_to_uah(amount)
        else:
            logger.warning("Unsupported currency for conversion", extra={
                'currency': currency
            })
            return amount  # Return original amount if currency not supported


async def get_usd_uah_rate() -> Decimal:
    """Основная точка входа: вернёт Decimal('41.05') и источник ('privat'|'mono')."""
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        try:
            if currency_rate := await _rate_from_monobank(session):
                return currency_rate
            logging.warning("USD not found in Mono response, fallback → Privat.")
        except Exception as exc:
            logging.warning("Monobank API failed (%s), fallback → PrivatBank.", exc)
        return await _rate_from_privat(session)


async def _rate_from_privat(session: aiohttp.ClientSession) -> Decimal | None:
    """Курс продажи USD/UAH из ПриватБанка, либо None."""
    async with session.get(PRIVAT_URL, timeout=10) as r:
        r.raise_for_status()
        for row in await r.json():
            if row["ccy"] == "USD" and row["base_ccy"] == "UAH":
                return Decimal(row["sale"])
    return None


async def _rate_from_monobank(session: aiohttp.ClientSession) -> Decimal:
    """Фолбэк: курс продажи USD/UAH из Монобанка."""
    async with session.get(MONO_URL, timeout=10) as r:
        r.raise_for_status()
        for row in await r.json():
            if row["currencyCodeA"] == USD_NUM and row["currencyCodeB"] == UAH_NUM:
                # Ночью bank может отдать только rateCross
                return Decimal(str(row.get("rateSell") or row["rateCross"]))
    raise RuntimeError("USD rate not found in Monobank response")
