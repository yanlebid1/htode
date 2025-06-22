import requests
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# Configuration
ADSPOWER_PROFILE_ID = "k10no2qx"
OLX_AD_URL = "https://www.olx.ua/d/uk/obyavlenie/zdam-kvartiru-v-tsentr-vul-gorova-vd-vlasnika-IDYkaWJ.html"
CORRECT_CHROMEDRIVER = "/tmp/chromedriver-linux64/chromedriver"

# AdsPower endpoints
start_url = f"http://local.adspower.net:50325/api/v1/browser/start?user_id={ADSPOWER_PROFILE_ID}"
stop_url = f"http://local.adspower.net:50325/api/v1/browser/stop?user_id={ADSPOWER_PROFILE_ID}"

print("📞 AdsPower + OLX Final Solution")
print("=" * 50)

# Start AdsPower browser
print("🚀 Starting AdsPower profile...")
resp = requests.get(start_url).json()

if resp.get("code") != 0:
    print(f"❌ Failed to start profile: {resp.get('msg')}")
    exit(1)

debug_port = resp["data"]["debug_port"]
print(f"✅ AdsPower started on port {debug_port}")

try:
    # Connect with correct ChromeDriver
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(CORRECT_CHROMEDRIVER)
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)
    
    print("✅ Connected to browser!")
    
    # Navigate to OLX ad
    print(f"🌐 Loading OLX ad...")
    driver.get(OLX_AD_URL)
    time.sleep(4)  # Give page time to load
    
    print(f"✅ Page loaded: {driver.title[:50]}...")
    
    # Handle cookie consent with better detection
    print("\n🍪 Checking for cookie banner...")
    cookie_selectors = [
        "#onetrust-accept-btn-handler",
        "[id*='cookie']",
        "[class*='cookie']",
        "button[data-testid*='cookie']",
        "[data-cy*='cookie']",
        "button:contains('Accept')",
        "button:contains('Прийняти')",
        "button:contains('Згоден')"
    ]
    
    cookie_handled = False
    for selector in cookie_selectors:
        try:
            if selector.startswith("button:contains"):
                # Handle text-based selectors
                text = selector.split("'")[1]
                cookie_btn = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
            else:
                cookie_btn = driver.find_element(By.CSS_SELECTOR, selector)
            
            if cookie_btn.is_displayed():
                cookie_btn.click()
                print(f"✅ Accepted cookies using: {selector}")
                cookie_handled = True
                time.sleep(2)
                break
        except:
            continue
    
    if not cookie_handled:
        print("🍪 No cookie banner detected or already handled")
    
    # Scroll down to find phone button
    print("\n📜 Scrolling to find phone button...")
    
    # First, scroll down in steps to load content
    for i in range(3):
        driver.execute_script("window.scrollBy(0, 300);")
        time.sleep(1)
    
    # Now look for phone button with multiple strategies
    print("📞 Looking for phone button...")
    phone_button = None
    phone_selectors = [
        "[data-testid='show-phone']",
        "[data-cy='ad-contact-phone']", 
        "button:contains('показати')",
        "button:contains('Показати телефон')",
        "[data-testid*='phone']",
        "button[class*='phone']"
    ]
    
    for selector in phone_selectors:
        try:
            if "contains" in selector:
                # Handle text-based selectors
                text = selector.split("'")[1]
                phone_button = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
            else:
                phone_button = driver.find_element(By.CSS_SELECTOR, selector)
            
            if phone_button:
                print(f"✅ Found phone button using: {selector}")
                break
        except:
            continue
    
    # If still not found, scroll more and search again
    if not phone_button:
        print("🔍 Button not found, scrolling more...")
        for i in range(3):
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(1)
            
            # Try again
            try:
                phone_button = driver.find_element(By.XPATH, "//button[contains(text(), 'показати')]")
                if phone_button:
                    print("✅ Found phone button after additional scrolling")
                    break
            except:
                continue
    
    if phone_button:
        print("🎯 Preparing to click phone button...")
        
        # Scroll to the button and ensure it's visible
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", phone_button)
        time.sleep(2)
        
        # Check if button is clickable
        if phone_button.is_displayed() and phone_button.is_enabled():
            print("✅ Button is visible and enabled")
            
            # Try multiple click methods
            clicked = False
            
            # Method 1: JavaScript click (most reliable)
            try:
                driver.execute_script("arguments[0].click();", phone_button)
                print("✅ Clicked phone button (JavaScript)")
                clicked = True
            except:
                # Method 2: Regular click
                try:
                    phone_button.click()
                    print("✅ Clicked phone button (regular)")
                    clicked = True
                except:
                    # Method 3: ActionChains
                    try:
                        ActionChains(driver).move_to_element(phone_button).click().perform()
                        print("✅ Clicked phone button (ActionChains)")
                        clicked = True
                    except:
                        pass
            
            if clicked:
                print("⏳ Waiting for phone number to load...")
                time.sleep(4)
                
                # Extract phone number
                phone_found = False
                
                # Method 1: Look for tel: links
                try:
                    phone_links = driver.find_elements(By.XPATH, "//a[starts-with(@href, 'tel:')]")
                    if phone_links:
                        for link in phone_links:
                            phone_text = link.text.strip()
                            if phone_text and 'xxx' not in phone_text.lower():
                                print(f"\n🎉 SUCCESS! Phone number: {phone_text}")
                                phone_found = True
                                break
                except:
                    pass
                
                # Method 2: Look for phone patterns in page
                if not phone_found:
                    try:
                        import re
                        page_source = driver.page_source
                        
                        # Ukrainian phone patterns
                        patterns = [
                            r'\+38\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
                            r'38\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
                            r'0\d{2}\s?\d{3}\s?\d{2}\s?\d{2}'
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, page_source)
                            for match in matches:
                                if 'xxx' not in match and '***' not in match:
                                    print(f"\n🎉 SUCCESS! Phone number found: {match}")
                                    phone_found = True
                                    break
                            if phone_found:
                                break
                    except:
                        pass
                
                # Method 3: Check phone container
                if not phone_found:
                    try:
                        # Look for updated phone containers
                        containers = driver.find_elements(By.CSS_SELECTOR, "[data-testid*='phone'], [class*='phone']")
                        for container in containers:
                            text = container.text.strip()
                            if text and 'xxx' not in text.lower() and len(text) > 5:
                                print(f"\n🎉 SUCCESS! Phone from container: {text}")
                                phone_found = True
                                break
                    except:
                        pass
                
                if not phone_found:
                    print("\n⚠️ Phone number not revealed")
                    print("Possible reasons:")
                    print("- Login required")
                    print("- Additional verification needed")
                    print("- Rate limiting")
                    
                    # Check for login messages
                    try:
                        login_text = driver.find_element(By.XPATH, "//*[contains(text(), 'Увійдіть')]")
                        print(f"🔐 Login message found: {login_text.text[:50]}...")
                    except:
                        pass
                
            else:
                print("❌ Failed to click phone button")
        else:
            print("❌ Button not clickable (hidden or disabled)")
    else:
        print("❌ Phone button not found on page")
    
    # Take final screenshot
    driver.save_screenshot("olx_final.png")
    print(f"\n📸 Final screenshot: olx_final.png")
    
    print(f"\n✅ Script completed!")
    print(f"🎯 AdsPower + Selenium + ChromeDriver v134 = WORKING! 🎉")
    
except KeyboardInterrupt:
    print("\n⏸️ Script interrupted by user")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    try:
        driver.quit()
        print("🔄 Browser closed")
    except:
        pass
    
    try:
        requests.get(stop_url)
        print("🛑 AdsPower profile stopped")
    except:
        pass
    
    print("✅ Cleanup completed") 