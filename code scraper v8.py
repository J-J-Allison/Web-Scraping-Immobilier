"""
SeLoger Scraper - ULTIMATE COMBINED VERSION
Combines: Original tab-based parallel architecture + Lazy loading fix + Redundancy

Priority: Original code structure and features
Additions: Lazy loading support with HUMAN-LIKE SCROLLING + validation + retry logic

Key anti-bot features:
- Human-like smooth scrolling with variable speed
- Random hesitations and micro-pauses
- Occasional scroll-back behavior (reviewing content)
- Easing functions for natural acceleration/deceleration
"""

import time
import csv
import random
import logging
import argparse
import json
import os
import sys
import pickle
from datetime import datetime
from functools import wraps
from typing import Optional, List, Dict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
import re
from queue import Queue

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException
)

# Try to import undetected-chromedriver
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
BASE_URL = "https://www.seloger.com/classified-search?distributionTypes=Buy&estateTypes=House,Apartment&locations=eyJwbGFjZUlkIjoiQUQwOEZSMzEwOTYiLCJyYWRpdXMiOjMwLCJwb2x5bGluZSI6Im1wempIZWhsTXBfQGJ1TmhfQm5hTmp7Q2J7TGpxRW5jS2JfR3h8SHxiSGJqRmx7SGxuQ3ZnSW5tQGxnSXlyQGx6SHtyQ25hSGFtRmp9Rn19SHBvRWtiS3x5Q2N4TGp-QWF9TWRfQHtvTmVfQHlvTmt-QWF9TX15Q2N4THFvRW1iS2t9Rnt9SG9hSGFtRm16SH1yQ21nSXlyQHdnSXBtQG17SGxuQ31iSGBqRmNfR3p8SGtxRWxjS2t7Q2J7TGlfQm5hTnFfQGJ1TiIsImNvb3JkaW5hdGVzIjp7ImxhdCI6NDguODU5Njk0NDg0NjY4NTE2LCJsbmciOjIuMzYxNzg2NTQ3MDMwNTU5fX0"

OUTPUT_DIR = "output"
MAX_RETRIES = 3
HEADLESS = False
PARALLEL_WORKERS = 3  # Number of simultaneous tabs
DEBUG_MODE = False  # Set to True to save HTML of cards with missing data

# More human-like delays (from original)
DELAY_BETWEEN_LISTINGS = (0.5, 1.5)  # Slower, more variable
PAGE_LOAD_WAIT = (3, 6)  # Longer initial wait
SCROLL_DELAY = (0.5, 1.2)  # More realistic scrolling
TAB_SWITCH_DELAY = (0.3, 0.8)  # Delay when switching tabs

# NEW: Lazy loading specific delays
LAZY_SCROLL_WAIT = (1.5, 2.5)  # Wait after each scroll for lazy loading
FINAL_WAIT_AFTER_SCROLL = (2, 3)  # Wait after all scrolling

# NEW: Quality thresholds for validation
MIN_LISTINGS_PER_PAGE = 20  # Expect at least this many listings per page
MIN_COMPLETE_DATA_RATIO = 0.6  # At least 60% should have complete data

# NEW: Retry delays
RETRY_DELAY = (8, 12)

# Thread-safe CSV writing and driver access
csv_lock = Lock()
driver_lock = Lock()

# NEW: Thread-safe retry queue management
retry_queue_lock = Lock()
failed_pages_lock = Lock()

# NEW: Track failed pages and retries
retry_queue = Queue()
failed_pages = set()
page_results = {}  # page_num -> (listing_count, complete_count, success)

# User agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Tab-%(thread)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('seloger_scraper_ultimate.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Fix Windows console encoding
if sys.platform.startswith('win'):
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def safe_get(element, selector: str, attribute: Optional[str] = None, fallback_selectors: Optional[List[str]] = None) -> Optional[str]:
    """
    Safely extract text or attribute from element
    Tries multiple selectors if the first one fails
    """
    selectors_to_try = [selector]
    if fallback_selectors:
        selectors_to_try.extend(fallback_selectors)
    
    for sel in selectors_to_try:
        try:
            elem = element.find_element(By.CSS_SELECTOR, sel)
            if attribute:
                result = elem.get_attribute(attribute)
                if result:  # Only return if we got a value
                    return result
            else:
                result = elem.text.strip()
                if result:  # Only return if we got a value
                    return result
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    
    return None

def parse_address(address: Optional[str]) -> tuple:
    """Parse address into city and postal code"""
    if not address:
        return None, None
    
    # Try to extract postal code from parentheses: "City (75000)"
    postal_match = re.search(r'\((\d{5})\)', address)
    if postal_match:
        postal_code = postal_match.group(1)
        city = address.split('(')[0].strip()
        if city.endswith(','):
            city = city[:-1].strip()
        return city, postal_code
    
    # Fallback
    parts = address.strip().split()
    for i, part in enumerate(parts):
        if part.isdigit() and len(part) == 5:
            postal_code = part
            city = " ".join(parts[:i] + parts[i+1:])
            return city.strip(), postal_code
    
    return address, None

