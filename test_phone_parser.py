#!/usr/bin/env python3
"""
Test script for debugging OLX phone parsing with Camoufox.
This script allows you to test the phone parser locally with specific OLX URLs.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from common.utils.phone_parser import _parse_olx_camoufox, extract_phone_numbers_from_resource
from common.utils import logger


async def test_olx_url(url: str, proxy: Optional[str] = None, headless: bool = True):
    """Test a single OLX URL with detailed debugging."""
    print(f"\n{'='*60}")
    print(f"Testing URL: {url}")
    print(f"Proxy: {proxy or 'None'}")
    print(f"Headless: {headless}")
    print(f"{'='*60}")
    
    try:
        # Test with the direct Camoufox function
        result = await _parse_olx_camoufox_debug(url, proxy, headless)
        
        print(f"\nResult:")
        print(f"  Phone numbers: {result.phone_numbers}")
        print(f"  Viber link: {result.viber_link}")
        
        if result.phone_numbers:
            print(f"✅ SUCCESS: Found {len(result.phone_numbers)} phone number(s)")
        else:
            print(f"❌ FAILED: No phone numbers found")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


async def _parse_olx_camoufox_debug(ad_url: str, proxy: Optional[str] = None, headless: bool = True):
    """Debug version of _parse_olx_camoufox with more verbose output and screenshots."""
    from camoufox.async_api import AsyncCamoufox
    from common.utils.phone_parser import ExtractionResult, _random_ua
    import urllib.parse
    import re
    
    print(f"🔍 Starting Camoufox debug session...")
    
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
            print(f"🌐 Using proxy: {proxy_config['server']}")

        # Initialize Camoufox with proper configuration
        camoufox_args = {
            "proxy": proxy_config,
            "headless": headless,
            "os": "windows",  # Use Windows OS to mimic real user
            "locale": "uk-UA",  # Set Ukrainian locale
            "geoip": True,  # Enable geolocation spoofing
            "block_webrtc": True,  # Prevent WebRTC leaks
            "humanize": True,  # Enable human-like cursor movements
        }

        # Remove None values
        camoufox_args = {k: v for k, v in camoufox_args.items() if v is not None}
        
        print(f"🚀 Launching Camoufox with args: {camoufox_args}")

        async with AsyncCamoufox(**camoufox_args) as browser:
            page = await browser.new_page()

            print(f"🌍 Navigating to: {ad_url}")
            await page.goto(ad_url, wait_until="domcontentloaded", timeout=30000)
            
            # Take initial screenshot
            await take_screenshot(page, "01_initial_page")
            
            # Get page title and URL for debugging
            title = await page.title()
            current_url = page.url
            print(f"📄 Page title: {title}")
            print(f"🔗 Current URL: {current_url}")

            # Handle cookie banner if it appears
            cookie_banner_selector = 'button[data-testid="dismiss-cookies-banner"]'
            print(f"🍪 Checking for cookie banner: {cookie_banner_selector}")
            try:
                # Wait for cookie banner with shorter timeout
                await page.wait_for_selector(cookie_banner_selector, timeout=3000)
                print("✅ Found cookie banner, dismissing...")
                await page.click(cookie_banner_selector)
                print("✅ Cookie banner dismissed")
                await page.wait_for_timeout(1000)  # Wait a bit after dismissing
                await take_screenshot(page, "02_cookies_dismissed")
            except Exception as e:
                print(f"ℹ️ No cookie banner found or already dismissed: {e}")
                await take_screenshot(page, "02_no_cookies")

            # Wait for the ad action buttons container
            # ad_action_selector = 'div[data-testid="ad-action-buttons"]'
            ad_action_selector = 'div[data-testid="phones-container"]'
            # btn_selector = 'button[data-cy="ad-contact-phone"]'
            btn_selector = 'button[data-testid="show-phone"]'
            print(f"🔍 Looking for ad action buttons: {ad_action_selector}")
            try:
                await page.wait_for_selector(ad_action_selector, timeout=8000)
                print("✅ Found ad action buttons container")
                await take_screenshot(page, "03_found_buttons")
            except Exception as e:
                print(f"❌ Ad action buttons not found: {e}")
                await take_screenshot(page, "03_no_buttons")

            # Check if phone button exists
            print(f"🔍 Looking for phone button: {btn_selector}")
            phone_button = await page.query_selector(btn_selector)
            if not phone_button:
                print("❌ Phone button not found")
                await take_screenshot(page, "04_no_phone_button")
                return ExtractionResult([], None)
            
            print("✅ Found phone button")
            button_text = await phone_button.inner_text()
            print(f"📱 Phone button text: '{button_text}'")

            # Click the phone button
            print("🖱️ Clicking phone button...")
            await page.click(btn_selector, force=True)
            print("✅ Clicked phone reveal button")
            
            # Wait a bit for the action to complete
            await page.wait_for_timeout(2000)
            await take_screenshot(page, "05_after_click")

            # Wait for the link that contains the phone number
            # link_selector = 'button[data-cy="ad-contact-phone"] a[data-testid="contact-phone"]'
            link_selector = 'div[data-testid="phones-container"] a[data-testid="contact-phone"]'
            print(f"🔍 Looking for phone link: {link_selector}")
            
            try:
                await page.wait_for_selector(link_selector, timeout=8000)
                print("✅ Phone link appeared")
                await take_screenshot(page, "06_phone_link_found")
            except Exception as e:
                print(f"❌ Phone link did not appear: {e}")
                await take_screenshot(page, "06_no_phone_link")
                
                # Try to find any links in the phone button
                # phone_links = await page.query_selector_all('button[data-cy="ad-contact-phone"] a')
                phone_links = await page.query_selector_all('div[data-testid="phones-container"] a[data-testid="contact-phone"]')
                print(f"🔍 Found {len(phone_links)} links in phone button:")
                for i, link in enumerate(phone_links):
                    try:
                        href = await link.get_attribute('href')
                        text = await link.inner_text()
                        data_testid = await link.get_attribute('data-testid')
                        print(f"  Link {i+1}: href='{href}' text='{text}' data-testid='{data_testid}'")
                    except:
                        print(f"  Link {i+1}: <could not read attributes>")
                
                return ExtractionResult([], None)

            # Extract the phone number
            link_el = await page.query_selector(link_selector)
            href_val = await link_el.get_attribute("href") if link_el else None

            if not href_val:
                print("❌ Failed to extract href with phone")
                return ExtractionResult([], None)

            print(f"📞 Raw href value: {href_val}")
            
            # href format example: tel:(068)6771621
            phone_raw = href_val.replace('tel:', '').strip()
            # Remove parentheses, spaces, dashes
            phone_clean = re.sub(r'[\s\-()]+', '', phone_raw)

            print(f"✅ Successfully extracted phone: {phone_clean}")
            await take_screenshot(page, "07_success")
            
            return ExtractionResult([phone_clean], None)

    except Exception as e:
        print(f"❌ Camoufox extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return ExtractionResult([], None)


async def take_screenshot(page, name: str):
    """Take a screenshot for debugging."""
    try:
        ss_dir = Path.cwd() / "debug_screenshots"
        ss_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ss_path = ss_dir / f"{name}_{timestamp}.png"
        await page.screenshot(path=str(ss_path), full_page=True)
        print(f"📸 Screenshot saved: {ss_path}")
    except Exception as e:
        print(f"❌ Failed to take screenshot: {e}")


async def main():
    """Main test function."""
    # Test URLs - replace with actual OLX URLs you want to test
    test_urls = [
        "https://www.olx.ua/d/uk/obyavlenie/orenda-1-kmnatna-kvartira-vul-hmchna-IDYeznF.html",
        # Add more URLs here for testing
    ]
    
    # You can also pass URLs as command line arguments
    if len(sys.argv) > 1:
        test_urls = sys.argv[1:]
    
    print(f"🧪 Testing {len(test_urls)} URL(s)")
    
    for url in test_urls:
        await test_olx_url(url, proxy=None, headless=True)
        print("\n" + "="*60 + "\n")
    
    print("🏁 Testing completed!")
    print(f"📁 Check debug_screenshots/ folder for screenshots")


if __name__ == "__main__":
    # Import here to avoid issues if running from different directories
    from typing import Optional
    
    asyncio.run(main()) 