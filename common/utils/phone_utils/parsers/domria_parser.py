"""
Parser for DOM.RIA real estate listings. Extracts phone numbers by simulating user interaction if needed.
"""

import re
from bs4 import BeautifulSoup
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult
from common.utils.phone_utils.http_client import AsyncHTTPClient, REQUEST_TIMEOUT
from common.utils.extraction_client import extraction_client


async def parse_domria_page(url: str, client: AsyncHTTPClient) -> ExtractionResult:
    """
    Extract phone number(s) from a DOM.RIA listing page.
    First tries to fetch the page content directly for phone numbers.
    If none found (likely hidden behind a "Show phone" button), uses Camoufox to simulate a user clicking the button.
    """
    logger.info(f"Attempting direct fetch for DOM.RIA page: {url}")
    try:
        html = await client.fetch(url)
    except Exception as e:
        logger.warning(f"Direct fetch failed for DOM.RIA: {e}")
        html = None
    phones: list = []
    if html:
        # Try to parse out any phone number from the static HTML
        soup = BeautifulSoup(html, "lxml")
        # Check for any tel: links first
        tel_links = soup.find_all("a", href=re.compile(r"^tel:"))
        for link in tel_links:
            phone = link.get("href").replace("tel:", "").strip()
            if phone:
                phones.append(phone)
        # If not found via tel: link, search the text for patterns
        if not phones:
            text_content = soup.get_text()
            # Patterns for Ukrainian phone numbers (with or without country code)
            pattern_intl = re.compile(
                r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
            )
            pattern_local = re.compile(r"\(?0\d{2}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}")
            matches = pattern_intl.findall(text_content) + pattern_local.findall(
                text_content
            )
            if matches:
                # Clean and normalize any found numbers
                for m in matches:
                    num = re.sub(r"[^\d+]", "", m)
                    if num:
                        phones.append(num)
        if phones:
            logger.info(f"Found phone(s) in DOM.RIA page without interaction: {phones}")
            return ExtractionResult(phones, None)
    # If no phone found in static content, use browser to click "Show phone" button
    logger.info(
        "Using browser automation to retrieve DOM.RIA phone number (simulating user interaction)"
    )

    try:
        # Use extraction client to click phone button and get content
        result = await extraction_client.extract_content_async(
            url=url,
            proxy=client.proxy,
            timeout=REQUEST_TIMEOUT,
            wait_after_load=3000,
            execute_script="""
                // Try to find and click the phone reveal button
                const phoneButtons = document.querySelectorAll('button, a, div, span');
                let clicked = false;
                
                for (const btn of phoneButtons) {
                    const text = btn.textContent?.toLowerCase() || '';
                    const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
                    
                    if (text.includes('показати телефон') || text.includes('показать телефон') ||
                        text.includes('phone') || text.includes('телефон') ||
                        ariaLabel.includes('phone') || ariaLabel.includes('телефон')) {
                        btn.click();
                        clicked = true;
                        break;
                    }
                }
                
                return clicked;
            """,
            wait_for_selector="[href^='tel:'], .phone-number, span[class*='phone']",
        )

        if result["status"] == "success" and result.get("content"):
            soup = BeautifulSoup(result["content"], "lxml")

            # Extract phone numbers from tel: links
            phones = []
            tel_links = soup.find_all("a", href=re.compile(r"^tel:"))
            for link in tel_links:
                phone = link.get("href").replace("tel:", "").strip()
                cleaned_phone = re.sub(r"[^\d+]", "", phone)
                if cleaned_phone and cleaned_phone not in phones:
                    phones.append(cleaned_phone)

            # Also search for phone patterns in the content
            if not phones:
                pattern_intl = re.compile(
                    r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                )
                pattern_local = re.compile(
                    r"\(?0\d{2}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                )
                matches = pattern_intl.findall(
                    result["content"]
                ) + pattern_local.findall(result["content"])
                phones = list(set([re.sub(r"[^\d+]", "", m) for m in matches if m]))

            # Check for Viber links
            viber_link = None
            viber_links = soup.find_all(href=re.compile(r"viber://"))
            if viber_links:
                viber_link = viber_links[0].get("href")

            if phones:
                logger.info(f"Successfully extracted phones from DOM.RIA: {phones}")
                return ExtractionResult(phones, viber_link)
            else:
                logger.warning("No phones found in DOM.RIA page even after interaction")
                return ExtractionResult([], None)
        else:
            logger.error(
                f"Browser extraction failed for DOM.RIA: {result.get('error')}"
            )
            return ExtractionResult([], None)

    except Exception as e:
        logger.error(f"Error during browser extraction for DOM.RIA: {e}")
        return ExtractionResult([], None)