def validate_listing(data: Dict) -> bool:
    """
    NEW: Check if listing has minimum required data
    Returns True if listing is considered "complete"
    """
    has_url = bool(data.get('url'))
    has_price = bool(data.get('price'))
    has_type = bool(data.get('type'))
    return has_url and (has_price or has_type)

def parse_listing(card) -> Dict[str, Optional[str]]:
    """Extract all information from a listing card with multiple fallback selectors"""
    data = {
        'type': None,
        'price': None,
        'price_per_m2': None,
        'surface': None,
        'rooms': None,
        'bedrooms': None,          # Number of bedrooms
        'delivery_date': None,     # For new construction
        'address': None,
        'city': None,
        'postal_code': None,
        'department': None,
        'program_name': None,      # For new construction programs
        'url': None
    }
    
    try:
        # NEW: Get all text first (in case element becomes stale)
        try:
            all_text = card.text
        except StaleElementReferenceException:
            return data
        
        # Type - try multiple selectors
        data['type'] = safe_get(card, "div.css-1n0wsen", fallback_selectors=[
            "div[class*='property-type']",
            "span[class*='type']",
            "div[data-testid*='type']"
        ])
        
        # Price - try multiple approaches
        price_elem = safe_get(card, "div[data-testid='cardmfe-price-testid']", fallback_selectors=[
            "div[class*='price']",
            "span[class*='price']",
            "div[data-testid*='price']"
        ])
        
        if price_elem:
            # Clean up price text
            price_text = price_elem.replace('\xa0', ' ').replace('\u202f', ' ').replace('\u00a0', ' ')
            
            # Try to extract just the main price
            if '€' in price_text:
                # Remove price per m² part if present
                price_parts = re.split(r'\(.*?\)', price_text)
                main_price = price_parts[0].strip()
                
                # Clean and format
                if '€' in main_price:
                    data['price'] = main_price
        
        # Fallback: try to find price in the entire card text
        if not data['price'] and all_text:
            # Look for pattern like "XXX XXX €" or "XXX,XXX €"
            price_match = re.search(r'([\d\s,]+)\s*€', all_text)
            if price_match:
                potential_price = price_match.group(1).strip()
                # Make sure it's a reasonable price (more than 10,000)
                price_num = int(re.sub(r'[^\d]', '', potential_price))
                if price_num > 10000:
                    data['price'] = potential_price + ' €'
        
        # Price per m² - multiple selectors
        try:
            price_per_m2_elem = card.find_element(By.CSS_SELECTOR, "span.css-xsih6f")
            data['price_per_m2'] = price_per_m2_elem.text.strip().replace('\xa0', ' ').replace('\u202f', ' ')
        except (NoSuchElementException, StaleElementReferenceException):
            # Fallback: look for pattern in text
            if all_text:
                ppm2_match = re.search(r'(\d[\d\s,]*\s*€/m²)', all_text)
                if ppm2_match:
                    data['price_per_m2'] = ppm2_match.group(1)
        
        # Key facts - try multiple approaches
        try:
            # Primary method
            keyfacts = card.find_element(By.CSS_SELECTOR, "div[data-testid='cardmfe-keyfacts-testid']")
            facts_elements = keyfacts.find_elements(By.CSS_SELECTOR, "div.css-9u48bm")
            
            for elem in facts_elements:
                try:
                    txt = elem.text.strip()
                    if txt and txt != '·':
                        txt_lower = txt.lower()
                        # Rooms (pièces)
                        if 'pièce' in txt_lower or 'piece' in txt_lower or 'pièces' in txt_lower:
                            data['rooms'] = txt
                        # Bedrooms (chambres)
                        elif 'chambre' in txt_lower or 'chambres' in txt_lower:
                            data['bedrooms'] = txt
                        # Surface
                        elif 'm²' in txt_lower or 'm2' in txt_lower or 'm²' in txt:
                            data['surface'] = txt
                        # Delivery date (for new construction)
                        elif 'dès' in txt_lower or '/' in txt:  # "dès le 31/12/2027"
                            data['delivery_date'] = txt
                except StaleElementReferenceException:
                    continue
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        
        # Fallback: parse from all card text
        if all_text:
            # Look for rooms: "X pièce(s)" or "X pcs"
            if not data['rooms']:
                rooms_match = re.search(r'(\d+)\s*(?:pièces?|pcs?)', all_text, re.IGNORECASE)
                if rooms_match:
                    data['rooms'] = f"{rooms_match.group(1)} pièce(s)"
            
            # Look for bedrooms: "X chambre(s)"
            if not data['bedrooms']:
                bedrooms_match = re.search(r'(\d+)\s*chambres?', all_text, re.IGNORECASE)
                if bedrooms_match:
                    data['bedrooms'] = f"{bedrooms_match.group(1)} chambre(s)"
            
            # Look for surface: "XX m²" or "XXX m2"
            if not data['surface']:
                surface_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*m[²2]', all_text, re.IGNORECASE)
                if surface_match:
                    data['surface'] = f"{surface_match.group(1)} m²"
            
            # Look for delivery date: "dès le XX/XX/XXXX"
            if not data['delivery_date']:
                delivery_match = re.search(r'dès\s+le\s+(\d{2}/\d{2}/\d{4})', all_text, re.IGNORECASE)
                if delivery_match:
                    data['delivery_date'] = f"dès le {delivery_match.group(1)}"
        
        # Address - multiple selectors
        address_raw = safe_get(card, "div[data-testid='cardmfe-description-box-address']", fallback_selectors=[
            "div[class*='address']",
            "span[class*='location']",
            "div[data-testid*='address']",
            "div[class*='location']"
        ])
        
        if address_raw:
            data['address'] = address_raw
            
            # Parse address - format can be:
            # "Street, City (PostalCode)" for regular properties
            # "Program Name, City (PostalCode)" for new construction
            
            # Extract postal code first
            postal_match = re.search(r'\((\d{5})\)', address_raw)
            if postal_match:
                data['postal_code'] = postal_match.group(1)
                data['department'] = postal_match.group(1)[:2]
            
            # Extract city (before postal code)
            city_match = re.search(r',\s*([^,]+?)\s*\(', address_raw)
            if city_match:
                data['city'] = city_match.group(1).strip()
            
            # Extract program name (before city, for new construction)
            # Format: "Program Name, City (Postal)"
            if ',' in address_raw:
                parts = address_raw.split(',')
                if len(parts) >= 2:
                    # First part might be program name or street
                    potential_program = parts[0].strip()
                    # Program names typically don't have numbers at start
                    if not re.match(r'^\d', potential_program):
                        data['program_name'] = potential_program
        else:
            # Try to find address in card text with regex
            if all_text:
                # Look for postal code pattern
                postal_match = re.search(r'(\d{5})', all_text)
                if postal_match:
                    data['postal_code'] = postal_match.group(1)
                    data['department'] = postal_match.group(1)[:2]
        
        # URL - multiple selectors
        url = safe_get(card, "a[data-testid='card-mfe-covering-link-testid']", attribute="href", fallback_selectors=[
            "a[href*='seloger']",
            "a[href*='/annonces/']",
            "a[class*='card']"
        ])
        
        if url and not url.startswith("http"):
            url = f"https://www.seloger.com{url}"
        data['url'] = url
        
    except Exception as e:
        logger.error(f"Error parsing listing: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    return data

def setup_chrome_driver(headless: bool = HEADLESS) -> webdriver:
    """Setup Chrome driver with human-like settings"""
    user_agent = random.choice(USER_AGENTS)
    
    if UNDETECTED_AVAILABLE:
        # undetected-chromedriver handles most anti-detection automatically
        # Don't add extra experimental options - it conflicts with uc's own setup
        options = uc.ChromeOptions()
        options.add_argument(f"--user-agent={user_agent}")
        if headless:
            options.add_argument("--headless=new")
        driver = uc.Chrome(options=options)
    else:
        # Regular Selenium - add all anti-detection measures
        options = ChromeOptions()
        options.add_argument(f"--user-agent={user_agent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        # Additional anti-detection measures
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        if headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        
        # Execute script to remove webdriver property (only for regular Selenium)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

@contextmanager
def csv_writer_context(filename: str):
    """Context manager for CSV writing"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    f = open(filepath, "a", newline="", encoding="utf-8-sig")  # Changed to utf-8-sig for Excel compatibility
    try:
        yield csv.writer(f)
    finally:
        f.close()

def initialize_csv(filename: str):
    """Create CSV file with headers"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Type",
            "Price",
            "Price_Per_M2",
            "Surface_m2",
            "Rooms",
            "Bedrooms",
            "Delivery_Date",
            "Address",
            "City",
            "PostalCode",
            "Department",
            "Program_Name",
            "URL"
        ])
    logger.info(f"Initialized CSV file: {filepath}")

