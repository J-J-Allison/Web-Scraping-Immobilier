
import time
import csv
import random
import logging
import argparse
import os
import sys
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from queue import Queue
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
    ElementClickInterceptedException
)

try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import warnings
warnings.filterwarnings('ignore', message='Connection pool is full')

if sys.platform.startswith('win'):
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
BASE_URL = "https://www.seloger.com/classified-search?distributionTypes=Buy&estateTypes=House,Apartment&locations=AD09FR43,AD09FR44,AD09FR45"

OUTPUT_DIR = "output"
MAX_RETRIES = 3
HEADLESS = False
PARALLEL_WORKERS = 3
MAX_WORKERS = 10
DEBUG_MODE = False
MISSING_DATA_INDICATOR = "N/A"

# # Delays - balanced for speed + anti-bot

DELAY_BETWEEN_LISTINGS = (0.05, 0.15)
PAGE_LOAD_WAIT = (2, 4)
SCROLL_DELAY = (0.2, 0.5)
LAZY_SCROLL_WAIT = (0.8, 1.5)
FINAL_WAIT_AFTER_SCROLL = (1.0, 1.8)
# Retry delays
RETRY_DELAY = (5, 10)
MAX_RETRY_ROUNDS = 2

# Quality thresholds
MIN_LISTINGS_PER_PAGE = 15
MIN_COMPLETE_DATA_RATIO = 0.5

# Human behavior simulation
BREAK_EVERY_N_PAGES = (8, 15)  # Take a break every 8-15 pages
BREAK_DURATION = (5, 15)  # Break for 5-15 seconds

# Thread-safe locks
csv_lock = Lock()
scraped_urls_lock = Lock()
scraped_urls: Set[str] = set()
stats_lock = Lock()
retry_queue_lock = Lock()
# Retry queue for failed pages
retry_queue: Queue = Queue()

global_stats = {
    'total_listings': 0,
    'complete_listings': 0,
    'failed_pages': set(),
    'successful_pages': set(),
    'pages_by_worker': {}
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

VIEWPORT_SIZES = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1600, 900), (1280, 720), (1680, 1050),
]

