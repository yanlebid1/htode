#!/usr/bin/env python3
"""
Parser Extraction Test Tool

Test phone number extraction from various real estate websites using different methods.
Works both locally and in Docker environments.

Usage:
    python test_parser_extraction.py <URL> [--method METHOD] [--service SERVICE] [--proxy PROXY]
    
Examples:
    # Test with automatic service selection
    python test_parser_extraction.py "https://www.olx.ua/d/uk/obyavlenie/..."
    
    # Force WebCrawler with specific method
    python test_parser_extraction.py "https://lun.ua/..." --service webcrawler --method curl_cffi
    
    # Force Camoufox
    python test_parser_extraction.py "https://dom.ria.com/..." --service camoufox
    
    # Test with proxy
    python test_parser_extraction.py "https://www.olx.ua/..." --proxy "http://user:pass@proxy:8080"
"""

import asyncio
import argparse
import sys
import os
from typing import Optional
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.utils.phone_utils.site_config import (
    get_service_for_url,
    get_webcrawler_methods_for_url,
    ExtractionService,
    SITE_CONFIG,
)
from common.utils.extraction_client import extraction_client
from common.utils.phone_utils.parsers.phone_parser import _extract_phone_numbers_async
from common.utils import logger
import logging

# Set up detailed logging for testing
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class TestResult:
    """Container for test results"""

    def __init__(self):
        self.url = ""
        self.detected_service = ""
        self.used_service = ""
        self.used_method = ""
        self.phone_numbers = []
        self.viber_link = None
        self.final_url = ""
        self.status_code = None
        self.error = None
        self.execution_time = 0
        self.content_preview = ""


async def test_extraction_client(
    url: str,
    force_service: Optional[str] = None,
    force_method: Optional[str] = None,
    proxy: Optional[str] = None,
) -> TestResult:
    """Test extraction using the extraction client directly"""
    result = TestResult()
    result.url = url

    start_time = datetime.now()

    try:
        # Detect which service would be used
        detected_service = get_service_for_url(url)
        result.detected_service = detected_service.value

        print(f"\n📍 URL: {url}")
        print(f"🔍 Detected service: {detected_service.value}")

        if detected_service == ExtractionService.WEBCRAWLER:
            methods = get_webcrawler_methods_for_url(url)
            if methods:
                print(f"📋 Preferred methods: {[m.value for m in methods]}")

        # Override service if requested
        if force_service:
            print(f"⚠️  Forcing service: {force_service}")

        # Prepare extraction parameters
        extract_params = {
            "url": url,
            "proxy": proxy,
            "timeout": 30,
            "wait_after_load": 3000,
        }

        # Add browser-specific parameters for sites that need interaction
        if any(domain in url for domain in ["olx.ua", "dom.ria"]):
            extract_params[
                "execute_script"
            ] = """
                // Try to find and click phone reveal button
                const buttons = document.querySelectorAll('button, a, div, span');
                for (const btn of buttons) {
                    const text = (btn.textContent || '').toLowerCase();
                    if (text.includes('показати') || text.includes('phone') || 
                        text.includes('телефон') || text.includes('call')) {
                        btn.click();
                        return 'Clicked phone button';
                    }
                }
                return 'No phone button found';
            """
            extract_params["wait_for_selector"] = "[href^='tel:'], .phone-number"

        # Force specific method if requested
        if force_method and force_service == "webcrawler":
            extract_params["headers"] = {"X-Test-Method": force_method}

        print("\n🚀 Starting extraction...")

        # Call extraction client
        if force_service == "webcrawler":
            # Direct call to webcrawler
            extraction_result = await extraction_client._extract_with_webcrawler(
                url, proxy, 30, extract_params.get("headers")
            )
        elif force_service == "camoufox":
            # Direct call to camoufox
            extraction_result = await extraction_client._extract_with_camoufox(
                url,
                proxy,
                30,
                extract_params.get("wait_after_load", 3000),
                extract_params.get("execute_script"),
                extract_params.get("wait_for_selector"),
            )
        else:
            # Auto-detect
            extraction_result = await extraction_client.extract_content_async(
                **extract_params
            )

        result.used_service = extraction_result.get("service_used", "unknown")
        result.used_method = extraction_result.get("method_used", "N/A")
        result.final_url = extraction_result.get("final_url", url)
        result.status_code = extraction_result.get("status_code")

        if extraction_result["status"] == "success":
            content = extraction_result.get("content", "")
            result.content_preview = (
                content[:500] + "..." if len(content) > 500 else content
            )

            # Extract phone numbers using the parser
            print("\n🔍 Extracting phone numbers...")
            from common.utils.phone_utils.parsers import (
                domria_parser,
                lun_parser,
                rieltor_parser,
                fallback_parser,
            )
            from common.utils.phone_utils.phone_models import ExtractionResult

            # Route to appropriate parser
            phones_result = ExtractionResult([], None)

            if "olx.ua" in result.final_url:
                from bs4 import BeautifulSoup
                import re

                soup = BeautifulSoup(content, "lxml")

                # Extract from tel: links
                phones = []
                tel_links = soup.find_all(href=re.compile(r"^tel:"))
                for link in tel_links:
                    phone = link.get("href", "").replace("tel:", "").strip()
                    if phone:
                        phones.append(re.sub(r"[^\d+]", "", phone))

                # Also try phone patterns
                if not phones:
                    phone_pattern = re.compile(
                        r"\+?38\s*\(?\d{3}\)?\s*\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                    )
                    matches = phone_pattern.findall(content)
                    phones = list(set([re.sub(r"[^\d+]", "", p) for p in matches]))

                phones_result = ExtractionResult(phones, None)

            elif "dom.ria" in result.final_url:
                phones_result = domria_parser.parse_domria_page(content, None)
            elif "lun.ua" in result.final_url:
                phones_result = lun_parser.parse_lun_page(content)
            elif "rieltor.ua" in result.final_url:
                phones_result = rieltor_parser.parse_rieltor_page(content)
            else:
                phones_result = fallback_parser.fallback_parse(content)

            result.phone_numbers = phones_result.phone_numbers
            result.viber_link = phones_result.viber_link

        else:
            result.error = extraction_result.get("error", "Unknown error")

    except Exception as e:
        result.error = str(e)
        logger.error(f"Test failed with exception: {e}", exc_info=True)

    result.execution_time = (datetime.now() - start_time).total_seconds()
    return result


async def test_full_parser_flow(url: str, proxy: Optional[str] = None) -> TestResult:
    """Test using the full parser flow (phone_parser.py)"""
    result = TestResult()
    result.url = url

    start_time = datetime.now()

    try:
        print(f"\n🔄 Testing full parser flow for: {url}")

        # Use the actual parser
        extraction_result = await _extract_phone_numbers_async(url, proxy)

        result.phone_numbers = extraction_result.phone_numbers
        result.viber_link = extraction_result.viber_link

        # We don't get service info from this method
        result.detected_service = "auto"
        result.used_service = "auto"

    except Exception as e:
        result.error = str(e)
        logger.error(f"Parser test failed: {e}", exc_info=True)

    result.execution_time = (datetime.now() - start_time).total_seconds()
    return result


def print_results(result: TestResult):
    """Pretty print test results"""
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)

    print(f"\n🌐 URL: {result.url}")
    if result.final_url and result.final_url != result.url:
        print(f"➡️  Final URL: {result.final_url}")

    print("\n🛠️  Service Detection:")
    print(f"   - Detected: {result.detected_service}")
    print(f"   - Used: {result.used_service}")
    if result.used_method:
        print(f"   - Method: {result.used_method}")

    print("\n📡 Response:")
    print(f"   - Status Code: {result.status_code or 'N/A'}")
    print(f"   - Execution Time: {result.execution_time:.2f}s")

    if result.error:
        print(f"\n❌ Error: {result.error}")
    else:
        print("\n✅ Success!")

        if result.phone_numbers:
            print(f"\n📞 Phone Numbers Found: {len(result.phone_numbers)}")
            for i, phone in enumerate(result.phone_numbers, 1):
                print(f"   {i}. {phone}")
        else:
            print("\n⚠️  No phone numbers found")

        if result.viber_link:
            print(f"\n💬 Viber Link: {result.viber_link}")

        if result.content_preview:
            print("\n📄 Content Preview:")
            print("-" * 40)
            print(result.content_preview)
            print("-" * 40)