# ---------------------------------------------------------
# Cookie Handler
# ---------------------------------------------------------
def wait_for_manual_cookie_acceptance(driver, timeout=60):
    """
    Wait for user to manually accept cookies
    Checks every 2 seconds if the cookie popup is gone
    """
    logger.info("=" * 70)
    logger.info("⏸️  PLEASE ACCEPT COOKIES MANUALLY IN THE BROWSER WINDOW")
    logger.info("=" * 70)
    logger.info("Waiting for you to click 'Tout accepter' or dismiss the cookie popup...")
    logger.info(f"Timeout: {timeout} seconds")
    logger.info("=" * 70)
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Check if the cookie popup is still present
            # Look for usercentrics-root or similar cookie consent elements
            popup_present = False
            
            # Try to find the popup in various ways
            try:
                # Check for shadow root
                shadow_script = """
                    const root = document.querySelector('#usercentrics-root');
                    if (!root || !root.shadowRoot) return false;
                    const button = root.shadowRoot.querySelector('[data-testid="uc-accept-all-button"]');
                    return button !== null && button.offsetParent !== null;
                """
                popup_present = driver.execute_script(shadow_script)
            except:
                pass
            
            # If no popup found, cookies were accepted!
            if not popup_present:
                logger.info("✅ Cookie popup dismissed! Continuing with scraping...")
                return True
            
            time.sleep(2)
            
        except Exception as e:
            logger.debug(f"Error checking for cookie popup: {e}")
            # If we can't find the popup, assume it's gone
            return True
    
    logger.warning(f"⏰ Timeout after {timeout} seconds. Continuing anyway...")
    return False

