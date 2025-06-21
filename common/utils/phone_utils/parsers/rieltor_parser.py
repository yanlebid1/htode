"""
Parser for rieltor.ua pages. Extracts phone number and Viber link if present from the HTML content.
"""

import re
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult

# Regex patterns for phone number and Viber link in rieltor.ua HTML
RIELTOR_PHONE_REGEX = re.compile(r'"tel:(.*?)"')
RIELTOR_VIBER_REGEX = re.compile(r'href="(viber:.*)" class')


def parse_rieltor_page(html: str) -> ExtractionResult:
    """
    Extract phone number and Viber link from a rieltor.ua advertisement page HTML.
    """
    logger.info("Parsing rieltor.ua content")
    result = ExtractionResult([], None)
    telephones = RIELTOR_PHONE_REGEX.findall(html)
    viber_links = RIELTOR_VIBER_REGEX.findall(html)
    if telephones:
        # Take the first phone number found (if multiple, typically only one is needed)
        result.phone_numbers = [telephones[0]]
    if viber_links:
        # Take the first Viber link if present
        result.viber_link = viber_links[0]
    return result
