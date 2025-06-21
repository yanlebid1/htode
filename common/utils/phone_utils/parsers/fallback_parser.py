"""
Fallback parser for unknown or unsupported domains. Attempts to find phone numbers and Viber links in the HTML content.
"""

import re
from bs4 import BeautifulSoup
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult


def fallback_parse(html: str) -> ExtractionResult:
    """
    Fallback parsing for an advertisement page when domain-specific logic is not available.
    Scans the HTML for any phone numbers or Viber links.
    """
    logger.info("Performing fallback parse for content")
    soup = BeautifulSoup(html, "lxml")
    phone_nums = []
    viber_link = None
    # Find any telephone links
    tel_links = soup.find_all("a", href=re.compile(r"^tel:"))
    for link in tel_links:
        phone = link.get("href").replace("tel:", "").strip()
        if phone:
            phone_nums.append(phone)
    # Find any Viber contact links
    viber_links = soup.find_all("a", href=re.compile(r"^viber:"))
    if viber_links:
        viber_link = viber_links[0].get("href")
    # If no phones found via links, search the text for phone number patterns
    if not phone_nums:
        phone_pattern = re.compile(r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}")
        text_content = soup.get_text()
        matches = phone_pattern.findall(text_content)
        if matches:
            phone_nums = [re.sub(r"[^\d+]", "", m) for m in matches]
    return ExtractionResult(phone_nums, viber_link)
