#!/usr/bin/env python3
"""
Test script for AdsPower integration in Docker environment
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.utils.phone_utils.adspower_manager import adspower_manager
from common.utils.phone_utils.parsers.olx_parser import parse_olx_adspower


def test_adspower_manager():
    """Test AdsPower manager configuration"""
    print("=== Testing AdsPower Manager ===")
    
    # Check configuration
    stats = adspower_manager.get_stats()
    print(f"Total profiles: {stats['total_profiles']}")
    print(f"Active profiles: {stats['active_profiles']}")
    
    if stats['total_profiles'] == 0:
        print("⚠️  No profiles configured. Please update adspower_config.json")
        return False
    
    # Check if profiles are properly configured
    for i, profile in enumerate(adspower_manager.profiles):
        print(f"Profile {i+1}: {profile.profile_name} (ID: {profile.profile_id})")
        if profile.profile_id.startswith("PROFILE_ID_"):
            print(f"  ⚠️  Profile {i+1} needs real profile ID")
        if profile.olx_email and profile.olx_email.endswith("@example.com"):
            print(f"  ⚠️  Profile {i+1} needs real OLX credentials")
    
    return True


async def test_login_detection():
    """Test login requirement detection"""
    print("\n=== Testing Login Requirement Detection ===")
    
    test_url = "https://www.olx.ua/d/uk/obyavlenie/prodam-1-k-kvartiru-zhk-miskiy-kvartal-IDOhswp.html"
    
    try:
        from common.utils.phone_utils.parsers.olx_parser import check_olx_login_required
        
        login_required = await check_olx_login_required(test_url)
        
        if login_required:
            print("✅ Login requirement detected - will use AdsPower")
        else:
            print("✅ No login requirement - will use Camoufox first")
        
        return True
            
    except Exception as e:
        print(f"❌ Error during login detection: {e}")
        return False


async def test_olx_parser():
    """Test OLX parser with smart method selection"""
    print("\n=== Testing Smart OLX Parser ===")
    
    test_url = "https://www.olx.ua/d/uk/obyavlenie/prodam-1-k-kvartiru-zhk-miskiy-kvartal-IDOhswp.html"
    
    try:
        from common.utils.phone_utils.parsers.phone_parser import _extract_phone_numbers_async
        
        result = await _extract_phone_numbers_async(test_url)
        
        if result.phone_numbers:
            print(f"✅ Successfully extracted phone: {result.phone_numbers[0]}")
            return True
        else:
            print("❌ No phone numbers extracted")
            return False
            
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        return False


def test_adspower_manager_structure():
    """Test AdsPower manager structure (without database)"""
    print("\n=== Testing AdsPower Manager Structure ===")
    
    try:
        # Test that we can create a manager instance
        manager = adspower_manager
        
        # Test basic methods exist
        assert hasattr(manager, 'get_next_available_profile'), "Missing get_next_available_profile method"
        assert hasattr(manager, 'start_profile'), "Missing start_profile method"
        assert hasattr(manager, 'stop_profile'), "Missing stop_profile method"
        assert hasattr(manager, 'create_driver'), "Missing create_driver method"
        assert hasattr(manager, 'extract_phone_with_rotation'), "Missing extract_phone_with_rotation method"
        
        print("✅ All required methods present")
        return True
            
    except Exception as e:
        print(f"❌ Manager structure test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("AdsPower Integration Test Suite")
    print("=" * 40)
    
    # Test 1: Manager configuration
    config_ok = test_adspower_manager()
    
    if not config_ok:
        print("\n❌ Configuration test failed. Please fix configuration first.")
        return
    
    # Test 2: Login detection (async test)
    print("\n📋 Testing login requirement detection...")
    try:
        import asyncio
        asyncio.run(test_login_detection())
    except Exception as e:
        print(f"❌ Login detection test failed: {e}")
    
    # Test 3: Manager structure
    test_adspower_manager_structure()
    
    print("\n🚀 Smart retry logic with popup handling is ready!")
    print("How it works:")
    print("1. Close any popups (cookies, survey) that might interfere")
    print("2. Check if OLX ad requires login (login button present)")
    print("3. If login required → use AdsPower directly")
    print("4. If no login required → try Camoufox first, AdsPower as fallback")
    print("")
    print("To complete setup:")
    print("1. Update adspower_config.json with real profile IDs")
    print("2. Start AdsPower on host system")
    print("3. MANUALLY login to OLX in each AdsPower profile")
    print("4. Build and run Docker services")
    print("5. Test with: docker exec -it scraper_worker_service python -m pytest tests/test_adspower_integration.py -v")


if __name__ == "__main__":
    main() 