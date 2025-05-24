# common/utils/phone_parser.py

import re
import urllib.parse
import asyncio
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox  # Camoufox async browser context
from playwright.async_api import Page, Browser  # For type hints (Camoufox uses Playwright under the hood)

from common.utils.unified_request_utils import make_request
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the common utils logger
try:
    from . import logger
except ImportError:
    from common.utils import logger


# ===========================
# Data structure
# ===========================
@dataclass
class ExtractionResult:
    phone_numbers: List[str]
    viber_link: Optional[str] = None


# ===========================
# Domain-specific constants
# ===========================
OLX_PHONE_LINK = "https://www.olx.ua/api/v1/offers/{}/limited-phones/"
REAL_ESTATE_LVIV_UA_LINK = "https://www.real-estate.lviv.ua/en/ajax_show_phone_object/{}"
REQUEST_TIMEOUT = 30  # seconds

TELEPHONE_REGEX_REAL_ESTATE = re.compile(r'tel:(.*?)\\u0022')
LUN_PHONE_REGEX = re.compile(r'"phones\\":\[\\"8(.*)\\"],\\"geoEntities')
RIELTOR_PHONE_REGEX = re.compile(r'"tel:(.*?)"')
RIELTOR_VIBER_REGEX = re.compile(r'href="(viber:.*)" class')
FAKTOR24_PHONE_REGEX = re.compile(r'"tel:(.*?)" id="phoneDisplay"')


# ===========================
# Proxy parsing utility
# ===========================
@log_operation("parse_proxy")
def parse_proxy(proxy_url: str):
    """Parse a proxy URL into Playwright proxy dict format."""
    parsed = urllib.parse.urlparse(proxy_url)
    return {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "username": parsed.username,
        "password": parsed.password
    }


# ===========================
# Domain-specific parsing functions
# ===========================
@log_operation("parse_real_estate_lviv")
def _parse_real_estate_lviv(ad_link: str) -> ExtractionResult:
    with log_context(logger, ad_link=ad_link):
        logger.info("Parsing real-estate.lviv.ua data.")
        try:
            # Extract the ID part from the URL
            ad_id_part = ad_link.split("/")[-1].split("-")[0]
            link_ = REAL_ESTATE_LVIV_UA_LINK.format(ad_id_part)
            # Use centralized request utility to fetch the phone via AJAX endpoint
            response = make_request(link_, timeout=REQUEST_TIMEOUT, retries=3)
            if not response:
                return ExtractionResult([], None)
            matches = TELEPHONE_REGEX_REAL_ESTATE.findall(response.text)
            if matches:
                phones = [p.replace('(', '').replace(')', '').replace(' ', '') for p in matches]
                logger.debug("Extracted phones", extra={'phone_count': len(phones)})
                return ExtractionResult(phones, None)
            return ExtractionResult([], None)
        except Exception as e:
            logger.exception("Error fetching real-estate.lviv.ua phone link", extra={
                'error_type': type(e).__name__,
                'ad_link': ad_link
            })
            return ExtractionResult([], None)


def _parse_lun(html: str) -> ExtractionResult:
    logger.info("Parsing lun.ua content.")
    matches = LUN_PHONE_REGEX.findall(html)
    if matches:
        # The regex captures the phone number after the leading "8"
        return ExtractionResult(["8" + matches[0]], None)
    return ExtractionResult([], None)


def _parse_rieltor(html: str) -> ExtractionResult:
    logger.info("Parsing rieltor.ua content.")
    result = ExtractionResult([], None)
    telephones = RIELTOR_PHONE_REGEX.findall(html)
    viber_link = RIELTOR_VIBER_REGEX.findall(html)
    if telephones:
        result.phone_numbers = telephones[0]
    if viber_link:
        result.viber_link = viber_link[0]
    return result


def _parse_faktor24(html: str) -> ExtractionResult:
    logger.info("Parsing faktor24.com content.")
    telephones = FAKTOR24_PHONE_REGEX.findall(html)
    if telephones:
        return ExtractionResult([telephones[0]], None)
    return ExtractionResult([], None)


def _fallback_parse(html: str) -> ExtractionResult:
    logger.info("Fallback parse for unknown domain.")
    soup = BeautifulSoup(html, "lxml")
    phone_nums, viber_link = [], None
    # Look for any "tel:" links and a Viber link in common container (if present)
    container = soup.find("div", class_="offer-view-rieltor-action")
    if container:
        contacts = container.find("div", attrs={"data-jss": "ovContacts"})
        if contacts:
            for link_ in contacts.find_all("a"):
                href = link_.get("href")
                if href and href.startswith("tel:"):
                    phone_nums.append(href)
        viber_a = container.find("a", id=lambda x: x and "send-viber" in x)
        if viber_a:
            viber_link = viber_a.get("href")
    return ExtractionResult(phone_nums, viber_link)