# ---------------------------------------------------------
# NEW: Lazy Loading Support
# ---------------------------------------------------------
def scroll_to_load_all_cards(driver, page_num: int) -> int:
    """
    CRITICAL NEW FEATURE: Scroll page to trigger lazy loading of all cards
    The site loads cards dynamically as you scroll down
    Uses HUMAN-LIKE SCROLLING to evade bot detection
    Returns the number of cards found
    """
    logger.info(f"Tab {page_num}: Scrolling to load all cards (lazy loading with human-like behavior)...")
    
    # Scroll in steps to trigger lazy loading
    scroll_steps = 5
    last_card_count = 0
    stable_count = 0
    
    for step in range(scroll_steps):
        # Calculate target scroll position
        scroll_position = (step + 1) * (1.0 / scroll_steps)
        target_y = int(driver.execute_script("return document.body.scrollHeight") * scroll_position)
        current_y = driver.execute_script("return window.pageYOffset")
        
        # HUMAN-LIKE SCROLLING: Smooth scroll with random speed variations
        # Instead of instant jump, scroll in smaller increments
        distance = target_y - current_y
        num_increments = random.randint(8, 15)  # Random number of scroll increments
        
        for i in range(num_increments):
            # Calculate next position with slight randomness
            progress = (i + 1) / num_increments
            # Use easing function for more natural deceleration
            eased_progress = 1 - pow(1 - progress, 3)  # Ease-out cubic
            next_y = int(current_y + (distance * eased_progress))
            
            # Add small random variation to simulate human imprecision
            variation = random.randint(-10, 10)
            next_y += variation
            
            # Smooth scroll to next position
            driver.execute_script(f"window.scrollTo({{top: {next_y}, behavior: 'smooth'}});")
            
            # Variable micro-pauses between increments (human doesn't scroll at constant speed)
            micro_pause = random.uniform(0.05, 0.15)
            time.sleep(micro_pause)
        
        # Occasional "hesitation" - humans sometimes pause mid-scroll
        if random.random() < 0.3:  # 30% chance
            hesitation = random.uniform(0.3, 0.8)
            logger.debug(f"Tab {page_num}: Human-like hesitation ({hesitation:.1f}s)")
            time.sleep(hesitation)
        
        # Wait for new cards to load
        wait_time = random.uniform(*LAZY_SCROLL_WAIT)
        logger.debug(f"Tab {page_num}: Scroll step {step+1}/{scroll_steps}, waiting {wait_time:.1f}s...")
        time.sleep(wait_time)
        
        # Occasionally scroll up slightly (humans do this when reviewing content)
        if random.random() < 0.25:  # 25% chance
            scroll_back = random.randint(50, 150)
            current = driver.execute_script("return window.pageYOffset")
            driver.execute_script(f"window.scrollTo({{top: {current - scroll_back}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.2, 0.5))
            # Then scroll back down
            driver.execute_script(f"window.scrollTo({{top: {current}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.3, 0.6))
        
        # Check card count
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='serp-core-classified-card-testid']")
            current_count = len(cards)
            logger.debug(f"Tab {page_num}: Found {current_count} cards after scroll step {step+1}")
            
            # Check if count is stable
            if current_count == last_card_count:
                stable_count += 1
                if stable_count >= 2:  # If stable for 2 steps, we're done
                    logger.info(f"Tab {page_num}: Card count stable at {current_count}")
                    break
            else:
                stable_count = 0
            
            last_card_count = current_count
        except Exception as e:
            logger.debug(f"Tab {page_num}: Error checking cards during scroll: {e}")
    
    # Scroll back to top with human-like behavior
    logger.debug(f"Tab {page_num}: Scrolling back to top...")
    current_y = driver.execute_script("return window.pageYOffset")
    num_increments = random.randint(10, 18)
    
    for i in range(num_increments):
        progress = (i + 1) / num_increments
        eased_progress = 1 - pow(1 - progress, 2)  # Ease-out quadratic
        next_y = int(current_y * (1 - eased_progress))
        
        driver.execute_script(f"window.scrollTo({{top: {next_y}, behavior: 'smooth'}});")
        time.sleep(random.uniform(0.04, 0.12))
    
    # Final scroll to exact top
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    time.sleep(random.uniform(*FINAL_WAIT_AFTER_SCROLL))
    
    # Final count
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='serp-core-classified-card-testid']")
        final_count = len(cards)
        logger.info(f"Tab {page_num}: ✓ Loaded {final_count} cards total")
        return final_count
    except:
        return 0