# Stable selectors
SELECTORS = {
    'card': "div[data-testid='serp-core-classified-card-testid']",
    'url': "a[data-testid='card-mfe-covering-link-testid']",
    'price_container': "div[data-testid='cardmfe-price-testid']",
    'keyfacts': "div[data-testid='cardmfe-keyfacts-testid']",
    'address': "div[data-testid='cardmfe-description-box-address']",
    'tags': "div[data-testid='cardmfe-tag-testid']",
    'energy': "span[data-testid='card-mfe-energy-performance-class']",
}

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Worker-%(thread)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('seloger_scraper_v12.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.WARNING)


# ---------------------------------------------------------
# POPUP HANDLING -
# ---------------------------------------------------------
def dismiss_all_popups(driver, worker_id: int) -> bool:
    """
    Automatically dismiss ALL popups:
    - Cookie consent (Usercentrics shadow DOM)
    - Modal dialogs
    - Newsletter popups
    - Any other overlays
    
    Returns True if any popup was dismissed.
    """
    dismissed_any = False
    
    # 1. USERCENTRICS COOKIE POPUP (Shadow DOM)
    try:
        cookie_script = """
            const root = document.querySelector('#usercentrics-root');
            if (root && root.shadowRoot) {
                const acceptBtn = root.shadowRoot.querySelector('[data-testid="uc-accept-all-button"]');
                if (acceptBtn && acceptBtn.offsetParent !== null) {
                    acceptBtn.click();
                    return true;
                }
            }
            return false;
        """
        if driver.execute_script(cookie_script):
            logger.info(f"Worker {worker_id}: ✓ Dismissed Usercentrics cookie popup")
            dismissed_any = True
            time.sleep(0.5)
    except Exception as e:
        logger.debug(f"Worker {worker_id}: Cookie popup check: {e}")
    
    # 2. GENERIC MODAL DIALOGS (role="dialog")
    try:
        dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog']")
        for dialog in dialogs:
            if dialog.is_displayed():
                # Try to find close button inside dialog
                close_selectors = [
                    "button[aria-label*='close' i]",
                    "button[aria-label*='fermer' i]",
                    "button[class*='close']",
                    "button[class*='dismiss']",
                    "[data-testid*='close']",
                    "svg[class*='close']",
                    "button:has(svg)",  # Button with icon
                ]
                
                for sel in close_selectors:
                    try:
                        close_btn = dialog.find_element(By.CSS_SELECTOR, sel)
                        if close_btn.is_displayed():
                            close_btn.click()
                            logger.info(f"Worker {worker_id}: ✓ Closed modal dialog via {sel}")
                            dismissed_any = True
                            time.sleep(0.5)
                            break
                    except:
                        continue
                
                # If no close button found, try pressing Escape
                if not dismissed_any:
                    try:
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        logger.info(f"Worker {worker_id}: ✓ Closed dialog via Escape key")
                        dismissed_any = True
                        time.sleep(0.5)
                    except:
                        pass
    except Exception as e:
        logger.debug(f"Worker {worker_id}: Dialog check: {e}")
    
    # 3. ARIA-MODAL OVERLAYS
    try:
        modals = driver.find_elements(By.CSS_SELECTOR, "[aria-modal='true']")
        for modal in modals:
            if modal.is_displayed():
                # Try clicking outside the modal
                try:
                    driver.execute_script("""
                        const overlay = document.querySelector('[aria-modal="true"]');
                        if (overlay && overlay.parentElement) {
                            overlay.parentElement.click();
                        }
                    """)
                    logger.info(f"Worker {worker_id}: ✓ Clicked outside aria-modal")
                    dismissed_any = True
                    time.sleep(0.5)
                except:
                    pass
    except Exception as e:
        logger.debug(f"Worker {worker_id}: Aria-modal check: {e}")
    
    # 4. POPIN / POPUP ELEMENTS
    try:
        popins = driver.find_elements(By.CSS_SELECTOR, "[class*='popin'], [class*='popup'], [class*='modal']")
        for popin in popins:
            if popin.is_displayed():
                # Find and click close button
                try:
                    close_btn = popin.find_element(By.CSS_SELECTOR, "button, [role='button'], [class*='close']")
                    if close_btn.is_displayed():
                        close_btn.click()
                        logger.info(f"Worker {worker_id}: ✓ Closed popin/popup")
                        dismissed_any = True
                        time.sleep(0.5)
                except:
                    pass
    except Exception as e:
        logger.debug(f"Worker {worker_id}: Popin check: {e}")
    
    # 5. OVERLAY ELEMENTS (blocking divs)
    try:
        overlays = driver.find_elements(By.CSS_SELECTOR, "[class*='overlay']")
        for overlay in overlays:
            if overlay.is_displayed():
                # Check if it's covering the page
                try:
                    rect = overlay.rect
                    if rect['width'] > 500 and rect['height'] > 500:
                        # Large overlay - try to dismiss
                        overlay.click()
                        logger.info(f"Worker {worker_id}: ✓ Clicked overlay to dismiss")
                        dismissed_any = True
                        time.sleep(0.5)
                except:
                    pass
    except Exception as e:
        logger.debug(f"Worker {worker_id}: Overlay check: {e}")
    
    # 6. PRESS ESCAPE AS FINAL FALLBACK
    if not dismissed_any:
        try:
            body = driver.find_element(By.TAG_NAME, 'body')
            body.send_keys(Keys.ESCAPE)
            time.sleep(0.3)
        except:
            pass
    
    return dismissed_any


def ensure_popups_dismissed(driver, worker_id: int, max_attempts: int = 5):
    """
    Keep trying to dismiss popups until none are found.
    """
    for attempt in range(max_attempts):
        if not dismiss_all_popups(driver, worker_id):
            # No popup was dismissed - we're clear
            break
        time.sleep(0.5)
    
    # Final check - can we see cards?
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, SELECTORS['card'])
        if cards and cards[0].is_displayed():
            logger.debug(f"Worker {worker_id}: ✓ Cards are visible")
            return True
    except:
        pass
    
    return False