# ===========================
# OLX phone fetch using page context
# ===========================
async def parse_olx_content(page: Page) -> ExtractionResult:
    """
    Parse OLX ad page content to extract the phone number.
    Uses the page context to perform a fetch call to OLX's phone API.
    """
    """Extract phone number from OLX ad page using Playwright ``page`` instance.

    OLX HTML/CSS changes rather often, тому тримаємо кілька запасних селекторів
    і намагаємося знайти будь-який <a href="tel:…"> елемент після кліку на
    кнопку «Показати телефон».
    """

    # 1. Спробувати натиснути кнопку «Показати телефон» (кілька можливих селекторів).
    show_phone_selectors = [
        '[data-cy="ad-contact-phone"]',                  # актуальний (2024)
        '[data-testid="show-contact"]',                  # можливий варіант
        'button:has([name="show_phone"])',               # запасний css4 селектор
    ]

    clicked = False
    for sel in show_phone_selectors:
        try:
            await page.click(sel, timeout=3000)
            clicked = True
            break
        except Exception:  # noqa: BLE001 – Playwright throws variety of errors
            continue

    if not clicked:
        logger.warning("OLX phone button not found or could not be clicked – %s", page.url)

    # 2. Дочекаймося появи будь-якого tel:-посилання на сторінці.
    try:
        await page.wait_for_selector('a[href^="tel:"]', timeout=10000)
    except Exception:
        # Не дочекався; продовжимо – можливо посилання зʼявилося вже без wait
        pass

    # 3. Збери всі tel-посилання
    phone_links = await page.query_selector_all('a[href^="tel:"]')
    phone_numbers = []
    for link in phone_links:
        href = await link.get_attribute("href")
        if href:
            phone_numbers.append(href.replace("tel:", ""))

    if phone_numbers:
        logger.info("Extracted %d phone number(s) from %s", len(phone_numbers), page.url)
        return ExtractionResult(phone_numbers, None)

    # 4. Якщо <a> немає, OLX іноді відображає номер у <span>. Шукаємо regex.
    page_content = await page.content()
    import re
    raw_numbers = re.findall(r"\+?\d[\d\s\-]{8,}\d", page_content)
    cleaned = [re.sub(r"[^\d]", "", n) for n in raw_numbers]
    cleaned = [n for n in cleaned if len(n) >= 9]

    if cleaned:
        logger.info("Extracted phone number(s) without tel: link from %s", page.url)
        return ExtractionResult(cleaned, None)

    logger.warning("OLX phone number not found on the page %s", page.url)
    return ExtractionResult([], None)


# ===========================
# Domain routing parse
# ===========================
async def _domain_parse_final(html: str, original_url: str, page: Page, browser: Browser) -> ExtractionResult:
    """
    Determine the domain of the content and apply the appropriate parsing function.
    """
    soup = BeautifulSoup(html, "lxml")
    canonical_tag = soup.find("link", rel="canonical") or soup.find("a", class_="redirect-link")
    canonical_url = canonical_tag.get("href") if canonical_tag else original_url
    if canonical_url != original_url:
        logger.info(f"Canonical URL for {original_url} is {canonical_url}")
    else:
        logger.info("No canonical redirect; using original URL for domain detection.")
    # Route to domain-specific parse functions
    if "olx.ua" in canonical_url:
        return await parse_olx_content(page)
    elif "real-estate.lviv.ua" in canonical_url:
        return _parse_real_estate_lviv(canonical_url)
    elif "rieltor.ua" in canonical_url:
        return _parse_rieltor(html)
    elif "lun.ua" in canonical_url:
        return _parse_lun(html)
    elif "faktor24.com" in canonical_url:
        return _parse_faktor24(html)
    else:
        logger.warning("Unknown domain, using fallback parser.")
        return _fallback_parse(html)


