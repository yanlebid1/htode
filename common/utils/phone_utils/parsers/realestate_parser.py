"""
Parser for real-estate.lviv.ua listings. Fetches phone numbers via the site's AJAX API.
"""

import re
from common.utils import logger
from common.utils.logging_config import log_operation, log_context
from common.utils.phone_utils.phone_models import ExtractionResult
from common.utils.phone_utils.http_client import AsyncHTTPClient

# AJAX endpoint for retrieving phone numbers (by listing ID) on real-estate.lviv.ua
REAL_ESTATE_LVIV_API = "https://www.real-estate.lviv.ua/en/ajax_show_phone_object/{}"
# Regex to extract phone from the AJAX response (encoded tel link)
TELEPHONE_REGEX_REAL_ESTATE = re.compile(r"tel:(.*?)\\u0022")


@log_operation("parse_real_estate_lviv")
async def parse_real_estate_lviv(
    ad_link: str, client: AsyncHTTPClient
) -> ExtractionResult:
    """
    Parse a real-estate.lviv.ua advertisement page to extract the phone number via the site's AJAX phone API.
    """
    with log_context(logger, ad_link=ad_link):
        logger.info("Parsing real-estate.lviv.ua phone data")
        try:
            # The ad link contains an identifier which we can use to call the AJAX phone endpoint
            ad_id_part = ad_link.split("/")[-1].split("-")[0]
            phone_api_url = REAL_ESTATE_LVIV_API.format(ad_id_part)
            headers = {"X-Requested-With": "XMLHttpRequest", "Referer": ad_link}
            # Fetch phone data via AJAX endpoint
            content = await client.fetch(phone_api_url, headers=headers)
            logger.info(f"Fetched phone data from {phone_api_url}")
            if not content:
                return ExtractionResult([], None)
            # Extract phone number(s) from the response content
            matches = TELEPHONE_REGEX_REAL_ESTATE.findall(content)
            if matches:
                # Clean up formatting characters
                phones = [
                    m.replace("(", "").replace(")", "").replace(" ", "")
                    for m in matches
                ]
                logger.debug("Extracted phones", extra={"phone_count": len(phones)})
                return ExtractionResult(phones, None)
            # If no matches, return empty result
            return ExtractionResult([], None)
        except Exception as e:
            logger.exception(
                "Error fetching real-estate.lviv.ua phone link",
                extra={"error_type": type(e).__name__, "ad_link": ad_link},
            )
            return ExtractionResult([], None)
