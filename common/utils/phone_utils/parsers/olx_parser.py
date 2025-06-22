"""
Parser for OLX.ua advertisements. Handles phone number extraction via API, Camoufox browser automation, or AdsPower profiles.
"""

import re
import json
from bs4 import BeautifulSoup
from typing import Optional, List, Dict
from pathlib import Path
from datetime import datetime, timedelta
from common.utils import logger
from common.utils.phone_utils.phone_models import ExtractionResult
from ..http_client import AsyncHTTPClient, REQUEST_TIMEOUT
from common.utils.extraction_client import extraction_client
from ..adspower_manager import adspower_manager

# API endpoint template for fetching phone numbers given an OLX offer ID
OLX_PHONE_API_URL = "https://www.olx.ua/api/v1/offers/{}/limited-phones/"


class OLXSessionManager:
    """Manages OLX login sessions for phone extraction."""
    
    def __init__(self):
        self.session_file = Path("olx_sessions.json")
        self._sessions = []
        self._current_session_index = 0
        self.load_sessions()
    
    def load_sessions(self):
        """Load saved sessions from file."""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    self._sessions = data.get('sessions', [])
                    logger.info(f"Loaded {len(self._sessions)} OLX sessions")
            except Exception as e:
                logger.error(f"Failed to load sessions: {e}")
                self._sessions = []
    
    def save_session(self, cookies: List[Dict], email: Optional[str] = None):
        """Save a new session."""
        session = {
            'cookies': cookies,
            'email': email or 'manual_login',
            'created_at': datetime.now().isoformat(),
            'last_used': datetime.now().isoformat(),
            'request_count': 0
        }
        self._sessions.append(session)
        self._save_to_file()
        logger.info(f"Saved new OLX session for {email or 'manual login'}")
    
    def _save_to_file(self):
        """Save sessions to file."""
        data = {'sessions': self._sessions}
        with open(self.session_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_next_session(self) -> Optional[Dict]:
        """Get next available session using round-robin."""
        if not self._sessions:
            return None
        
        # Try up to len(sessions) times to find a valid one
        for _ in range(len(self._sessions)):
            session = self._sessions[self._current_session_index]
            self._current_session_index = (self._current_session_index + 1) % len(self._sessions)
            
            # Check if session is not overused (max 100 requests per session)
            if session.get('request_count', 0) < 100:
                # Update usage
                session['last_used'] = datetime.now().isoformat()
                session['request_count'] = session.get('request_count', 0) + 1
                self._save_to_file()
                return session
        
        logger.warning("All sessions are overused, need new sessions")
        return None
    
    def has_sessions(self) -> bool:
        """Check if any sessions are available."""
        return len(self._sessions) > 0


# Global session manager instance
_session_manager = OLXSessionManager()


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
    Now with session support for logged-in extraction.
    """
    logger.info("Starting browser automation for OLX phone extraction")
    
    # Check if we have saved sessions
    if _session_manager.has_sessions():
        logger.info("Using saved OLX session for extraction")
        return await _parse_olx_with_session(ad_url, proxy)
    else:
        logger.info("No saved sessions, using standard extraction")
        return await _parse_olx_standard(ad_url, proxy)


async def check_olx_login_required(ad_url: str, proxy: Optional[str] = None) -> bool:
    """
    Check if OLX ad requires login to show phone number.
    Returns True if login button is present (login required), False otherwise.
    """
    try:
        from common.utils.extraction_client import extraction_client
        
        logger.info(f"Checking if login required for OLX ad: {ad_url}")
        
        result = await extraction_client.extract_content_async(
            url=ad_url,
            proxy=proxy,
            timeout=REQUEST_TIMEOUT,
            wait_after_load=2000,
            execute_script="""
                // Close popups first to get clean page state
                const cookieButton = document.querySelector('button[data-testid*="cookie"]');
                if (cookieButton) cookieButton.click();
                
                const surveyCloseButton = document.querySelector('div[data-testid="survey-container"] button[aria-label="Close"]');
                if (surveyCloseButton) surveyCloseButton.click();
                
                // Wait a bit for popups to close
                await new Promise(resolve => setTimeout(resolve, 500));
                
                return true;
            """,
        )
        
        if result["status"] == "success" and result.get("content"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result["content"], "lxml")
            
            # Check for login button in ad action box
            login_button = soup.select_one('div[data-testid="ad-action-box"] button[data-testid="login-button"]')
            
            if login_button:
                logger.info("Login button found - login required for phone extraction")
                return True
            else:
                logger.info("No login button found - phone should be accessible without login")
                return False
        else:
            logger.warning(f"Failed to check login requirement: {result.get('error')}")
            # If we can't determine, assume login required for safety
            return True
            
    except Exception as e:
        logger.error(f"Error checking login requirement: {e}")
        # If we can't determine, assume login required for safety
        return True


async def parse_olx_adspower(ad_url: str) -> ExtractionResult:
    """
    Extract phone number from OLX ad using AdsPower profile rotation.
    This method uses multiple AdsPower profiles that should be pre-logged into OLX.
    """
    logger.info("Starting AdsPower extraction for OLX phone extraction")
    
    try:
        phone = adspower_manager.extract_phone_with_rotation(ad_url)
        if phone:
            return ExtractionResult([phone], None)
        else:
            return ExtractionResult([], None)
    except Exception as e:
        logger.error(f"AdsPower extraction failed: {e}")
        return ExtractionResult([], None)


async def _parse_olx_with_session(
    ad_url: str, proxy: Optional[str] = None
) -> ExtractionResult:
    """Extract using saved session cookies."""
    session = _session_manager.get_next_session()
    if not session:
        logger.warning("No valid session available, falling back to standard extraction")
        return await _parse_olx_standard(ad_url, proxy)
    
    logger.info(f"Using session from {session.get('email', 'unknown')}")
    
    try:
        from camoufox.async_api import AsyncCamoufox
        import urllib.parse
        
        # Configure proxy if provided
        proxy_config = None
        if proxy:
            parsed_proxy = urllib.parse.urlparse(proxy)
            proxy_config = {
                "server": f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
            }
            if parsed_proxy.username and parsed_proxy.password:
                proxy_config["username"] = parsed_proxy.username
                proxy_config["password"] = parsed_proxy.password
        
        async with AsyncCamoufox(
            proxy=proxy_config,
            headless=True,
            os="windows",
            locale="uk-UA",
            geoip=True,
            block_webrtc=True,
            humanize=True,
        ) as browser:
            context = await browser.new_context()
            
            # Add session cookies
            cookies = session.get('cookies', [])
            if cookies:
                await context.add_cookies(cookies)
                logger.info(f"Added {len(cookies)} session cookies")
            
            page = await context.new_page()
            
            # Navigate to ad
            await page.goto(ad_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT)
            
            # Close any popups
            await _close_olx_popups(page)
            
            # Check if we're still logged in
            if 'login' in page.url:
                logger.warning("Session expired, need to re-login")
                # Mark session as invalid by maxing out request count
                session['request_count'] = 100
                _session_manager._save_to_file()
                return await _parse_olx_standard(ad_url, proxy)
            
            # Try to click phone button
            try:
                await page.wait_for_selector('button[data-testid="show-phone"]', timeout=5000)
                await page.click('button[data-testid="show-phone"]')
                logger.info("Clicked phone reveal button")
                
                # Wait for phone to appear
                await page.wait_for_selector('a[data-testid="contact-phone"]', timeout=5000)
                
                # Extract phone
                phone_element = await page.query_selector('a[data-testid="contact-phone"]')
                if phone_element:
                    href = await phone_element.get_attribute('href')
                    if href and href.startswith('tel:'):
                        phone = re.sub(r"[^\d+]", "", href.replace('tel:', ''))
                        logger.info(f"Successfully extracted phone with session: {phone}")
                        return ExtractionResult([phone], None)
            
            except Exception as e:
                logger.error(f"Failed to extract phone with session: {e}")
            
            # Fallback to searching in page content
            return await _extract_from_page_content(page)
            
    except Exception as e:
        logger.error(f"Session extraction error: {e}")
        return await _parse_olx_standard(ad_url, proxy)


async def _parse_olx_standard(
    ad_url: str, proxy: Optional[str] = None
) -> ExtractionResult:
    """Standard extraction without login (original method)."""
    try:
        # Use extraction client to click phone button and get content
        result = await extraction_client.extract_content_async(
            url=ad_url,
            proxy=proxy,
            timeout=REQUEST_TIMEOUT,
            wait_after_load=3000,
            execute_script="""
                // Close popups first
                const cookieButton = document.querySelector('button[data-testid*="cookie"]');
                if (cookieButton) cookieButton.click();
                
                const surveyCloseButton = document.querySelector('div[data-testid="survey-container"] button[aria-label="Close"]');
                if (surveyCloseButton) surveyCloseButton.click();
                
                // Wait a bit for popups to close
                await new Promise(resolve => setTimeout(resolve, 1000));
                
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


async def _close_olx_popups(page) -> None:
    """Close common OLX popups (cookies, survey, etc.)"""
    try:
        # Close cookie banner
        try:
            await page.wait_for_selector('button[data-testid*="cookie"]', timeout=3000)
            await page.click('button[data-testid*="cookie"]')
            logger.info("Closed cookie banner")
            await page.wait_for_timeout(1000)
        except Exception:
            logger.debug("No cookie banner found")
        
        # Close survey popup
        try:
            await page.wait_for_selector('div[data-testid="survey-container"]', timeout=3000)
            await page.click('div[data-testid="survey-container"] button[aria-label="Close"]')
            logger.info("Closed survey popup")
            await page.wait_for_timeout(1000)
        except Exception:
            logger.debug("No survey popup found")
            
    except Exception as e:
        logger.debug(f"Error closing popups: {e}")


async def _extract_from_page_content(page) -> ExtractionResult:
    """Extract phone numbers from page content."""
    try:
        content = await page.content()
        phone_pattern = re.compile(r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}")
        matches = phone_pattern.findall(content)
        
        if matches:
            phones = list(set([re.sub(r"[^\d+]", "", phone) for phone in matches]))
            logger.info(f"Found phones in page content: {phones}")
            return ExtractionResult(phones, None)
    except Exception as e:
        logger.error(f"Failed to extract from page content: {e}")
    
    return ExtractionResult([], None)


# Helper function to add a new session
async def add_olx_session(email: str, password: str) -> bool:
    """Login to OLX and save the session."""
    try:
        from camoufox.async_api import AsyncCamoufox
        
        logger.info(f"Logging in to OLX as {email}")
        
        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            
            # Navigate to login page
            await page.goto("https://www.olx.ua/uk/account/login/")
            
            # Fill login form
            await page.fill('input[name="username"]', email)
            await page.fill('input[name="password"]', password)
            
            # Submit
            await page.click('button[type="submit"]')
            
            # Wait for redirect
            await page.wait_for_navigation(timeout=10000)
            
            # Check if logged in
            if 'login' not in page.url:
                # Get cookies
                cookies = await page.context.cookies()
                
                # Save session
                _session_manager.save_session(cookies, email)
                logger.info(f"Successfully saved OLX session for {email}")
                return True
            else:
                logger.error("Login failed - still on login page")
                return False
                
    except Exception as e:
        logger.error(f"Failed to add OLX session: {e}")
        return False
