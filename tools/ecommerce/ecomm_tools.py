"""
tools/ecommerce/ecomm_tools.py
E-commerce availability checker tools for the E-commerce Agent.
Uses requests + BeautifulSoup (async-safe; no sync_playwright).
"""

import requests
from bs4 import BeautifulSoup

CITIES_TO_CHECK = [
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
    "Chandigarh", "Indore", "Bhopal", "Kochi", "Nagpur",
    "Surat", "Patna", "Vadodara", "Guwahati", "Coimbatore",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


def ecomm_check(platform: str, city: str, brand_name: str) -> dict:
    """
    Check if a brand's products are available on a platform in a given city.

    Args:
        platform:   One of "swiggy", "blinkit", "amazon"
        city:       Indian city name
        brand_name: Food brand to search

    Returns:
        dict with keys: found (bool), product_count (int), url (str), platform (str)
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
    """Check Swiggy Instamart for brand availability (uses public search API)."""
    url = f"https://www.swiggy.com/api/instamart/search?query={requests.utils.quote(brand_name)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        # Swiggy Instamart API returns 'data' > 'products' list
        products = (
            data.get("data", {}).get("products", []) or
            data.get("data", {}).get("cards", [])
        )
        count = len(products)
        return {
            "found": count > 0,
            "product_count": count,
            "url": f"https://www.swiggy.com/instamart/search?query={brand_name}",
            "platform": "swiggy",
            "city": city,
        }
    except Exception as e:
        # Fallback: scrape HTML search page
        try:
            page_url = f"https://www.swiggy.com/instamart/search?query={requests.utils.quote(brand_name)}"
            r = requests.get(page_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("[data-testid='product-card'], .sc-aXZVg")
            return {
                "found": len(items) > 0,
                "product_count": len(items),
                "url": page_url,
                "platform": "swiggy",
                "city": city,
            }
        except Exception:
            return {"found": False, "product_count": 0, "url": "", "platform": "swiggy", "error": str(e)}


def _check_blinkit(city: str, brand_name: str) -> dict:
    """Check Blinkit for brand availability."""
    url = f"https://blinkit.com/s/?q={requests.utils.quote(brand_name)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        # Blinkit renders server-side product cards
        items = soup.select(".product-card, [class*='Product__Container']")
        count = len(items)
        return {
            "found": count > 0,
            "product_count": count,
            "url": url,
            "platform": "blinkit",
            "city": city,
        }
    except Exception as e:
        return {"found": False, "product_count": 0, "url": url, "platform": "blinkit", "error": str(e)}


def _check_amazon(city: str, brand_name: str) -> dict:
    """Check Amazon India grocery for brand availability."""
    url = f"https://www.amazon.in/s?k={requests.utils.quote(brand_name)}&i=grocery"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("[data-component-type='s-search-result']")
        count = len(items)
        return {
            "found": count > 0,
            "product_count": count,
            "url": url,
            "platform": "amazon",
            "city": city,
        }
    except Exception as e:
        return {"found": False, "product_count": 0, "url": url, "platform": "amazon", "error": str(e)}


def get_cities_list() -> list[str]:
    """Returns the full list of Indian cities to check."""
    return CITIES_TO_CHECK


# ---- Register tools list for DeepAgent ----
ECOMM_TOOLS = [ecomm_check, get_cities_list]
