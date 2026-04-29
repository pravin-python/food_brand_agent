"""
tools/ecommerce/ecomm_tools.py
E-commerce availability checker tools for the E-commerce Agent
"""

from playwright.sync_api import sync_playwright
from typing import Optional
import time

CITIES_TO_CHECK = [
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
    "Chandigarh", "Indore", "Bhopal", "Kochi", "Nagpur",
    "Surat", "Patna", "Vadodara", "Guwahati", "Coimbatore",
]

CITY_COORDS = {
    "Mumbai":     (19.0760, 72.8777),
    "Delhi":      (28.7041, 77.1025),
    "Bengaluru":  (12.9716, 77.5946),
    "Chennai":    (13.0827, 80.2707),
    "Hyderabad":  (17.3850, 78.4867),
    "Kolkata":    (22.5726, 88.3639),
    "Pune":       (18.5204, 73.8567),
    "Ahmedabad":  (23.0225, 72.5714),
    "Jaipur":     (26.9124, 75.7873),
    "Lucknow":    (26.8467, 80.9462),
    "Chandigarh": (30.7333, 76.7794),
    "Indore":     (22.7196, 75.8577),
    "Bhopal":     (23.2599, 77.4126),
    "Kochi":      (9.9312,  76.2673),
    "Nagpur":     (21.1458, 79.0882),
}


def ecomm_check(platform: str, city: str, brand_name: str) -> dict:
    """
    Check if a brand's products are available on a platform in a given city.

    Args:
        platform: One of "swiggy", "blinkit", "amazon"
        city: Indian city name
        brand_name: Food brand to search

    Returns:
        dict with keys: found (bool), product_count (int), url (str)
    """
    try:
        if platform == "swiggy":
            return _check_swiggy(city, brand_name)
        elif platform == "blinkit":
            return _check_blinkit(city, brand_name)
        elif platform == "amazon":
            return _check_amazon(city, brand_name)
        else:
            return {"found": False, "product_count": 0, "url": "", "error": "unknown platform"}
    except Exception as e:
        return {"found": False, "product_count": 0, "url": "", "error": str(e)}


def _check_swiggy(city: str, brand_name: str) -> dict:
    url = f"https://www.swiggy.com/search?query={brand_name.replace(' ', '+')}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            geolocation={"latitude": CITY_COORDS.get(city, (19.07, 72.87))[0],
                         "longitude": CITY_COORDS.get(city, (19.07, 72.87))[1]},
            permissions=["geolocation"],
        )
        page = ctx.new_page()
        page.goto(url, timeout=20000)
        time.sleep(2)
        items = page.query_selector_all(".store-card, [data-testid='store-card']")
        count = len(items)
        browser.close()
        return {"found": count > 0, "product_count": count, "url": url, "platform": "swiggy"}


def _check_blinkit(city: str, brand_name: str) -> dict:
    url = f"https://blinkit.com/s/?q={brand_name.replace(' ', '+')}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            geolocation={"latitude": CITY_COORDS.get(city, (28.70, 77.10))[0],
                         "longitude": CITY_COORDS.get(city, (28.70, 77.10))[1]},
            permissions=["geolocation"],
        )
        page = ctx.new_page()
        page.goto(url, timeout=20000)
        time.sleep(2)
        items = page.query_selector_all(".product-card")
        count = len(items)
        browser.close()
        return {"found": count > 0, "product_count": count, "url": url, "platform": "blinkit"}


def _check_amazon(city: str, brand_name: str) -> dict:
    url = f"https://www.amazon.in/s?k={brand_name.replace(' ', '+')}&i=grocery"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=20000)
        items = page.query_selector_all("[data-component-type='s-search-result']")
        count = len(items)
        browser.close()
        return {"found": count > 0, "product_count": count, "url": url, "platform": "amazon"}


def get_cities_list() -> list[str]:
    """Returns the full list of cities to check."""
    return CITIES_TO_CHECK


# ---- Register tools list for DeepAgent ----
ECOMM_TOOLS = [ecomm_check, get_cities_list]