def check_and_dismiss_popups_if_needed(driver, worker_id: int):
    """
    Quick check if popups exist and dismiss them.
    Called before scraping each page.
    """
    # Quick check for blocking elements
    blocking_selectors = [
        "#usercentrics-root",
        "[role='dialog']",
        "[aria-modal='true']",
    ]
    
    for selector in blocking_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
            if any(e.is_displayed() for e in elems):
                logger.debug(f"Worker {worker_id}: Found blocking element: {selector}")
                dismiss_all_popups(driver, worker_id)
                return
        except:
            pass


# ---------------------------------------------------------
# Parsing Functions
# ---------------------------------------------------------
def parse_listing(card, page_num: int, worker_id: int) -> Dict[str, Optional[str]]:
    """Extract all data from a listing card."""
    data = {
        'page_num': page_num,
        'type': None, 'price': None, 'price_per_m2': None,
        'surface': None, 'rooms': None, 'bedrooms': None,
        'floor': None, 'address': None, 'city': None,
        'postal_code': None, 'department': None,
        'url': None, 'energy_class': None, 'is_new': False,
        'agency': None, 'raw_card_text': None, 'confidence_score': 10,
    }
    
    try:
        try:
            raw_text = card.text
            data['raw_card_text'] = raw_text
        except StaleElementReferenceException:
            return data
        
        # 1. URL
        try:
            url_elem = card.find_element(By.CSS_SELECTOR, SELECTORS['url'])
            url = url_elem.get_attribute('href')
            if url:
                data['url'] = url if url.startswith('http') else f"https://www.seloger.com{url}"
                title = url_elem.get_attribute('title')
                if title:
                    type_match = re.search(r'(Appartement|Maison|Studio|Villa|Duplex|Loft|Terrain)', title, re.IGNORECASE)
                    if type_match:
                        data['type'] = type_match.group(1)
        except NoSuchElementException:
            try:
                links = card.find_elements(By.CSS_SELECTOR, "a[href*='/annonces/']")
                for link in links:
                    href = link.get_attribute('href')
                    if href and '/annonces/' in href:
                        data['url'] = href if href.startswith('http') else f"https://www.seloger.com{href}"
                        break
            except:
                pass
        
        # 2. PRICE
        try:
            price_elem = card.find_element(By.CSS_SELECTOR, SELECTORS['price_container'])
            price_text = price_elem.text
            
            price_m2_match = re.search(r'([\d\s\u00a0\u202f,\.]+\s*€\s*/\s*m[²2])', price_text)
            if price_m2_match:
                data['price_per_m2'] = price_m2_match.group(1).replace('\xa0', ' ').replace('\u202f', ' ')
            
            main_price_match = re.search(r'([\d\s\u00a0\u202f]+)\s*€(?!\s*/)', price_text)
            if main_price_match:
                price_val = main_price_match.group(1).replace('\xa0', ' ').replace('\u202f', ' ').strip()
                data['price'] = f"{price_val} €"
        except NoSuchElementException:
            pass
        
        # 3. KEY FACTS
        try:
            keyfacts = card.find_element(By.CSS_SELECTOR, SELECTORS['keyfacts'])
            facts_text = keyfacts.text
            
            surface_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*m[²2]', facts_text)
            if surface_match:
                data['surface'] = f"{surface_match.group(1)} m²"
            
            rooms_match = re.search(r'(\d+)\s*pièces?', facts_text, re.IGNORECASE)
            if rooms_match:
                data['rooms'] = f"{rooms_match.group(1)} pièce(s)"
            
            bedrooms_match = re.search(r'(\d+)\s*chambres?', facts_text, re.IGNORECASE)
            if bedrooms_match:
                data['bedrooms'] = f"{bedrooms_match.group(1)} chambre(s)"
            
            floor_match = re.search(r'(?:[ÉE]tage\s*)?(\d+(?:[eè]me)?(?:\s*étage)?|RDC)', facts_text, re.IGNORECASE)
            if floor_match:
                data['floor'] = floor_match.group(1)
        except NoSuchElementException:
            pass
        
        # 4. ADDRESS
        try:
            addr_elem = card.find_element(By.CSS_SELECTOR, SELECTORS['address'])
            address_text = addr_elem.text.strip()
            data['address'] = address_text
            
            postal_match = re.search(r'\((\d{5})\)', address_text)
            if postal_match:
                data['postal_code'] = postal_match.group(1)
                data['department'] = postal_match.group(1)[:2]
            
            city_match = re.search(r',\s*([^,\(]+?)\s*\(\d{5}\)', address_text)
            if city_match:
                data['city'] = city_match.group(1).strip()
            else:
                city_match = re.search(r'^([^,\(]+?)\s*\(\d{5}\)', address_text)
                if city_match:
                    data['city'] = city_match.group(1).strip()
        except NoSuchElementException:
            pass
        
        # 5. PROPERTY TYPE (fallback)
        if not data['type'] and raw_text:
            type_match = re.search(r'(Appartement|Maison|Studio|Villa|Duplex|Loft|Terrain)\s+à\s+vendre', raw_text, re.IGNORECASE)
            if type_match:
                data['type'] = type_match.group(1)
        
        # 6. ENERGY CLASS
        try:
            energy_elem = card.find_element(By.CSS_SELECTOR, SELECTORS['energy'])
            energy_html = energy_elem.get_attribute('innerHTML')
            energy_match = re.search(r'>([A-G])<', energy_html)
            if energy_match:
                data['energy_class'] = energy_match.group(1)
        except NoSuchElementException:
            pass
        
        # 7. TAGS
        try:
            tags_elem = card.find_element(By.CSS_SELECTOR, SELECTORS['tags'])
            if 'nouveau' in tags_elem.text.lower():
                data['is_new'] = True
        except NoSuchElementException:
            pass
        
        # FALLBACKS from raw text
        if not data['price'] and raw_text:
            price_match = re.search(r'([\d\s\u00a0\u202f]{4,})\s*€(?!\s*/)', raw_text)
            if price_match:
                data['price'] = price_match.group(1).replace('\xa0', ' ').replace('\u202f', ' ').strip() + ' €'
        
        if not data['surface'] and raw_text:
            surface_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*m[²2]', raw_text)
            if surface_match:
                data['surface'] = f"{surface_match.group(1)} m²"
        
        if not data['rooms'] and raw_text:
            rooms_match = re.search(r'(\d+)\s*pièces?', raw_text, re.IGNORECASE)
            if rooms_match:
                data['rooms'] = f"{rooms_match.group(1)} pièce(s)"
        
        if not data['postal_code'] and raw_text:
            postal_match = re.search(r'\((\d{5})\)', raw_text)
            if postal_match:
                data['postal_code'] = postal_match.group(1)
                data['department'] = postal_match.group(1)[:2]
        
        # CONFIDENCE SCORE
        critical_fields = {'url', 'price', 'surface'}
        found_critical = sum(1 for f in critical_fields if data.get(f))
        
        if found_critical == 3:
            data['confidence_score'] = 10
        elif found_critical == 2:
            data['confidence_score'] = 7
        elif found_critical == 1:
            data['confidence_score'] = 4
        else:
            data['confidence_score'] = 1
            
    except Exception as e:
        logger.error(f"Worker {worker_id}: Error parsing listing: {e}")
        data['confidence_score'] = 0
    
    return data


