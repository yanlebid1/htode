# common/utils/phone_parser.py

import re
import urllib.parse
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict
import json
import random
from contextlib import asynccontextmanager

from bs4 import BeautifulSoup
import aiohttp
from curl_cffi.requests import AsyncSession
import httpx
from camoufox.async_api import AsyncCamoufox

# Handle imports for both package and direct execution
from common.utils.logging_config import log_operation, log_context, LogAggregator
from common.utils import logger

# User-Agent generator
try:
    from fake_useragent import UserAgent  # type: ignore

    _UA_GEN = UserAgent()
except Exception:  # pragma: no cover – fallback if fake_useragent data unavailable
    _UA_GEN = None


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

# Browser impersonation options for curl_cffi
IMPERSONATE_OPTIONS = [
    "chrome110",
    "chrome107",
    "chrome104",
    "chrome99",
    "firefox109",
    "firefox102",
    "safari15_5",
    "safari15_3",
    "edge99",
]

# User agents pool for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


# ===========================
# HTTP Client Manager
# ===========================
class AsyncHTTPClient:
    """Manages async HTTP requests with fallback mechanisms.

    Order of fallback methods:
    1. aiohttp (primary) - Fast and lightweight
    2. curl_cffi - Browser impersonation for anti-bot protection
    3. httpx - HTTP/2 support and advanced features
    4. camoufox - Full browser automation as last resort
    """

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self.proxy_dict = self._parse_proxy(proxy) if proxy else None

    def _parse_proxy(self, proxy_url: str) -> Dict[str, str]:
        """Parse proxy URL into dict format."""
        parsed = urllib.parse.urlparse(proxy_url)
        proxy_dict = {
            "http": proxy_url,
            "https": proxy_url
        }
        return proxy_dict

    def _get_random_headers(self) -> Dict[str, str]:
        """Get randomized headers to avoid detection."""
        user_agent = _random_ua()

        return {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,uk;q=0.8,ru;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    @asynccontextmanager
    async def _get_aiohttp_session(self):
        """Create aiohttp session - PRIMARY METHOD."""
        connector = None
        if self.proxy:
            try:
                from aiohttp_proxy import ProxyConnector
                connector = ProxyConnector.from_url(self.proxy)
            except ImportError:
                # Fallback to regular proxy
                pass

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self._get_random_headers()
        ) as session:
            yield session

    @asynccontextmanager
    async def _get_curl_cffi_session(self, impersonate: str):
        """Create curl_cffi async session with impersonation."""
        session = AsyncSession(
            impersonate=impersonate,
            timeout=REQUEST_TIMEOUT,
            proxies=self.proxy_dict if self.proxy else None
        )
        try:
            yield session
        finally:
            await session.close()

    async def _fetch_with_camoufox(self, url: str) -> Optional[str]:
        """Use Camoufox headless browser as a last resort for JavaScript-heavy sites."""
        browser = None
        try:
            # Parse proxy if available
            proxy_config = None
            if self.proxy:
                parsed_proxy = urllib.parse.urlparse(self.proxy)
                proxy_config = {
                    'server': f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
                }
                if parsed_proxy.username and parsed_proxy.password:
                    proxy_config['username'] = parsed_proxy.username
                    proxy_config['password'] = parsed_proxy.password

            # Initialize Camoufox with proper configuration
            camoufox_args = {
                'headless': True,
                'proxy': proxy_config,
                # Add viewport to appear more like a real browser
                'viewport': {'width': 1920, 'height': 1080},
                # Add locale
                'locale': 'en-US',
                # Add timezone
                'timezone_id': 'America/New_York',
            }

            # Remove None values
            camoufox_args = {k: v for k, v in camoufox_args.items() if v is not None}

            async with AsyncCamoufox(**camoufox_args) as browser:
                page = await browser.new_page()

                # Set extra headers to avoid detection
                await page.set_extra_http_headers(self._get_random_headers())

                # Navigate to the page
                await page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)

                # Wait a bit for dynamic content
                await page.wait_for_timeout(2000)

                # Get the content
                content = await page.content()

                logger.info("Successfully fetched with Camoufox")
                return content

        except Exception as e:
            logger.warning(f"Camoufox failed: {e}")
            return None

    async def fetch_with_aiohttp(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        """Fetch URL using aiohttp - PRIMARY METHOD."""
        try:
            async with self._get_aiohttp_session() as session:
                combined_headers = {**self._get_random_headers(), **(headers or {})}

                # Add anti-bot headers - filter out None values
                if "api" in url:
                    combined_headers["X-Requested-With"] = "XMLHttpRequest"
                combined_headers["Referer"] = "https://www.google.com/"

                # Remove any None values from headers
                combined_headers = {k: v for k, v in combined_headers.items() if v is not None}

                async with session.get(url, headers=combined_headers, ssl=False) as response:
                    response.raise_for_status()
                    logger.info("Successfully fetched with aiohttp")
                    return await response.text()
        except Exception as e:
            logger.warning(f"aiohttp failed: {e}")
            return None

    async def fetch_with_curl_cffi(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        """Fetch URL using curl_cffi with different impersonations."""
        combined_headers = {**self._get_random_headers(), **(headers or {})}
        # Remove None values
        combined_headers = {k: v for k, v in combined_headers.items() if v is not None}

        # Try different impersonations
        for impersonate in IMPERSONATE_OPTIONS:
            try:
                logger.debug(f"Trying curl_cffi with impersonate={impersonate}")
                async with self._get_curl_cffi_session(impersonate) as session:
                    response = await session.get(url, headers=combined_headers)
                    if response.status_code == 200:
                        logger.info(f"Successfully fetched with curl_cffi ({impersonate})")
                        return response.text
                    else:
                        logger.warning(f"curl_cffi returned status {response.status_code} with {impersonate}")
            except Exception as e:
                logger.debug(f"curl_cffi failed with {impersonate}: {e}")
                continue

        return None

    async def fetch_with_httpx(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        """Fetch URL using httpx with http2 support."""
        try:
            combined_headers = {**self._get_random_headers(), **(headers or {})}
            # Remove None values
            combined_headers = {k: v for k, v in combined_headers.items() if v is not None}

            async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    proxy=self.proxy,
                    headers=combined_headers,
                    follow_redirects=True,
                    http2=True,  # Enable HTTP/2
                    verify=False  # Disable SSL verification for problematic sites
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                logger.info("Successfully fetched with httpx")
                return response.text
        except Exception as e:
            logger.warning(f"httpx failed: {e}")
            return None

    async def fetch(self, url: str, headers: Optional[Dict] = None) -> str:
        """Fetch URL with fallback mechanism in order of preference."""
        methods = [
            ("aiohttp", self.fetch_with_aiohttp),
            ("curl_cffi", self.fetch_with_curl_cffi),
            ("httpx", self.fetch_with_httpx),
            ("camoufox", lambda u, h: self._fetch_with_camoufox(u)),
        ]

        for method_name, method_func in methods:
            logger.info(f"Trying {method_name} for {url}")
            try:
                content = await method_func(url, headers)
                if content:
                    return content
            except Exception as e:
                logger.warning(f"{method_name} failed with exception: {e}")
                continue

        raise Exception(f"Failed to fetch {url} with all available methods")


# ===========================
# Domain-specific parsing functions
# ===========================
@log_operation("parse_real_estate_lviv")
async def _parse_real_estate_lviv(ad_link: str, client: AsyncHTTPClient) -> ExtractionResult:
    with log_context(logger, ad_link=ad_link):
        logger.info("Parsing real-estate.lviv.ua data.")
        try:
            # Extract the ID part from the URL
            ad_id_part = ad_link.split("/")[-1].split("-")[0]
            link_ = REAL_ESTATE_LVIV_UA_LINK.format(ad_id_part)

            # Special headers for AJAX request
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": ad_link
            }

            # Fetch the phone via AJAX endpoint
            content = await client.fetch(link_, headers=headers)
            logger.info(f"Fetched content from {link_}")
            logger.info(f"Content {content}")
            if not content:
                return ExtractionResult([], None)

            matches = TELEPHONE_REGEX_REAL_ESTATE.findall(content)
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
        result.phone_numbers = [telephones[0]]
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

    # Look for tel: links
    tel_links = soup.find_all("a", href=re.compile(r"^tel:"))
    for link in tel_links:
        phone = link.get("href").replace("tel:", "").strip()
        if phone:
            phone_nums.append(phone)

    # Look for Viber links
    viber_links = soup.find_all("a", href=re.compile(r"^viber:"))
    if viber_links:
        viber_link = viber_links[0].get("href")

    # Also try to find phone numbers in text
    if not phone_nums:
        phone_pattern = re.compile(r'\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}')
        text_content = soup.get_text()
        matches = phone_pattern.findall(text_content)
        if matches:
            phone_nums = [re.sub(r'[^\d+]', '', phone) for phone in matches]

    return ExtractionResult(phone_nums, viber_link)


# ===========================
# OLX phone fetch
# ===========================
async def parse_olx_content(html: str, url: str, client: AsyncHTTPClient) -> ExtractionResult:
    """
    Parse OLX ad page content to extract the phone number.
    Since we can't execute JavaScript easily, we'll try to find the ad ID and call the API directly.
    """
    logger.info("Parsing OLX content")

    # Try to extract ad ID from URL or page content
    ad_id_match = re.search(r'"sku":"(.*?)"', html)
    if not ad_id_match:
        # Try to find it in the page content
        soup = BeautifulSoup(html, "lxml")
        # Look for data attributes that might contain the ad ID
        ad_id_elem = soup.find(attrs={"data-ad-id": True})
        if ad_id_elem:
            ad_id = ad_id_elem.get("data-ad-id")
        else:
            # Try another approach - look in JavaScript
            id_match = re.search(r'"id":\s*"?(\d+)"?', html)
            if id_match:
                ad_id = id_match.group(1)
            else:
                logger.warning(f"SKU IS IN THE HTML: {'sku' in html}")
                logger.warning("Could not extract OLX ad ID")
                logger.warning(f"HTML content: {html[:500]}...")

                # Last resort - use Camoufox if available
                logger.info("Attempting to fetch OLX phone with Camoufox")
                try:
                    full_content = await client._fetch_with_camoufox(url)
                    if full_content:
                        # Look for phone after JavaScript execution
                        phone_soup = BeautifulSoup(full_content, "lxml")
                        tel_links = phone_soup.find_all("a", href=re.compile(r"^tel:"))
                        if tel_links:
                            phones = [link.get("href").replace("tel:", "") for link in tel_links]
                            return ExtractionResult(phones, None)
                except Exception as e:
                    logger.warning(f"Camoufox OLX fetch failed: {e}")

                return ExtractionResult([], None)
    else:
        ad_id = ad_id_match.group(1)

    # Try to fetch phone from API
    try:
        phone_api_url = OLX_PHONE_LINK.format(ad_id)

        # OLX API requires specific headers
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url,
            "Accept": "application/json, text/plain, */*",
        }

        phone_data = await client.fetch(phone_api_url, headers=headers)
        if phone_data:
            data = json.loads(phone_data)
            phones = []
            if "data" in data and "phones" in data["data"]:
                for phone_obj in data["data"]["phones"]:
                    if isinstance(phone_obj, dict) and "uri" in phone_obj:
                        phones.append(phone_obj["uri"].replace("tel:", ""))
                    elif isinstance(phone_obj, str):
                        phones.append(phone_obj.replace(' ', ''))
            return ExtractionResult(phones, None)
    except Exception as e:
        logger.warning(f"Failed to fetch OLX phone via API: {e}")

    # Fallback: try to find phone numbers in the HTML
    phone_pattern = re.compile(r'\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}')
    matches = phone_pattern.findall(html)
    if matches:
        phones = [re.sub(r'[^\d+]', '', phone) for phone in matches]
        return ExtractionResult(phones, None)

    return ExtractionResult([], None)


# ===========================
# Camoufox-based OLX parsing
# ===========================
async def _parse_olx_camoufox(ad_url: str, proxy: Optional[str] = None) -> ExtractionResult:
    """Use Camoufox to extract phone number from an OLX advertisement page.

    Flow:
      1. Navigate to the ad page.
      2. Wait for the contact phone button (button[data-cy="ad-contact-phone"]).
      3. Click the button to reveal the phone link.
      4. Wait for the link (button[data-cy="ad-contact-phone"] a[data-testid="contact-phone"]).
      5. Extract the `href` attribute which contains the telephone number in the format
         ``tel:(068)6771621``.
      6. Normalise and return the number.
    """
    logger.info("Parsing OLX content via Camoufox")

    browser = None
    try:
        # Parse proxy if available
        proxy_config = None
        if proxy:
            parsed_proxy = urllib.parse.urlparse(proxy)
            proxy_config = {
                'server': f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
            }
            if parsed_proxy.username and parsed_proxy.password:
                proxy_config['username'] = parsed_proxy.username
                proxy_config['password'] = parsed_proxy.password

        # Initialize Camoufox with proper configuration
        camoufox_args = {
            'headless': True,
            'proxy': proxy_config,
            'viewport': {'width': 1920, 'height': 1080},
            'locale': 'uk-UA',  # Ukrainian locale for OLX
            'timezone_id': 'Europe/Kiev',
        }

        # Remove None values
        camoufox_args = {k: v for k, v in camoufox_args.items() if v is not None}

        async with AsyncCamoufox(**camoufox_args) as browser:
            page = await browser.new_page()

            # Set Ukrainian headers for OLX
            headers = {
                "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
                "User-Agent": _random_ua(),
            }
            await page.set_extra_http_headers(headers)

            logger.info(f"Navigating to OLX ad URL via Camoufox: {ad_url}")
            await page.goto(ad_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)

            # Wait for the ad action buttons container
            ad_action_selector = 'div[data-testid="ad-action-buttons"]'
            btn_selector = 'button[data-cy="ad-contact-phone"]'

            try:
                await page.wait_for_selector(ad_action_selector, timeout=8000)
                logger.info("Found ad action buttons container")
            except Exception:
                # Capture screenshot for debugging
                try:
                    from pathlib import Path
                    from datetime import datetime

                    ss_dir = Path.cwd() / "debug_screenshots"
                    ss_dir.mkdir(parents=True, exist_ok=True)
                    ss_path = ss_dir / f"olx_no_button_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
                    await page.screenshot(path=str(ss_path), full_page=True)
                    logger.warning(f"Saved troubleshooting screenshot to {ss_path}")
                except Exception as ss_err:
                    logger.warning(f"Failed to capture screenshot: {ss_err}")

                logger.warning("Phone button did not appear on OLX page")
                return ExtractionResult([], None)

            # Click the phone button
            await page.click(btn_selector, force=True)
            logger.info("Clicked phone reveal button")

            # Wait for the link that contains the phone number
            link_selector = 'button[data-cy="ad-contact-phone"] a[data-testid="contact-phone"]'
            try:
                await page.wait_for_selector(link_selector, timeout=8000)
                logger.info("Phone link appeared")
            except Exception:
                # Capture screenshot for debugging
                try:
                    from pathlib import Path
                    from datetime import datetime

                    ss_dir = Path.cwd() / "debug_screenshots"
                    ss_dir.mkdir(parents=True, exist_ok=True)
                    ss_path = ss_dir / f"olx_no_link_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
                    await page.screenshot(path=str(ss_path), full_page=True)
                    logger.warning(f"Saved troubleshooting screenshot to {ss_path}")
                except Exception as ss_err:
                    logger.warning(f"Failed to capture screenshot: {ss_err}")

                logger.warning("Phone link did not appear after clicking button on OLX page")
                return ExtractionResult([], None)

            # Extract the phone number
            link_el = await page.query_selector(link_selector)
            href_val = await link_el.get_attribute("href") if link_el else None

            if not href_val:
                logger.warning("Failed to extract href with phone from OLX page")
                return ExtractionResult([], None)

            # href format example: tel:(068)6771621
            phone_raw = href_val.replace('tel:', '').strip()
            # Remove parentheses, spaces, dashes
            phone_clean = re.sub(r'[\s\-()]+', '', phone_raw)

            logger.info(f"Successfully extracted phone: {phone_clean}")
            return ExtractionResult([phone_clean], None)

    except Exception as e:
        logger.warning(f"Camoufox extraction for OLX failed: {e}")
        return ExtractionResult([], None)


# ===========================
# Domain routing parse
# ===========================
async def _domain_parse_final(html: str, original_url: str, client: AsyncHTTPClient) -> ExtractionResult:
    """
    Determine the domain of the content and apply the appropriate parsing function.
    """
    soup = BeautifulSoup(html, "html.parser")
    canonical_tag = soup.find("link", rel="canonical") or soup.find("a", class_="redirect-link")
    canonical_url = canonical_tag.get("href") if canonical_tag else original_url
    if canonical_url != original_url:
        logger.info(f"Canonical URL for {original_url} is {canonical_url}")
    else:
        logger.info("No canonical redirect; using original URL for domain detection.")

    # Route to domain-specific parse functions
    if "olx.ua" in canonical_url:
        # For OLX we rely solely on Camoufox interaction
        return await _parse_olx_camoufox(canonical_url, proxy=client.proxy)
    elif "real-estate.lviv.ua" in canonical_url:
        return await _parse_real_estate_lviv(canonical_url, client)
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
# Main asynchronous extraction logic
# ===========================
@log_operation("extract_phone_numbers_async")
async def _extract_phone_numbers_async(resource_url: str, proxy: Optional[str] = None) -> ExtractionResult:
    """
    Asynchronously extract phone numbers (and Viber link if present) from the given resource URL.
    Optionally uses a proxy for network requests if provided.
    """
    aggregator = LogAggregator(logger, f"extract_phone_numbers_async_{resource_url}")

    try:
        with log_context(logger, resource_url=resource_url):
            client = AsyncHTTPClient(proxy=proxy)

            # Fetch the page content
            try:
                html_content = await client.fetch(resource_url)
            except Exception as e:
                logger.error(f"Failed to fetch {resource_url}: {e}")
                aggregator.add_error("fetch_failed", {'error': str(e)})

                # If the target is an OLX advertisement, attempt Camoufox extraction
                if "olx.ua" in resource_url:
                    logger.info("Attempting Camoufox extraction for OLX after fetch failure")
                    return await _parse_olx_camoufox(resource_url, proxy=proxy)

                return ExtractionResult([], None)

            # --- 2. Handle Flatfy (or similar) redirection pages -----------------
            # Some services (e.g., flatfy.ua) serve intermediary pages that display
            # a simple "Перенаправлення" ("Redirection") message and contain a link
            # with class "redirect-link" which leads to the real advertisement.
            # Those pages do not contain phone numbers or ad markup. We therefore
            # detect such pages and transparently follow the redirect once before
            # proceeding with the usual domain-specific parsing.

            try:
                if "Перенаправлення" in html_content:
                    soup_tmp = BeautifulSoup(html_content, "html.parser")
                    redirect_tag = soup_tmp.select_one("a.redirect-link[href]")
                    if redirect_tag and redirect_tag.get("href"):
                        redirect_href = redirect_tag.get("href")

                        # Normalise the URL (may be relative)
                        redirect_url = urllib.parse.urljoin(resource_url, redirect_href)

                        logger.info(
                            f"Detected redirect page. Following redirect to {redirect_url}")

                        # Attempt to fetch the real advert page
                        redirected_html = await client.fetch(redirect_url)
                        if redirected_html:
                            html_content = redirected_html
                            resource_url = redirect_url  # Update for downstream logic
            except Exception as e:
                # We swallow errors here because failure to follow redirect should not
                # abort the entire extraction; downstream fallback parsers may still
                # succeed.
                logger.warning(f"Redirect handling failed: {e}")

            # Parse the content based on domain
            result = await _domain_parse_final(html_content, resource_url, client)

            method_label = "proxy" if proxy else "no-proxy"
            aggregator.add_item({'method': method_label}, success=True)
            return result

    except Exception as e:
        logger.warning("Extraction failed", extra={
            'resource_url': resource_url,
            'error_type': type(e).__name__
        })
        aggregator.add_error("extraction_failed", {'error': str(e)})
        return ExtractionResult([], None)
    finally:
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
            # Create new event loop if none exists
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — run in executor to avoid blocking
                fut = asyncio.run_coroutine_threadsafe(
                    _extract_phone_numbers_async(resource_url, proxy=proxy), loop
                )
                result = fut.result()
            except RuntimeError:
                # No running loop, create one
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


def _random_ua() -> str:
    """Return a (cached) random User-Agent string quickly."""
    if _UA_GEN is not None:
        try:
            return _UA_GEN.random  # type: ignore[attr-defined]
        except Exception:
            pass  # network failure → fallback below
    return random.choice(USER_AGENTS)