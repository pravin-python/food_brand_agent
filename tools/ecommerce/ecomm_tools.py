"""
tools/ecommerce/ecomm_tools.py
E-commerce availability checker tools for the E-commerce Agent.

Checks Swiggy Instamart, Blinkit, and Amazon India across major Indian cities.
Uses Playwright for JS-rendered pages; gracefully returns empty on block/error.
"""

import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


CITIES_TO_CHECK = [
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
    "Chandigarh", "Indore", "Bhopal", "Kochi", "Nagpur",
    "Surat", "Patna", "Vadodara", "Guwahati", "Coimbatore",
]

CITY_COORDS: dict[str, tuple[float, float]] = {
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
    "Kochi":      ( 9.9312, 76.2673),
    "Nagpur":     (21.1458, 79.0882),
    "Surat":      (21.1702, 72.8311),
    "Patna":      (25.5941, 85.1376),
    "Vadodara":   (22.3072, 73.1812),
    "Guwahati":   (26.1445, 91.7362),
    "Coimbatore": (11.0168, 76.9558),
}

DEFAULT_COORD = (20.5937, 78.9629)  # geographic centre of India


def get_cities_list() -> list[str]:
    """Return the full list of Indian cities to check."""
    return CITIES_TO_CHECK


def ecomm_check(platform: str, city: str, brand_name: str) -> dict:
    """
    Check if a brand's products are available on a given platform in a city.

    Args:
        platform:   One of "swiggy", "blinkit", "amazon".
        city:       Indian city name (must match CITIES_TO_CHECK or similar).
        brand_name: Food brand to search for.

    Returns:
        Dict with keys: found (bool), product_count (int), url (str),
        platform (str), city (str), error (str, optional).
    """
    if not HAS_PLAYWRIGHT:
        return {
            "found": False, "product_count": 0, "url": "",
            "platform": platform, "city": city,
            "error": "playwright not installed",
        }

    try:
        if platform == "swiggy":
            return _check_swiggy(city, brand_name)
        if platform == "blinkit":
            return _check_blinkit(city, brand_name)
        if platform == "amazon":
            return _check_amazon(city, brand_name)
        return {
            "found": False, "product_count": 0, "url": "",
            "platform": platform, "city": city,
            "error": f"unknown platform: {platform}",
        }
    except Exception as exc:
        return {
            "found": False, "product_count": 0, "url": "",
            "platform": platform, "city": city, "error": str(exc),
        }


# ─── Platform implementations ─────────────────────────────────────────────────

def _check_swiggy(city: str, brand_name: str) -> dict:
    lat, lon = CITY_COORDS.get(city, DEFAULT_COORD)
    url = f"https://www.swiggy.com/search?query={_enc(brand_name)}"
    count = 0
    error = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                geolocation={"latitude": lat, "longitude": lon},
                permissions=["geolocation"],
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15",
            )
            page = ctx.new_page()
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Try multiple card selectors used across Swiggy versions
            for sel in [
                "[data-testid='store-card']",
                ".store-card",
                "[class*='RestaurantCard']",
                "[class*='product-card']",
                "[class*='item-card']",
            ]:
                items = page.query_selector_all(sel)
                if items:
                    count = len(items)
                    break

            browser.close()
    except Exception as exc:
        error = str(exc)

    return {"found": count > 0, "product_count": count, "url": url,
            "platform": "swiggy", "city": city, **({"error": error} if error else {})}


def _check_blinkit(city: str, brand_name: str) -> dict:
    lat, lon = CITY_COORDS.get(city, DEFAULT_COORD)
    url = f"https://blinkit.com/s/?q={_enc(brand_name)}"
    count = 0
    error = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                geolocation={"latitude": lat, "longitude": lon},
                permissions=["geolocation"],
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15",
            )
            page = ctx.new_page()
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            for sel in [
                ".product-card",
                "[class*='ProductCard']",
                "[class*='product-container']",
                "[data-testid='product-card']",
            ]:
                items = page.query_selector_all(sel)
                if items:
                    count = len(items)
                    break

            browser.close()
    except Exception as exc:
        error = str(exc)

    return {"found": count > 0, "product_count": count, "url": url,
            "platform": "blinkit", "city": city, **({"error": error} if error else {})}


def _check_amazon(city: str, brand_name: str) -> dict:
    url = f"https://www.amazon.in/s?k={_enc(brand_name)}&i=grocery"
    count = 0
    error = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                )
            )
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            for sel in [
                "[data-component-type='s-search-result']",
                "[data-asin]",
                ".s-result-item",
            ]:
                items = page.query_selector_all(sel)
                if items:
                    count = len(items)
                    break

            browser.close()
    except Exception as exc:
        error = str(exc)

    return {"found": count > 0, "product_count": count, "url": url,
            "platform": "amazon", "city": city, **({"error": error} if error else {})}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _enc(text: str) -> str:
    return text.replace(" ", "+")


# ── Tool registry ─────────────────────────────────────────────────────────────
ECOMM_TOOLS = [ecomm_check, get_cities_list]
