"""
Parser for lun.ua pages. Extracts phone numbers from embedded JSON in page HTML.
"""

import re
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult

# Regex to find phone number in lun.ua HTML (looking for JSON field "phones")
LUN_PHONE_REGEX = re.compile(r'"phones\\":\\[\\"8(.*)\\"],\\\"geoEntities')


def parse_lun_page(html: str) -> ExtractionResult:
    """
    Extract phone number from a lun.ua advertisement page HTML.
    """
    logger.info("Parsing lun.ua content")
    matches = LUN_PHONE_REGEX.findall(html)
    if matches:
        # The regex captures the phone number after the leading "8"
        return ExtractionResult(["8" + matches[0]], None)
    return ExtractionResult([], None)