# ---------------------------------------------------------
# Tab-Based Page Scraper
# ---------------------------------------------------------
def randomize_viewport(driver, tab_handle):
    """
    Randomly resize the viewport to make each tab appear different
    Simulates different screen sizes / window states
    """
    with driver_lock:
        driver.switch_to.window(tab_handle)
        
        # Common viewport sizes (width, height)
        viewports = [
            (1920, 1080),  # Full HD
            (1366, 768),   # Common laptop
            (1536, 864),   # HD+
            (1440, 900),   # MacBook
            (1600, 900),   # HD+
            (1280, 720),   # HD
        ]
        
        width, height = random.choice(viewports)
        driver.set_window_size(width, height)
        logger.debug(f"Tab viewport set to {width}x{height}")

def delayed_scrape_wrapper(driver, page_num: int, tab_handle: str, output_file: str, delay: float) -> tuple:
    """
    Wrapper that adds a staggered delay before scraping
    This prevents all tabs from hitting the server at exactly the same time
    NEW: Returns tuple (listing_count, complete_count, success) for validation
    """
    if delay > 0:
        logger.info(f"Tab {page_num}: Waiting {delay:.1f}s before starting (staggered start)...")
        time.sleep(delay)
    
    listing_count, complete_count, success = scrape_page_in_tab(driver, page_num, tab_handle, output_file)
    
    # NEW: Store results and queue for retry if needed
    with retry_queue_lock:
        page_results[page_num] = (listing_count, complete_count, success)
    
    if not success:
        with retry_queue_lock:
            logger.warning(f"Page {page_num}: FAILED validation - adding to retry queue")
            retry_queue.put((page_num, 1))
    
    return listing_count, complete_count, success

def scrape_page_in_tab(driver, page_num: int, tab_handle: str, output_file: str, retry_count: int = 0) -> tuple:
    """
    Scrape a single page in a specific browser tab
    UPDATED: Now with lazy loading support and validation
    
    Args:
        driver: Shared webdriver instance
        page_num: Page number to scrape
        tab_handle: Window handle for this tab
        output_file: CSV filename to write to
        retry_count: Current retry attempt
    
    Returns:
        tuple: (listing_count, complete_count, success)
    """
    try:
        # Thread-safe driver operations
        with driver_lock:
            # Small delay before switching tabs (simulate human thinking/clicking)
            time.sleep(random.uniform(*TAB_SWITCH_DELAY))
            
            # Switch to this tab
            driver.switch_to.window(tab_handle)
            
            # Build URL with page number
            url = f"{BASE_URL}&page={page_num}"
            logger.info(f"Tab {page_num}: Loading URL (attempt {retry_count + 1})")
            
            # Load page
            driver.get(url)
        
        # Wait outside the lock
        time.sleep(random.uniform(*PAGE_LOAD_WAIT))
        
        # NEW: CRITICAL - Scroll to load all cards (lazy loading)
        with driver_lock:
            card_count = scroll_to_load_all_cards(driver, page_num)
        
        if card_count == 0:
            logger.error(f"Tab {page_num}: NO CARDS found after lazy loading!")
            
            # Save diagnostic info
            if DEBUG_MODE:
                debug_dir = os.path.join(OUTPUT_DIR, "failed_pages")
                os.makedirs(debug_dir, exist_ok=True)
                
                with driver_lock:
                    html_file = os.path.join(debug_dir, f"page{page_num}_attempt{retry_count+1}.html")
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    logger.warning(f"Saved HTML to: {html_file}")
                    
                    screenshot_file = os.path.join(debug_dir, f"page{page_num}_attempt{retry_count+1}.png")
                    try:
                        driver.save_screenshot(screenshot_file)
                        logger.warning(f"Saved screenshot to: {screenshot_file}")
                    except:
                        pass
            
            return 0, 0, False
        
        # Get listing cards (outside lock since we already scrolled)
        with driver_lock:
            cards = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='serp-core-classified-card-testid']")
        
        logger.info(f"Tab {page_num}: Found {len(cards)} card containers")
        
        if not cards:
            logger.warning(f"Tab {page_num}: No listing cards found!")
            return 0, 0, False
        
        # Parse listings (can be done outside lock since we have the elements)
        listings = []
        complete_count = 0
        
        for i, card in enumerate(cards, 1):
            time.sleep(random.uniform(*DELAY_BETWEEN_LISTINGS)) 
            
            # Parse (without lock - we have the element)
            data = parse_listing(card)
            
            # NEW: Validate listing
            is_complete = validate_listing(data)
            if is_complete:
                complete_count += 1
            
            # Detailed logging for missing data
            missing_fields = []
            if not data['url']:
                missing_fields.append('URL')
            if not data['price']:
                missing_fields.append('price')
            if not data['type']:
                missing_fields.append('type')
            if not data['surface']:
                missing_fields.append('surface')
            if not data['rooms']:
                missing_fields.append('rooms')
            if not data['address']:
                missing_fields.append('address')
            
            if missing_fields:
                logger.warning(f"Tab {page_num}, Card {i}: Missing fields: {', '.join(missing_fields)}")
                
                # Save HTML for debugging if debug mode is on
                if DEBUG_MODE:
                    try:
                        debug_dir = os.path.join(OUTPUT_DIR, "debug_html")
                        os.makedirs(debug_dir, exist_ok=True)
                        
                        with driver_lock:
                            card_html = card.get_attribute('outerHTML')
                        debug_file = os.path.join(debug_dir, f"page{page_num}_card{i}.html")
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(card_html)
                        logger.debug(f"Saved HTML to {debug_file}")
                    except Exception as e:
                        logger.debug(f"Could not save debug HTML: {e}")
                else:
                    # Just log a preview
                    try:
                        with driver_lock:
                            card_html = card.get_attribute('outerHTML')[:500]
                        logger.debug(f"Card HTML preview: {card_html}")
                    except:
                        pass
            
            listings.append(data)
        
        logger.info(f"Tab {page_num}: Parsed {len(listings)} listings")
        
        # Count how many have actual data
        logger.info(f"Tab {page_num}: {complete_count}/{len(listings)} listings have complete data")
        
        # NEW: Validate results
        success = True
        if len(listings) < MIN_LISTINGS_PER_PAGE:
            logger.warning(f"Tab {page_num}: Only {len(listings)} listings (expected {MIN_LISTINGS_PER_PAGE}+)")
            success = False
        
        if complete_count < len(listings) * MIN_COMPLETE_DATA_RATIO:
            ratio = complete_count/len(listings)*100 if listings else 0
            logger.warning(f"Tab {page_num}: Only {complete_count}/{len(listings)} complete ({ratio:.1f}%)")
            success = False
        
        # Save to CSV (thread-safe)
        with csv_lock:
            with csv_writer_context(output_file) as writer:
                for listing in listings:
                    writer.writerow([
                        listing['type'],
                        listing['price'],
                        listing['price_per_m2'],
                        listing['surface'],
                        listing['rooms'],
                        listing['bedrooms'],
                        listing['delivery_date'],
                        listing['address'],
                        listing['city'],
                        listing['postal_code'],
                        listing['department'],
                        listing['program_name'],
                        listing['url']
                    ])
        
        logger.info(f"Tab {page_num}: Saved {len(listings)} listings to CSV")
        return len(listings), complete_count, success
        
    except TimeoutException as e:
        logger.error(f"Tab {page_num}: Timeout waiting for listings - {e}")
        if retry_count < MAX_RETRIES - 1:
            logger.info(f"Tab {page_num}: Retrying...")
            time.sleep(5)
            return scrape_page_in_tab(driver, page_num, tab_handle, output_file, retry_count + 1)
        return 0, 0, False
    except Exception as e:
        logger.error(f"Tab {page_num}: Error - {e}")
        import traceback
        logger.error(f"Tab {page_num}: Traceback - {traceback.format_exc()}")
        
        if retry_count < MAX_RETRIES - 1:
            logger.info(f"Tab {page_num}: Retrying...")
            time.sleep(5)
            return scrape_page_in_tab(driver, page_num, tab_handle, output_file, retry_count + 1)
        return 0, 0, False

