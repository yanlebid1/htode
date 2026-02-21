"""
AdsPower Profile Manager for OLX Phone Extraction
Manages multiple AdsPower profiles and OLX accounts with rotation logic.
"""

import json
import os
import time
import random
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from common.utils import logger


@dataclass
class AdsPowerProfile:
    """Configuration for an AdsPower profile"""
    profile_id: str
    profile_name: str
    olx_email: Optional[str] = None
    olx_password: Optional[str] = None
    last_used: Optional[str] = None
    usage_count: int = 0
    max_daily_usage: int = 50  # Max phone extractions per day
    is_active: bool = True


@dataclass
class ExtractionStats:
    """Statistics for phone extraction"""
    total_extractions: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    last_extraction: Optional[str] = None


class AdsPowerManager:
    """Manages multiple AdsPower profiles for phone extraction"""
    
    def __init__(self, config_file: str = "adspower_config.json"):
        self.config_file = Path(config_file)
        self.profiles: List[AdsPowerProfile] = []
        self.current_profile_index = 0
        self.stats = ExtractionStats()
        self.adspower_api_url = os.getenv("ADSPOWER_API_URL", "http://local.adspower.net:50325")
        self.chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/tmp/chromedriver-linux64/chromedriver")
        
        self.load_config()
        
    def load_config(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.profiles = [AdsPowerProfile(**profile) for profile in data.get('profiles', [])]
                    if 'stats' in data:
                        self.stats = ExtractionStats(**data['stats'])
                    logger.info("Loaded AdsPower profiles", extra={"count": len(self.profiles)})
            except Exception as e:
                logger.error("Failed to load AdsPower config", extra={"error": str(e)})
                self.profiles = []
        else:
            # Create default config template
            self.create_default_config()
    
    def create_default_config(self):
        """Create a default configuration file template with scaled profiles"""
        default_profiles = [
            AdsPowerProfile(
                profile_id="PROFILE_ID_1",  # Replace with your actual profile ID
                profile_name="Profile 1",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # Increased from 50 for scaling
            ),
            AdsPowerProfile(
                profile_id="PROFILE_ID_2",  # Replace with your actual profile ID  
                profile_name="Profile 2",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # Increased from 50 for scaling
            ),
            AdsPowerProfile(
                profile_id="PROFILE_ID_3",  # Replace with your actual profile ID  
                profile_name="Profile 3",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # High usage limit for scaling
            ),
            AdsPowerProfile(
                profile_id="PROFILE_ID_4",  # Replace with your actual profile ID  
                profile_name="Profile 4",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # High usage limit for scaling
            ),
            AdsPowerProfile(
                profile_id="PROFILE_ID_5",  # Replace with your actual profile ID  
                profile_name="Profile 5",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # High usage limit for scaling
            ),
            AdsPowerProfile(
                profile_id="PROFILE_ID_6",  # Replace with your actual profile ID  
                profile_name="Profile 6",
                olx_email=None,  # Optional: for reference only (manual login expected)
                olx_password=None,  # Optional: for reference only (manual login expected)
                max_daily_usage=200  # High usage limit for scaling
            ),
        ]
        
        data = {
            'profiles': [asdict(profile) for profile in default_profiles],
            'stats': asdict(self.stats)
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info("Created default config", extra={"config_file": str(self.config_file)})
        logger.warning("Please update the config file with your actual AdsPower profile IDs and OLX credentials")
        
        self.profiles = default_profiles
    
    def save_config(self):
        """Save current configuration to file"""
        data = {
            'profiles': [asdict(profile) for profile in self.profiles],
            'stats': asdict(self.stats)
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_next_available_profile(self) -> Optional[AdsPowerProfile]:
        """Get the next available profile using round-robin with usage limits"""
        if not self.profiles:
            logger.error("No AdsPower profiles configured")
            return None
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Try each profile once
        for _ in range(len(self.profiles)):
            profile = self.profiles[self.current_profile_index]
            self.current_profile_index = (self.current_profile_index + 1) % len(self.profiles)
            
            # Check if profile is active and under daily limit
            if (profile.is_active and 
                profile.usage_count < profile.max_daily_usage and
                (not profile.last_used or profile.last_used != today)):
                
                return profile
        
        # If all profiles are at daily limit, wait and try again
        logger.warning("All profiles at daily usage limit, using least used profile")
        return min(self.profiles, key=lambda p: p.usage_count)
    
    def start_profile(self, profile: AdsPowerProfile) -> Optional[Dict]:
        """Start an AdsPower profile and return connection details"""
        try:
            url = f"{self.adspower_api_url}/api/v1/browser/start"
            params = {
                "user_id": profile.profile_id,
                "open_tabs": 1
            }
            
            logger.info("Starting AdsPower profile", extra={"profile": profile.profile_name})
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    logger.info("Successfully started profile", extra={"profile": profile.profile_name})
                    return data["data"]
                else:
                    logger.error("Failed to start profile", extra={"msg": data.get("msg")})
                    return None
            else:
                logger.error("HTTP error starting profile", extra={"status_code": response.status_code})
                return None
                
        except Exception as e:
            logger.error("Exception starting profile", extra={"profile": profile.profile_name, "error": str(e)})
            return None
    
    def stop_profile(self, profile: AdsPowerProfile) -> bool:
        """Stop an AdsPower profile"""
        try:
            url = f"{self.adspower_api_url}/api/v1/browser/stop"
            params = {"user_id": profile.profile_id}
            
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                success = data.get("code") == 0
                if success:
                    logger.info("Successfully stopped profile", extra={"profile": profile.profile_name})
                else:
                    logger.error("Failed to stop profile", extra={"msg": data.get("msg")})
                return success
            else:
                logger.error("HTTP error stopping profile", extra={"status_code": response.status_code})
                return False
                
        except Exception as e:
            logger.error("Exception stopping profile", extra={"profile": profile.profile_name, "error": str(e)})
            return False
    
    def create_driver(self, connection_data: Dict) -> Optional[webdriver.Chrome]:
        """Create a Selenium WebDriver connected to AdsPower browser"""
        try:
            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", connection_data["ws"]["selenium"])
            
            driver = webdriver.Chrome(
                executable_path=self.chromedriver_path,
                options=chrome_options
            )
            
            return driver
            
        except Exception as e:
            logger.error("Failed to create driver", extra={"error": str(e)})
            return None
    

    
    def extract_phone_from_olx_ad(self, driver: webdriver.Chrome, ad_url: str, profile: AdsPowerProfile) -> Optional[str]:
        """Extract phone number from an OLX ad using AdsPower browser"""
        try:
            logger.info("Extracting phone", extra={"ad_url": ad_url, "profile": profile.profile_name})
            
            # Navigate to ad
            driver.get(ad_url)
            time.sleep(3)
            
            # Accept cookies if present
            try:
                cookie_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid*='cookie']"))
                )
                cookie_button.click()
                time.sleep(1)
            except TimeoutException:
                pass
            
            # Close survey popup if present
            try:
                survey_close_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@data-testid='survey-container']//button[@aria-label='Close']"))
                )
                survey_close_button.click()
                logger.info("Closed survey popup")
                time.sleep(1)
            except TimeoutException:
                logger.debug("No survey popup found")
            except Exception as e:
                logger.debug("Failed to close survey popup", extra={"error": str(e)})
            
            # Scroll down to find phone button
            max_scrolls = 5
            phone_button = None
            
            for scroll in range(max_scrolls):
                try:
                    # Try different selectors for phone button
                    selectors = [
                        "[data-cy='ad-contact-phone']",
                        "button[data-testid='show-phone']",
                        "button[data-testid='call-button']",
                        ".phone-button",
                        "button[aria-label*='phone']",
                        "button[aria-label*='телефон']"
                    ]
                    
                    for selector in selectors:
                        try:
                            phone_button = driver.find_element(By.CSS_SELECTOR, selector)
                            if phone_button.is_displayed():
                                break
                        except NoSuchElementException:
                            continue
                    
                    if phone_button and phone_button.is_displayed():
                        break
                    
                    # Scroll down
                    driver.execute_script("window.scrollBy(0, 500);")
                    time.sleep(1)
                    
                except Exception as e:
                    logger.debug("Scroll failed", extra={"scroll": scroll + 1, "error": str(e)})
            
            if not phone_button:
                logger.error("Phone button not found")
                return None
            
            # Click phone button using multiple strategies
            try:
                # Try regular click
                phone_button.click()
            except Exception:
                try:
                    # Try JavaScript click
                    driver.execute_script("arguments[0].click();", phone_button)
                except Exception:
                    try:
                        # Try ActionChains click
                        ActionChains(driver).move_to_element(phone_button).click().perform()
                    except Exception as e:
                        logger.error("All click methods failed", extra={"error": str(e)})
                        return None
            
            time.sleep(2)
            
            # Extract phone number
            phone_selectors = [
                "a[href^='tel:']",
                "[data-testid='contact-phone']",
                ".phone-number",
                "span[class*='phone']"
            ]
            
            for selector in phone_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            phone_text = element.get_attribute('href') or element.text
                            if phone_text:
                                # Clean phone number
                                phone = phone_text.replace('tel:', '').strip()
                                if phone and len(phone) >= 10:
                                    logger.info("Successfully extracted phone")
                                    
                                    # Update profile stats
                                    profile.usage_count += 1
                                    profile.last_used = datetime.now().strftime('%Y-%m-%d')
                                    self.stats.successful_extractions += 1
                                    self.stats.total_extractions += 1
                                    self.stats.last_extraction = datetime.now().isoformat()
                                    self.save_config()
                                    
                                    return phone
                except Exception as e:
                    logger.debug("Phone extraction with selector failed", extra={"selector": selector, "error": str(e)})
            
            logger.error("No phone number found in page")
            self.stats.failed_extractions += 1
            self.stats.total_extractions += 1
            self.save_config()
            return None
            
        except Exception as e:
            logger.error("Error extracting phone", extra={"error": str(e)})
            self.stats.failed_extractions += 1
            self.stats.total_extractions += 1
            self.save_config()
            return None
    
    def extract_phone_with_rotation(self, ad_url: str) -> Optional[str]:
        """Extract phone using profile rotation"""
        profile = self.get_next_available_profile()
        if not profile:
            logger.error("No available profiles for extraction")
            return None
        
        # Add random delay to avoid detection
        time.sleep(random.uniform(2, 8))
        
        connection_data = self.start_profile(profile)
        if not connection_data:
            return None
        
        driver = None
        try:
            driver = self.create_driver(connection_data)
            if not driver:
                return None
            
            # Note: Manual login expected - profiles should be pre-logged in
            logger.info("Using pre-logged AdsPower profile (manual login expected)")
            
            # Extract phone
            phone = self.extract_phone_from_olx_ad(driver, ad_url, profile)
            return phone
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.stop_profile(profile)
    
    def get_stats(self) -> Dict:
        """Get extraction statistics"""
        return {
            'total_profiles': len(self.profiles),
            'active_profiles': len([p for p in self.profiles if p.is_active]),
            'total_extractions': self.stats.total_extractions,
            'successful_extractions': self.stats.successful_extractions,
            'failed_extractions': self.stats.failed_extractions,
            'success_rate': (self.stats.successful_extractions / self.stats.total_extractions * 100) if self.stats.total_extractions > 0 else 0,
            'last_extraction': self.stats.last_extraction
        }


# Global manager instance
adspower_manager = AdsPowerManager() 