def validate_listing(data: Dict) -> bool:
    has_url = bool(data.get('url'))
    has_price = bool(data.get('price'))
    has_type = bool(data.get('type'))
    has_surface = bool(data.get('surface'))
    return has_url and (has_price or has_surface or has_type)


def format_for_csv(value) -> str:
    if value is None or (isinstance(value, str) and value.strip() == ''):
        return MISSING_DATA_INDICATOR
    if isinstance(value, bool):
        return 'Oui' if value else 'Non'
    return str(value)


# ---------------------------------------------------------
# Browser Setup
# ---------------------------------------------------------
def setup_chrome_driver(worker_id: int, headless: bool = False) -> webdriver:
    user_agent = USER_AGENTS[worker_id % len(USER_AGENTS)]
    
    if UNDETECTED_AVAILABLE:
        options = uc.ChromeOptions()
        options.add_argument(f"--user-agent={user_agent}")
        if headless:
            options.add_argument("--headless=new")
        driver = uc.Chrome(options=options)
    else:
        options = ChromeOptions()
        options.add_argument(f"--user-agent={user_agent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        if headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    width, height = random.choice(VIEWPORT_SIZES)
    driver.set_window_size(width, height)
    
    x_offset = (worker_id % 3) * 650
    y_offset = (worker_id // 3) * 450
    driver.set_window_position(x_offset, y_offset)
    
    return driver


def randomize_viewport(driver, worker_id: int):
    width, height = random.choice(VIEWPORT_SIZES)
    driver.set_window_size(width, height)


# ---------------------------------------------------------
# Scrolling
# ---------------------------------------------------------
def scroll_to_load_all_cards(driver, worker_id: int, page_num: int) -> int:
    logger.debug(f"Worker {worker_id}: Scrolling page {page_num}...")
    
    scroll_steps = 5
    last_card_count = 0
    stable_count = 0
    
    for step in range(scroll_steps):
        scroll_position = (step + 1) * (1.0 / scroll_steps)
        target_y = int(driver.execute_script("return document.body.scrollHeight") * scroll_position)
        current_y = driver.execute_script("return window.pageYOffset")
        
        distance = target_y - current_y
        num_increments = random.randint(8, 15)
        
        for i in range(num_increments):
            progress = (i + 1) / num_increments
            eased_progress = 1 - pow(1 - progress, 3)
            next_y = int(current_y + (distance * eased_progress))
            driver.execute_script(f"window.scrollTo({{top: {next_y}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.03, 0.1))
        
        time.sleep(random.uniform(*LAZY_SCROLL_WAIT))
        
        # Check for popups that might appear during scroll
        check_and_dismiss_popups_if_needed(driver, worker_id)
        
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, SELECTORS['card'])
            current_count = len(cards)
            
            if current_count == last_card_count:
                stable_count += 1
                if stable_count >= 2:
                    break
            else:
                stable_count = 0
            last_card_count = current_count
        except:
            pass
    
    # Scroll back to top
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    time.sleep(random.uniform(*FINAL_WAIT_AFTER_SCROLL))
    
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, SELECTORS['card'])
        return len(cards)
    except:
        return 0


def save_debug_info(driver, worker_id: int, page_num: int, reason: str):
    if not DEBUG_MODE:
        return
    
    debug_dir = os.path.join(OUTPUT_DIR, "debug", f"worker{worker_id}")
    os.makedirs(debug_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%H%M%S')
    
    try:
        with open(os.path.join(debug_dir, f"page{page_num}_{reason}_{timestamp}.html"), 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    except:
        pass
    
    try:
        driver.save_screenshot(os.path.join(debug_dir, f"page{page_num}_{reason}_{timestamp}.png"))
    except:
        pass


# ---------------------------------------------------------
# CSV Handling
# ---------------------------------------------------------
def initialize_csv(filename: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Page_Number", "Type", "Price", "Price_Per_M2", "Surface_m2",
            "Rooms", "Bedrooms", "Floor", "Address", "City",
            "PostalCode", "Department", "Energy_Class", "Is_New",
            "Agency", "URL", "Confidence_Score"
        ])
    logger.info(f"Initialized CSV: {filepath}")


def write_listings_to_csv(listings: List[Dict], output_file: str):
    with csv_lock:
        filepath = os.path.join(OUTPUT_DIR, output_file)
        with open(filepath, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            for listing in listings:
                writer.writerow([
                    format_for_csv(str(listing['page_num'])),
                    format_for_csv(listing['type']),
                    format_for_csv(listing['price']),
                    format_for_csv(listing['price_per_m2']),
                    format_for_csv(listing['surface']),
                    format_for_csv(listing['rooms']),
                    format_for_csv(listing['bedrooms']),
                    format_for_csv(listing['floor']),
                    format_for_csv(listing['address']),
                    format_for_csv(listing['city']),
                    format_for_csv(listing['postal_code']),
                    format_for_csv(listing['department']),
                    format_for_csv(listing['energy_class']),
                    format_for_csv(listing['is_new']),
                    format_for_csv(listing['agency']),
                    format_for_csv(listing['url']),
                    listing['confidence_score'],
                ])


def is_duplicate_url(url: Optional[str]) -> bool:
    if not url:
        return False
    with scraped_urls_lock:
        if url in scraped_urls:
            return True
        scraped_urls.add(url)
        return False


# ---------------------------------------------------------
# Worker Function
# ---------------------------------------------------------
def worker_scrape_pages(worker_id: int, driver: webdriver, pages: List[int], output_file: str) -> Dict:
    results = {
        'listings': 0, 'complete': 0,
        'failed_pages': [], 'successful_pages': [],
        'pages_scraped': 0
    }
    
    pages_since_break = 0
    next_break_at = random.randint(*BREAK_EVERY_N_PAGES)
    
    for page_idx, page_num in enumerate(pages):
        try:
            pages_since_break += 1
            if pages_since_break >= next_break_at:
                break_time = random.uniform(*BREAK_DURATION)
                logger.info(f"Worker {worker_id}: Taking a {break_time:.1f}s break...")
                time.sleep(break_time)
                pages_since_break = 0
                next_break_at = random.randint(*BREAK_EVERY_N_PAGES)
                if random.random() < 0.3:
                    randomize_viewport(driver, worker_id)
            
            url = f"{BASE_URL}&page={page_num}"
            logger.info(f"Worker {worker_id}: Loading page {page_num} ({page_idx+1}/{len(pages)})")
            
            driver.get(url)
            time.sleep(random.uniform(*PAGE_LOAD_WAIT))
            
            # CRITICAL: Dismiss any popups before scraping
            ensure_popups_dismissed(driver, worker_id)
            
            card_count = scroll_to_load_all_cards(driver, worker_id, page_num)
            
            # Check popups again after scrolling
            check_and_dismiss_popups_if_needed(driver, worker_id)
            
            if card_count == 0:
                logger.warning(f"Worker {worker_id}: No cards on page {page_num}")
                save_debug_info(driver, worker_id, page_num, "no_cards")
                results['failed_pages'].append(page_num)
                with retry_queue_lock:
                    retry_queue.put((page_num, worker_id, 1))
                continue
            
            cards = driver.find_elements(By.CSS_SELECTOR, SELECTORS['card'])
            logger.info(f"Worker {worker_id}: Page {page_num} has {len(cards)} cards")
            
            listings = []
            complete_count = 0
            duplicate_count = 0
            
            for card in cards:
                time.sleep(random.uniform(*DELAY_BETWEEN_LISTINGS))
                data = parse_listing(card, page_num, worker_id)
                
                if is_duplicate_url(data.get('url')):
                    duplicate_count += 1
                    continue
                
                if validate_listing(data):
                    complete_count += 1
                
                listings.append(data)
            
            write_listings_to_csv(listings, output_file)
            
            results['listings'] += len(listings)
            results['complete'] += complete_count
            results['successful_pages'].append(page_num)
            results['pages_scraped'] += 1
            
            with stats_lock:
                global_stats['total_listings'] += len(listings)
                global_stats['complete_listings'] += complete_count
                global_stats['successful_pages'].add(page_num)
                if worker_id not in global_stats['pages_by_worker']:
                    global_stats['pages_by_worker'][worker_id] = []
                global_stats['pages_by_worker'][worker_id].append(page_num)
            
            status = "✓" if len(listings) >= MIN_LISTINGS_PER_PAGE else "⚠"
            logger.info(f"Worker {worker_id}: Page {page_num} {status} - {len(listings)} listings ({complete_count} complete)")
            
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.error(f"Worker {worker_id}: Error on page {page_num}: {e}")
            logger.debug(traceback.format_exc())
            save_debug_info(driver, worker_id, page_num, "error")
            results['failed_pages'].append(page_num)
            with retry_queue_lock:
                retry_queue.put((page_num, worker_id, 1))
    
    return results


def retry_failed_pages(drivers: List[Tuple[int, webdriver]], output_file: str) -> Dict:
    results = {'retried': 0, 'succeeded': 0, 'failed': []}
    
    if retry_queue.empty():
        return results
    
    pages_to_retry = []
    while not retry_queue.empty():
        try:
            page_num, original_worker, attempt = retry_queue.get_nowait()
            if attempt <= MAX_RETRIES:
                pages_to_retry.append((page_num, attempt))
        except:
            break
    
    if not pages_to_retry:
        return results
    
    logger.info(f"\nRETRY PHASE: {len(pages_to_retry)} pages to retry")
    time.sleep(random.uniform(*RETRY_DELAY))
    
    for page_num, attempt in pages_to_retry:
        worker_id, driver = random.choice(drivers)
        logger.info(f"Retrying page {page_num} (attempt {attempt + 1}/{MAX_RETRIES})")
        
        try:
            url = f"{BASE_URL}&page={page_num}"
            driver.get(url)
            time.sleep(random.uniform(*PAGE_LOAD_WAIT))
            
            ensure_popups_dismissed(driver, worker_id)
            card_count = scroll_to_load_all_cards(driver, worker_id, page_num)
            
            if card_count == 0:
                if attempt < MAX_RETRIES:
                    retry_queue.put((page_num, worker_id, attempt + 1))
                else:
                    results['failed'].append(page_num)
                continue
            
            cards = driver.find_elements(By.CSS_SELECTOR, SELECTORS['card'])
            
            listings = []
            complete_count = 0
            
            for card in cards:
                data = parse_listing(card, page_num, worker_id)
                if not is_duplicate_url(data.get('url')):
                    if validate_listing(data):
                        complete_count += 1
                    listings.append(data)
            
            write_listings_to_csv(listings, output_file)
            results['retried'] += 1
            results['succeeded'] += 1
            
            with stats_lock:
                global_stats['total_listings'] += len(listings)
                global_stats['complete_listings'] += complete_count
                global_stats['successful_pages'].add(page_num)
            
            logger.info(f"✓ Page {page_num} RETRY SUCCESS: {len(listings)} listings")
            
        except Exception as e:
            logger.error(f"✗ Page {page_num} retry failed: {e}")
            if attempt < MAX_RETRIES:
                retry_queue.put((page_num, worker_id, attempt + 1))
            else:
                results['failed'].append(page_num)
    
    return results


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def scrape_parallel(start_page: int, end_page: int, output_file: str, num_workers: int):
    global scraped_urls
    
    logger.info("=" * 70)
    logger.info("SeLoger Scraper v12 - AUTO POPUP HANDLING")
    logger.info("=" * 70)
    logger.info(f"Pages: {start_page} to {end_page}")
    logger.info(f"Workers: {num_workers}")
    logger.info("=" * 70)
    
    with scraped_urls_lock:
        scraped_urls = set()
    
    with stats_lock:
        global_stats['total_listings'] = 0
        global_stats['complete_listings'] = 0
        global_stats['failed_pages'] = set()
        global_stats['successful_pages'] = set()
        global_stats['pages_by_worker'] = {}
    
    while not retry_queue.empty():
        try:
            retry_queue.get_nowait()
        except:
            break
    
    initialize_csv(output_file)
    
    print(f"\n🌐 Opening {num_workers} browser windows...")
    
    drivers = []
    for i in range(num_workers):
        print(f"   Opening browser {i+1}/{num_workers}...")
        try:
            driver = setup_chrome_driver(i)
            driver.get(BASE_URL)
            drivers.append((i, driver))
            time.sleep(1)
            
            # Immediately try to dismiss popups
            ensure_popups_dismissed(driver, i)
            
        except Exception as e:
            logger.error(f"Failed to open browser {i+1}: {e}")
    
    if not drivers:
        logger.error("No browsers could be opened!")
        return
    
    print(f"✅ Opened {len(drivers)} browsers")
    print(f"\n🍪 Attempting to auto-dismiss popups...")
    
    # Give popups a chance to appear, then dismiss them
    time.sleep(3)
    
    for worker_id, driver in drivers:
        ensure_popups_dismissed(driver, worker_id)
    
    print(f"✅ Popup handling complete")
    
    # Distribute pages
    pages = list(range(start_page, end_page + 1))
    pages_per_worker = []
    
    for i in range(len(drivers)):
        worker_pages = [p for j, p in enumerate(pages) if j % len(drivers) == i]
        pages_per_worker.append(worker_pages)
    
    print(f"\n🚀 Starting parallel scrape...")
    
    phase1_start = time.time()
    
    with ThreadPoolExecutor(max_workers=len(drivers)) as executor:
        futures = []
        for (worker_id, driver), worker_pages in zip(drivers, pages_per_worker):
            if worker_pages:
                future = executor.submit(
                    worker_scrape_pages,
                    worker_id, driver, worker_pages, output_file
                )
                futures.append((future, worker_id))
        
        for future, worker_id in futures:
            try:
                result = future.result()
                logger.info(f"Worker {worker_id} finished: {result['listings']} listings")
            except Exception as e:
                logger.error(f"Worker {worker_id} failed: {e}")
    
    phase1_time = time.time() - phase1_start
    
    # Retries
    retry_results = {'retried': 0, 'succeeded': 0, 'failed': []}
    for retry_round in range(MAX_RETRY_ROUNDS):
        if retry_queue.empty():
            break
        round_results = retry_failed_pages(drivers, output_file)
        retry_results['retried'] += round_results['retried']
        retry_results['succeeded'] += round_results['succeeded']
        retry_results['failed'].extend(round_results['failed'])
    
    total_time = time.time() - phase1_start
    
    # Summary
    with stats_lock:
        total_listings = global_stats['total_listings']
        complete_listings = global_stats['complete_listings']
        successful_pages = global_stats['successful_pages']
    
    print("\n" + "=" * 70)
    print("📊 SCRAPING COMPLETE")
    print("=" * 70)
    print(f"   Total listings: {total_listings}")
    if total_listings:
        print(f"   Complete data: {complete_listings} ({100*complete_listings/total_listings:.1f}%)")
    print(f"   Pages successful: {len(successful_pages)}/{end_page - start_page + 1}")
    print(f"   Time: {total_time:.1f}s ({total_time/60:.1f} min)")
    if successful_pages:
        print(f"   Speed: {len(successful_pages)/total_time*60:.1f} pages/min")
    print(f"\n   Output: {OUTPUT_DIR}/{output_file}")
    print("=" * 70)
    
    print("\nClosing browsers...")
    for worker_id, driver in drivers:
        try:
            driver.quit()
        except:
            pass
    
    print("Done!")


def main():
    parser = argparse.ArgumentParser(description="SeLoger Scraper v12 - Auto Popup Handling")
    parser.add_argument("--start", type=int, help="Start page")
    parser.add_argument("--end", type=int, help="End page")
    parser.add_argument("--workers", type=int, default=PARALLEL_WORKERS)
    parser.add_argument("--output", type=str)
    parser.add_argument("--debug", action="store_true")
    
    args = parser.parse_args()
    
    global DEBUG_MODE
    DEBUG_MODE = args.debug
    
    if not args.start or not args.end:
        print("\n" + "=" * 70)
        print("SeLoger Scraper v12 - AUTO POPUP HANDLING")
        print("=" * 70)
        print("\n✨ NEW: Automatically dismisses all popups!")
        print("   - Cookie consent")
        print("   - Modal dialogs")
        print("   - Newsletter popups")
        print("   - Any other overlays\n")
        
        try:
            start = int(input("Start page: ").strip())
            end = int(input("End page: ").strip())
            workers_input = input(f"Workers (default {PARALLEL_WORKERS}): ").strip()
            workers = int(workers_input) if workers_input else PARALLEL_WORKERS
            workers = max(1, min(workers, MAX_WORKERS))
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return
    else:
        start = args.start
        end = args.end
        workers = max(1, min(args.workers, MAX_WORKERS))
    
    output_file = args.output or f"seloger_v12_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    confirm = input(f"\nScrape pages {start}-{end} with {workers} workers? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    scrape_parallel(start, end, output_file, workers)


if __name__ == "__main__":
    main()