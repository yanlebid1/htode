#!/usr/bin/env python3
"""
Visual test script for debugging OLX phone parsing with Camoufox.
This script runs Camoufox in non-headless mode so you can see what's happening.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from test_phone_parser import test_olx_url


async def main():
    """Main visual test function."""
    # Default test URL from your logs
    default_url = "https://www.olx.ua/d/uk/obyavlenie/2-kom-kv-zhk-gertsen-park-ul-gertsena-35-metro-dorogozhichi-10-min-IDY4Sb1.html"

    # Get URL from command line or use default
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        test_url = default_url

    print(f"🧪 Visual testing with URL: {test_url}")
    print("👀 Browser will open in non-headless mode - you can watch what happens!")
    print("⏳ The script will pause at key moments so you can observe...")

    # Run in non-headless mode so you can see what's happening
    await test_olx_url(test_url, proxy=None, headless=False)

    print("🏁 Visual testing completed!")


if __name__ == "__main__":

    asyncio.run(main())
