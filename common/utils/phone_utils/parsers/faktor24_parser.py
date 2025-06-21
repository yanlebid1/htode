"""
Parser for faktor24.com pages. Extracts phone number from the HTML content.
"""

import re
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult

# Regex pattern to find the phone number in faktor24.com HTML
FAKTOR24_PHONE_REGEX = re.compile(r'"tel:(.*?)" id="phoneDisplay"')


def parse_faktor24_page(html: str) -> ExtractionResult:
    """
    Extract phone number from a faktor24.com advertisement page HTML.
    """
    logger.info("Parsing faktor24.com content")
    telephones = FAKTOR24_PHONE_REGEX.findall(html)
    if telephones:
        # Return the first phone number found
        return ExtractionResult([telephones[0]], None)
    return ExtractionResult([], None)