# ===========================
# Page fetch with Camoufox
# ===========================
@log_operation("fetch_page")
async def _fetch_page(url: str, browser: Browser, proxy: Optional[str], attempts: int = 3) -> str:
    """
    Load the page content using the browser (Camoufox) with optional proxy.
    Retries up to `attempts` times if loading fails.
    Returns the page HTML content on success, or raises an Exception on failure.
    """
    aggregator = LogAggregator(logger, f"fetch_page_{url}")
    proxy_config = parse_proxy(proxy) if proxy else None
    for i in range(1, attempts + 1):
        attempt_info = {'attempt': i, 'total_attempts': attempts, 'using_proxy': bool(proxy)}
        logger.info(f"[Camoufox] Attempt {i}/{attempts} to load {url}", extra=attempt_info)
        context_kwargs = {"java_script_enabled": True}
        if proxy_config:
            context_kwargs["proxy"] = proxy_config
        try:
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            # Use "domcontentloaded" to wait for initial HTML load
            await page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            content = await page.content()
            await context.close()
            aggregator.add_item({'attempt': i, 'url': url}, success=True)
            logger.debug("Page fetch successful", extra={'attempt': i})
            return content
        except Exception as e:
            logger.exception(f"Error on attempt {i} for URL: {url}", extra={
                'error_type': type(e).__name__,
                'url': url,
                'attempt': i
            })
            aggregator.add_error(str(e), {'attempt': i, 'url': url})
            try:
                await context.close()
            except Exception:
                pass
            await asyncio.sleep(1)
    aggregator.log_summary()
    raise Exception(f"Failed to load {url} after {attempts} attempts (proxy={bool(proxy)})")


# ===========================
# Main asynchronous extraction logic
# ===========================
@log_operation("extract_phone_numbers_async")
async def _extract_phone_numbers_async(resource_url: str, proxy: Optional[str] = None) -> ExtractionResult:
    """
    Asynchronously extract phone numbers (and Viber link if present) from the given resource URL.
    Optionally uses a proxy for network requests if provided.
    """
    aggregator = LogAggregator(logger, f"extract_phone_numbers_async_{resource_url}")
    camoufox_kwargs = {
        "headless": True,
    }
    if proxy:
        logger.info(f"Using proxy for extraction: {proxy}")
        camoufox_kwargs["proxy"] = parse_proxy(proxy)
    cam = AsyncCamoufox(**camoufox_kwargs)
    try:
        browser = await cam.__aenter__()  # Launch Camoufox browser
    except Exception as e:
        logger.exception(f"Failed to launch Camoufox browser: {e}")
        raise
    try:
        with log_context(logger, resource_url=resource_url):
            # html_content = await _fetch_page(resource_url, browser, proxy, attempts=5)
            parse_context_kwargs = {"java_script_enabled": True}
            if proxy:
                parse_context_kwargs["proxy"] = parse_proxy(proxy)
            page_ctx = await browser.new_context(**parse_context_kwargs)
            page = await page_ctx.new_page()
            await page.goto(resource_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            html_content = await page.content()
            result = await _domain_parse_final(html_content, resource_url, page, browser)
            await page_ctx.close()
            method_label = "proxy" if proxy else "no-proxy"
            aggregator.add_item({'method': method_label}, success=True)
            return result
    except Exception as e:
        logger.warning("Extraction via browser failed", extra={
            'resource_url': resource_url,
            'error_type': type(e).__name__
        })
        aggregator.add_error("browser_extraction_failed", {'error': str(e)})
        return ExtractionResult([], None)
    finally:
        if browser is not None:
            await cam.__aexit__(None, None, None)
        aggregator.log_summary()


@log_operation("extract_phone_numbers_from_resource")
def extract_phone_numbers_from_resource(resource_url: str, proxy: Optional[str] = None) -> ExtractionResult:
    """
    Synchronously extract phone numbers and a Viber link (if any) from the given resource URL.
    This function wraps the asynchronous extraction logic and can be used in a synchronous context.
    """
    with log_context(logger, resource_url=resource_url):
        logger.info("Starting phone number extraction", extra={'url': resource_url})
        try:
            result = asyncio.run(_extract_phone_numbers_async(resource_url, proxy=proxy))
            logger.info("Phone extraction completed successfully", extra={
                'resource_url': resource_url,
                'phone_count': len(result.phone_numbers),
                'has_viber': bool(result.viber_link)
            })
            return result
        except Exception as e:
            logger.exception("Phone extraction failed", extra={
                'resource_url': resource_url,
                'error_type': type(e).__name__
            })
            return ExtractionResult([], None)


# Example usage (for manual testing)
if __name__ == "__main__":
    # Optionally, set a proxy if needed
    proxy_url = None  # e.g. "http://username:password@proxyserver:port"
    test_urls = [
        # "https://rieltor.ua/flats-rent/view/11906106/?utm_term=3067881497&utm_medium=referral&utm_source=flatfy.ua&utm_campaign=external_rank_2000",
        "https://www.olx.ua/d/uk/obyavlenie/odnokmnatna-kvartira-v-zhk-nova-anglya-metro-vasilkvska-IDY1Q0o.html"
    ]
    for u in test_urls:
        res = extract_phone_numbers_from_resource(u, proxy=proxy_url)
        print(f"\nURL: {u}\nPhones: {res.phone_numbers}\nViber: {res.viber_link}")
