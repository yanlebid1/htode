#!/usr/bin/env python3
"""
Test script for the Camoufox service.
Run this after starting the service with docker-compose.
"""
import asyncio
import sys
from common.utils.camoufox_client import camoufox_client


async def test_camoufox_service():
    """Test the Camoufox service with various URLs"""

    # Test health check
    print("🏥 Testing health check...")
    is_healthy = await camoufox_client.health_check_async()
    if is_healthy:
        print("✅ Service is healthy")
    else:
        print("❌ Service is not healthy")
        return

    # Test URLs
    test_cases = [
        {
            "url": "https://example.com",
            "extraction_type": "content",
            "description": "Simple content extraction",
        },
        {
            "url": "https://flatfy.ua/uk/redirect/3200295090",
            "extraction_type": "content",
            "description": "Flatfy redirect resolution",
        },
        {
            "url": "https://www.olx.ua/d/uk/obyavlenie/prodam-2k-kvartiru-v-zhk-kreyser-avrora-IDU6bpN.html",
            "extraction_type": "phone_numbers",
            "description": "OLX phone extraction",
        },
    ]

    for test in test_cases:
        print(f"\n📋 Test: {test['description']}")
        print(f"   URL: {test['url']}")

        try:
            result = await camoufox_client.extract_async(
                url=test["url"], extraction_type=test["extraction_type"], timeout=30
            )

            if result["status"] == "success":
                print("✅ Success!")
                print(f"   Status code: {result.get('status_code')}")
                print(f"   Final URL: {result.get('final_url')}")

                if test["extraction_type"] == "phone_numbers":
                    data = result.get("data", {})
                    phones = data.get("phone_numbers", [])
                    viber = data.get("viber_link")
                    print(f"   Phone numbers: {phones}")
                    if viber:
                        print(f"   Viber link: {viber}")
                elif test["extraction_type"] == "content":
                    content = result.get("data", {}).get("content", "")
                    print(f"   Content length: {len(content)} chars")
            else:
                print(f"❌ Failed: {result.get('error')}")

        except Exception as e:
            print(f"❌ Exception: {e}")


if __name__ == "__main__":
    # Check if running inside Docker
    import os

    if not os.path.exists("/.dockerenv"):
        print("⚠️  This script should be run inside the Docker container")
        print(
            "   Run: docker-compose exec scraper_worker_service python test_camoufox_service.py"
        )
        sys.exit(1)

    asyncio.run(test_camoufox_service())
