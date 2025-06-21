"""
Parser for OLX.ua advertisements. Handles phone number extraction via API or Camoufox browser automation.
"""

import re
import json
from bs4 import BeautifulSoup
from typing import Optional
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult
from ..http_client import AsyncHTTPClient, REQUEST_TIMEOUT
from common.utils.extraction_client import extraction_client

# API endpoint template for fetching phone numbers given an OLX offer ID
OLX_PHONE_API_URL = "https://www.olx.ua/api/v1/offers/{}/limited-phones/"


async def parse_olx_content(
    html: str, url: str, client: AsyncHTTPClient
) -> ExtractionResult:
    """
    Parse an OLX advertisement page's HTML content to extract phone number(s).
    Attempts to find the advertisement ID and use OLX's API to get phone numbers.
    Fallbacks to searching the HTML content (or using Camoufox via client) if needed.
    """
    logger.info("Parsing OLX page content via HTML and API approach")
    # Try to find advertisement ID in the HTML or URL
    ad_id_match = re.search(r'"sku":"(.*?)"', html)
    if not ad_id_match:
        soup = BeautifulSoup(html, "lxml")
        ad_id_elem = soup.find(attrs={"data-ad-id": True})
        if ad_id_elem:
            ad_id = ad_id_elem.get("data-ad-id")
        else:
            id_match = re.search(r'"id":\s*"?(\d+)"?', html)
            if id_match:
                ad_id = id_match.group(1)
            else:
                logger.warning(
                    "Could not extract OLX ad ID from HTML; attempting browser extraction as last resort"
                )
                try:
                    result = await extraction_client.extract_content_async(
                        url=url,
                        proxy=client.proxy,
                        timeout=REQUEST_TIMEOUT,
                        wait_after_load=3000,
                        execute_script="document.querySelector('.phone-button')?.click();",
                        wait_for_selector=".phone-number",
                    )

                    if result["status"] == "success" and result.get("content"):
                        # Extract phones from the content after button click
                        phone_pattern = re.compile(
                            r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                        )
                        matches = phone_pattern.findall(result["content"])
                        if matches:
                            phones = [re.sub(r"[^\d+]", "", phone) for phone in matches]
                            return ExtractionResult(phones, None)
                except Exception as e:
                    logger.warning(f"Browser extraction failed: {e}")
                # If Camoufox approach didn't yield results
                return ExtractionResult([], None)
    else:
        ad_id = ad_id_match.group(1)
    # If we have an ad ID, attempt to fetch phone via OLX API
    try:
        phone_api_url = OLX_PHONE_API_URL.format(ad_id)
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url,
            "Accept": "application/json, text/plain, */*",
        }
        phone_data = await client.fetch(phone_api_url, headers=headers)
        if phone_data:
            data = json.loads(phone_data)
            phones: list = []
            if "data" in data and "phones" in data["data"]:
                for phone_obj in data["data"]["phones"]:
                    if isinstance(phone_obj, dict) and "uri" in phone_obj:
                        phones.append(phone_obj["uri"].replace("tel:", ""))
                    elif isinstance(phone_obj, str):
                        phones.append(phone_obj.replace(" ", ""))
            return ExtractionResult(phones, None)
    except Exception as e:
        logger.warning(f"Failed to fetch OLX phone via API: {e}")
    # Fallback: search for phone patterns in the HTML content
    phone_pattern = re.compile(r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}")
    matches = phone_pattern.findall(html)
    if matches:
        phones = [re.sub(r"[^\d+]", "", phone) for phone in matches]
        return ExtractionResult(phones, None)
    # If nothing found
    return ExtractionResult([], None)


async def parse_olx_camoufox(
    ad_url: str, proxy: Optional[str] = None
) -> ExtractionResult:
    """
    Use browser automation to extract the phone number from an OLX advertisement page.
    This simulates a real user: loads the ad, clicks the phone reveal button, and captures the number.
    """
    logger.info("Starting browser automation for OLX phone extraction")

    try:
        # Use extraction client to click phone button and get content
        result = await extraction_client.extract_content_async(
            url=ad_url,
            proxy=proxy,
            timeout=REQUEST_TIMEOUT,
            wait_after_load=3000,
            execute_script="""
                // Try to find and click the phone reveal button
                const phoneButton = document.querySelector('[data-testid="call-button"], .phone-button, button[aria-label*="phone"], button[aria-label*="телефон"]');
                if (phoneButton) phoneButton.click();
                
                // Return true if button was found
                return !!phoneButton;
            """,
            wait_for_selector="[href^='tel:'], .phone-number, span[class*='phone']",
        )

        if result["status"] == "success" and result.get("content"):
            soup = BeautifulSoup(result["content"], "lxml")

            # Extract phone numbers from tel: links
            phones = []
            tel_links = soup.find_all(href=re.compile(r"^tel:"))
            for link in tel_links:
                phone = link.get("href", "").replace("tel:", "").strip()
                if phone and re.match(r"\+?[\d\s\-\(\)]+", phone):
                    cleaned_phone = re.sub(r"[^\d+]", "", phone)
                    if cleaned_phone and cleaned_phone not in phones:
                        phones.append(cleaned_phone)

            # Also search for phone patterns in visible text
            if not phones:
                phone_pattern = re.compile(
                    r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                )
                matches = phone_pattern.findall(result["content"])
                phones = list(set([re.sub(r"[^\d+]", "", phone) for phone in matches]))

            # Check for Viber links
            viber_link = None
            viber_links = soup.find_all(href=re.compile(r"viber://"))
            if viber_links:
                viber_link = viber_links[0].get("href")

            if phones:
                logger.info(f"Successfully extracted phones from OLX: {phones}")
                return ExtractionResult(phones, viber_link)
            else:
                logger.warning("No phones found in OLX page after button click")
                return ExtractionResult([], None)
        else:
            logger.error(f"Browser extraction failed for OLX: {result.get('error')}")
            return ExtractionResult([], None)

    except Exception as e:
        logger.error(f"Error during browser extraction for OLX: {e}")
        return ExtractionResult([], None)