def print_site_configuration():
    """Print current site configuration"""
    print("\n📋 SITE CONFIGURATION")
    print("=" * 60)

    for domain, config in SITE_CONFIG.items():
        print(f"\n🌐 {domain}")
        print(f"   Service: {config['service'].value}")
        if "methods" in config:
            print(f"   Methods: {[m.value for m in config['methods']]}")
        print(f"   Info: {config['description']}")


async def main():
    parser = argparse.ArgumentParser(
        description="Test phone extraction from real estate websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("url", nargs="?", help="URL to test")
    parser.add_argument(
        "--service",
        choices=["webcrawler", "camoufox", "auto"],
        default="auto",
        help="Force specific service",
    )
    parser.add_argument(
        "--method",
        choices=["aiohttp", "curl_cffi", "httpx"],
        help="Force specific method (webcrawler only)",
    )
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument(
        "--full-flow",
        action="store_true",
        help="Test full parser flow (phone_parser.py)",
    )
    parser.add_argument(
        "--show-config", action="store_true", help="Show site configuration and exit"
    )

    args = parser.parse_args()

    if args.show_config:
        print_site_configuration()
        return

    if not args.url:
        parser.print_help()
        print("\n" + "=" * 60)
        print_site_configuration()
        return

    # Ensure services are accessible
    if os.getenv("DOCKER_ENV"):
        print("🐳 Running in Docker environment")
    else:
        print("💻 Running in local environment")
        # For local testing, you might want to override service URLs
        os.environ["CAMOUFOX_SERVICE_URL"] = os.getenv(
            "CAMOUFOX_SERVICE_URL", "http://localhost:8100"
        )
        os.environ["WEBCRAWLER_SERVICE_URL"] = os.getenv(
            "WEBCRAWLER_SERVICE_URL", "http://localhost:8200"
        )

    # Run test
    if args.full_flow:
        result = await test_full_parser_flow(args.url, args.proxy)
    else:
        result = await test_extraction_client(
            args.url,
            args.service if args.service != "auto" else None,
            args.method,
            args.proxy,
        )

    # Print results
    print_results(result)


if __name__ == "__main__":
    asyncio.run(main())
