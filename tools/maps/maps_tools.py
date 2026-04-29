"""
tools/maps/maps_tools.py
Google Maps, Justdial, IndiaMart tools for the Web & Maps Agent
"""

import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
SERP_API_KEY        = os.getenv("SERP_API_KEY", "")


def maps_search(query: str, city: str) -> list[dict]:
    """
    Search Google Maps for a query in a specific city.
    Uses SerpAPI if key available, else falls back to Playwright scraping.

    Args:
        query: e.g. "Haldirams distributor"
        city: Indian city name

    Returns:
        List of business location dicts
    """
    full_query = f"{query} {city} India"

    if SERP_API_KEY:
        return _serp_maps_search(full_query)
    else:
        return _playwright_maps_search(full_query)


def _serp_maps_search(query: str) -> list[dict]:
    resp = requests.get(
        "https://serpapi.com/search",
        params={"q": query, "engine": "google_maps", "api_key": SERP_API_KEY},
        timeout=15,
    )
    data = resp.json()
    results = []
    for place in data.get("local_results", []):
        results.append({
            "name":    place.get("title", ""),
            "address": place.get("address", ""),
            "city":    place.get("address", "").split(",")[-2].strip() if "," in place.get("address","") else "",
            "state":   place.get("address", "").split(",")[-1].strip() if "," in place.get("address","") else "",
            "phone":   place.get("phone", ""),
            "rating":  place.get("rating", 0),
            "source":  "google_maps",
            "verified": True,
        })
    return results


def _playwright_maps_search(query: str) -> list[dict]:
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"https://www.google.com/maps/search/{query.replace(' ', '+')}", timeout=25000)
            page.wait_for_selector('[data-result-index]', timeout=10000)

            cards = page.query_selector_all('[data-result-index]')
            for card in cards[:10]:
                name_el = card.query_selector('.qBF1Pd')
                addr_el = card.query_selector('.W4Efsd:last-child')
                name    = name_el.inner_text() if name_el else ""
                address = addr_el.inner_text() if addr_el else ""
                parts   = address.split(",")
                results.append({
                    "name":     name,
                    "address":  address,
                    "city":     parts[-2].strip() if len(parts) >= 2 else "",
                    "state":    parts[-1].strip() if len(parts) >= 1 else "",
                    "source":   "google_maps",
                    "verified": False,
                })
            browser.close()
    except Exception as e:
        results.append({"error": str(e)})
    return results


def justdial_search(brand: str, city: str) -> list[dict]:
    """
    Search Justdial for brand dealers/distributors in a city.

    Args:
        brand: Brand name
        city: Indian city

    Returns:
        List of dealer dicts
    """
    results = []
    city_slug  = city.lower().replace(" ", "-")
    brand_slug = brand.lower().replace(" ", "-")
    url = f"https://www.justdial.com/{city_slug}/{brand_slug}-dealers"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        listings = soup.select(".resultbox_info, .store-details")

        for listing in listings[:15]:
            name_el = listing.select_one(".store_name, h2")
            addr_el = listing.select_one(".address-info, .jd-address")
            name    = name_el.get_text(strip=True) if name_el else ""
            address = addr_el.get_text(strip=True) if addr_el else ""
            results.append({
                "name":     name,
                "address":  address,
                "city":     city,
                "state":    "",
                "source":   "justdial",
                "verified": False,
            })
    except Exception as e:
        results.append({"error": str(e)})

    return results


def indiamart_search(brand: str) -> list[dict]:
    """
    Search IndiaMart for wholesale distributors/suppliers of a brand across India.

    Args:
        brand: Brand name

    Returns:
        List of supplier location dicts
    """
    results = []
    url = f"https://www.indiamart.com/search.mp?ss={brand.replace(' ', '+')}&categ=food"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(".imb-bx, .supplier-card")

        for card in cards[:20]:
            name_el  = card.select_one(".imb_bname, .supplier-name")
            city_el  = card.select_one(".imb_city, .city")
            state_el = card.select_one(".imb_state, .state")

            results.append({
                "name":    name_el.get_text(strip=True)  if name_el  else "",
                "city":    city_el.get_text(strip=True)  if city_el  else "",
                "state":   state_el.get_text(strip=True) if state_el else "",
                "source":  "indiamart",
                "verified": False,
            })
    except Exception as e:
        results.append({"error": str(e)})

    return results


# ---- Register tools list for DeepAgent ----
MAPS_TOOLS = [maps_search, justdial_search, indiamart_search]