# ---------------------------------------------------------
# Main Tab-Based Scraper (WITH REDUNDANCY)
# ---------------------------------------------------------
def scrape_with_tabs(start_page: int, end_page: int, output_file: str, workers: int = PARALLEL_WORKERS):
    """
    Scrape multiple pages using tabs in a single browser window
    NEW: With lazy loading support, validation, and retry logic
    
    This maintains cookie consent across all scraping operations!
    """
    logger.info("=" * 70)
    logger.info("SeLoger TAB-BASED PARALLEL Scraper - ULTIMATE VERSION")
    logger.info("=" * 70)
    logger.info(f"Pages: {start_page} to {end_page}")
    logger.info(f"Parallel tabs: {workers}")
    logger.info(f"Output: {output_file}")
    logger.info(f"Features: Lazy loading + Validation + Retry")
    logger.info("=" * 70)
    
    # Initialize CSV
    initialize_csv(output_file)
    
    # Setup single Chrome driver
    driver = setup_chrome_driver()
    
    try:
        # Load initial page and wait for manual cookie acceptance
        logger.info("Loading initial page for cookie consent...")
        driver.get(BASE_URL)
        time.sleep(3)
        
        # Wait for user to manually accept cookies
        wait_for_manual_cookie_acceptance(driver, timeout=120)
        
        # Create additional tabs using switch_to.new_window (more reliable)
        logger.info(f"Creating {workers - 1} additional tabs...")
        tab_handles = [driver.current_window_handle]
        
        for i in range(workers - 1):
            # Human-like delay between opening tabs (2-5 seconds)
            delay = random.uniform(2, 5)
            logger.info(f"Opening tab {i+2}/{workers} (waiting {delay:.1f}s)...")
            time.sleep(delay)
            
            try:
                # Method 1: Try switch_to.new_window (Selenium 4)
                driver.switch_to.new_window('tab')
                time.sleep(1)
                tab_handles.append(driver.current_window_handle)
                logger.info(f"Successfully created tab {i+2} using new_window()")
            except Exception as e:
                logger.warning(f"new_window() failed: {e}. Trying alternative method...")
                # Method 2: Try window.open with about:blank
                try:
                    driver.execute_script("window.open('about:blank', '_blank');")
                    time.sleep(2)
                    # Switch to the new tab
                    new_handles = [h for h in driver.window_handles if h not in tab_handles]
                    if new_handles:
                        tab_handles.append(new_handles[0])
                        logger.info(f"Successfully created tab {i+2} using window.open()")
                    else:
                        logger.error(f"Failed to create tab {i+2} - no new window handle found")
                except Exception as e2:
                    logger.error(f"Both methods failed for tab {i+2}: {e2}")
                    break
        
        # Wait a moment for all tabs to be fully registered
        time.sleep(2)
        
        # Get all tab handles (final verification)
        final_handles = driver.window_handles
        logger.info(f"Final tab count: {len(final_handles)} tabs")
        
        # Use only the tabs we successfully created
        if len(tab_handles) < workers:
            logger.warning(f"Could only create {len(tab_handles)} tabs instead of {workers}")
            logger.warning(f"Will continue with {len(tab_handles)} parallel workers")
            workers = len(tab_handles)
        
        # Randomize viewport for each tab
        logger.info("Randomizing viewport sizes for each tab...")
        for tab_handle in tab_handles:
            try:
                randomize_viewport(driver, tab_handle)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not randomize viewport for tab: {e}")
        
        # Add a small delay before starting to scrape
        logger.info("Tabs ready. Pausing briefly before starting scrape...")
        time.sleep(random.uniform(2, 4))
        
        # Create list of pages to scrape
        pages = list(range(start_page, end_page + 1))
        total_listings = 0
        
        start_time = time.time()
        
        # NEW: PHASE 1 - Initial scrape
        logger.info("\n" + "=" * 70)
        logger.info("PHASE 1: Initial scrape with lazy loading")
        logger.info("=" * 70)
        
        # Scrape in parallel using tabs
        # We'll use a thread pool, but each thread will use a specific tab
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            
            # Assign pages to tabs in a round-robin fashion
            # Add staggered start times to avoid all tabs hitting at once
            for idx, page in enumerate(pages):
                tab_idx = idx % len(tab_handles)
                tab_handle = tab_handles[tab_idx]
                
                # Stagger the start of each page request
                stagger_delay = idx * random.uniform(0.5, 1.5)
                
                # Add random "breaks" every 10-15 pages
                if idx > 0 and idx % random.randint(10, 15) == 0:
                    break_time = random.uniform(10, 20)
                    logger.info(f"📊 Taking a {break_time:.1f}s break after {idx} pages (simulating human behavior)...")
                    time.sleep(break_time)
                
                future = executor.submit(
                    delayed_scrape_wrapper,
                    driver, 
                    page, 
                    tab_handle, 
                    output_file,
                    stagger_delay
                )
                futures.append((future, page))
            
            # Process completed tasks
            for future, page in futures:
                try:
                    count, complete, success = future.result()
                    total_listings += count
                    status = "✓" if success else "⚠"
                    logger.info(f"{status} Page {page} complete ({count} listings, {complete} complete)")
                except Exception as e:
                    logger.error(f"✗ Page {page} failed: {e}")
                    with retry_queue_lock:
                        retry_queue.put((page, 1))
        
        # NEW: PHASE 2 - Retry failed pages
        if not retry_queue.empty():
            logger.info("\n" + "=" * 70)
            logger.info("PHASE 2: Retrying failed pages")
            logger.info("=" * 70)
            
            retry_attempts = 0
            max_retry_rounds = 2
            
            while not retry_queue.empty() and retry_attempts < max_retry_rounds:
                retry_attempts += 1
                logger.info(f"\n--- Retry Round {retry_attempts} ---")
                
                # Get all pages to retry
                pages_to_retry = []
                while not retry_queue.empty():
                    try:
                        page_num, attempt = retry_queue.get_nowait()
                        if attempt <= MAX_RETRIES:
                            pages_to_retry.append((page_num, attempt))
                    except:
                        break
                
                if not pages_to_retry:
                    break
                
                logger.info(f"Retrying {len(pages_to_retry)} pages...")
                
                # Wait before retrying
                retry_delay = random.uniform(*RETRY_DELAY)
                logger.info(f"Waiting {retry_delay:.1f}s before retry...")
                time.sleep(retry_delay)
                
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = []
                    
                    for idx, (page_num, attempt) in enumerate(pages_to_retry):
                        tab_idx = idx % len(tab_handles)
                        tab_handle = tab_handles[tab_idx]
                        
                        future = executor.submit(
                            scrape_page_in_tab,
                            driver, page_num, tab_handle, output_file, attempt
                        )
                        futures.append((future, page_num, attempt))
                    
                    for future, page_num, attempt in futures:
                        try:
                            count, complete, success = future.result()
                            if success:
                                logger.info(f"✓ Page {page_num} RETRY SUCCESS: {count} listings")
                                total_listings += count
                            else:
                                logger.warning(f"⚠ Page {page_num} retry failed again")
                                if attempt < MAX_RETRIES:
                                    retry_queue.put((page_num, attempt + 1))
                                else:
                                    logger.error(f"✗ Page {page_num} ABANDONED after {MAX_RETRIES} attempts")
                                    with failed_pages_lock:
                                        failed_pages.add(page_num)
                        except Exception as e:
                            logger.error(f"✗ Page {page_num} retry error: {e}")
                            if attempt < MAX_RETRIES:
                                retry_queue.put((page_num, attempt + 1))
        
        elapsed = time.time() - start_time
        
        logger.info("=" * 70)
        logger.info(f"Scraping complete!")
        logger.info(f"Total listings: {total_listings}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Average: {elapsed/(end_page-start_page+1):.1f}s per page")
        logger.info(f"Pages scraped: {len(pages)}")
        
        if failed_pages:
            logger.warning(f"Failed pages: {sorted(failed_pages)}")
        else:
            logger.info("✓ All pages scraped successfully!")
        
        logger.info(f"Results: {OUTPUT_DIR}/{output_file}")
        logger.info("=" * 70)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        # Clean up
        logger.info("Closing browser...")
        try:
            driver.quit()
        except:
            pass

# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="SeLoger Tab-Based Parallel Scraper - ULTIMATE VERSION (Lazy Loading + Redundancy)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape pages 1-20 with 3 tabs
  python seloger_scraper_ultimate.py --start 1 --end 20 --workers 3
  
  # Scrape pages 50-100 with 10 tabs (maximum)
  python seloger_scraper_ultimate.py --start 50 --end 100 --workers 10
  
  # Interactive mode
  python seloger_scraper_ultimate.py

NEW FEATURES:
  ✨ Lazy loading support - scrolls to load all cards
  ✨ Data validation - checks completeness
  ✨ Automatic retry - failed pages are retried
  ✨ Debug mode - saves HTML of problematic cards
  ✨ Human-like scrolling - evades bot detection
  ✨ Up to 10 parallel tabs - faster scraping
      
NOTE: You will need to manually accept cookies in the browser window
      when it first opens. After that, all tabs will maintain the consent!
        """
    )
    
    parser.add_argument("--start", type=int, help="Start page number")
    parser.add_argument("--end", type=int, help="End page number")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel tabs (default: 3, max: 10)")
    parser.add_argument("--output", type=str, help="Output CSV filename")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (not recommended for cookie consent)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (saves HTML of problematic cards)")
    
    args = parser.parse_args()
    
    global HEADLESS, DEBUG_MODE
    HEADLESS = args.headless
    DEBUG_MODE = args.debug
    
    if DEBUG_MODE:
        logger.info("🐛 Debug mode enabled - will save HTML of cards with missing data")
        logging.getLogger().setLevel(logging.DEBUG)
    
    if HEADLESS:
        logger.warning("⚠️  Headless mode enabled - you won't be able to manually accept cookies!")
        logger.warning("    This may cause the scraper to fail. Consider running without --headless")
    
    # Interactive mode
    if not args.start or not args.end:
        print("\n" + "=" * 70)
        print("SeLoger Tab-Based Parallel Scraper - ULTIMATE VERSION")
        print("=" * 70)
        print("\n✨ NEW FEATURES:")
        print("   • Lazy loading support (scrolls to load all cards)")
        print("   • Data validation (checks completeness)")
        print("   • Automatic retry (failed pages are retried)")
        print("   • Debug mode (saves problematic pages)")
        print("\n🍪 This scraper uses tabs in a SINGLE browser window!")
        print("   You only need to accept cookies ONCE at the start.")
        print(f"   Default tabs: {PARALLEL_WORKERS} (max: 10)")
        print()
        
        try:
            start = int(input("Start page (e.g., 1): ").strip())
            end = int(input("End page (e.g., 20): ").strip())
            
            workers_input = input(f"Number of tabs (1-10, default {PARALLEL_WORKERS}): ").strip()
            workers = int(workers_input) if workers_input else PARALLEL_WORKERS
            
            if workers < 1 or workers > 10:
                print("Workers should be between 1 and 10. Using default.")
                workers = PARALLEL_WORKERS
                
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return
    else:
        start = args.start
        end = args.end
        workers = args.workers
        
        if workers > 10:
            logger.warning(f"⚠️  {workers} tabs requested. Maximum is 10. Setting to 10.")
            workers = 10
        elif workers < 1:
            logger.warning(f"⚠️  {workers} tabs requested. Minimum is 1. Setting to 1.")
            workers = 1
    
    # Generate output filename
    if args.output:
        output_file = args.output
    else:
        output_file = f"seloger_ultimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Calculate time estimate
    total_pages = end - start + 1
    est_time = (total_pages / workers) * 70  # ~70 sec per page with lazy loading
    
    print()
    print("=" * 70)
    print(f"Will scrape pages {start} to {end} ({total_pages} pages)")
    print(f"Using {workers} parallel tabs (in ONE browser window)")
    print(f"Estimated time: ~{est_time/60:.1f} minutes")
    print(f"Output: {output_file}")
    print()
    print("🍪 IMPORTANT: When the browser opens, please accept the cookies!")
    print("   This only needs to be done ONCE - all tabs will share the consent.")
    print("=" * 70)
    print()
    
    confirm = input("Start scraping? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    # Start scraping
    scrape_with_tabs(start, end, output_file, workers)

if __name__ == "__main__":
    main()