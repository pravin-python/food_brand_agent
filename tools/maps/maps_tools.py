"""
tools/maps/maps_tools.py
Google Maps, Justdial, IndiaMart tools for the Web & Maps Agent.
Uses SerpAPI (if key set) or DuckDuckGo/requests fallback — no sync_playwright.
"""

import os
import requests
from bs4 import BeautifulSoup

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
SERP_API_KEY        = os.getenv("SERP_API_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def maps_search(query: str, city: str) -> list[dict]:
    """
    Search Google Maps for a query in a specific Indian city.
    Uses SerpAPI if key is set, else Google Places API, else DuckDuckGo fallback.

    Args:
        query: e.g. "AMUL distributor"
        city:  Indian city name

    Returns:
        List of business location dicts
    """
    full_query = f"{query} {city} India"

    if SERP_API_KEY:
        return _serp_maps_search(full_query, city)
    elif GOOGLE_MAPS_API_KEY:
        return _google_places_search(full_query, city)
    else:
        return _duckduckgo_search(full_query, city)


def _serp_maps_search(query: str, city: str) -> list[dict]:
    """Use SerpAPI Google Maps engine."""
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "engine": "google_maps", "api_key": SERP_API_KEY},
            timeout=15,
        )
        data = resp.json()
        results = []
        for place in data.get("local_results", []):
            address = place.get("address", "")
            results.append({
                "name":     place.get("title", ""),
                "address":  address,
                "city":     city,
                "state":    address.split(",")[-1].strip() if "," in address else "",
                "phone":    place.get("phone", ""),
                "rating":   place.get("rating", 0),
                "source":   "google_maps",
                "verified": True,
            })
        return results
    except Exception as e:
        return [{"error": str(e), "source": "serpapi"}]


def _google_places_search(query: str, city: str) -> list[dict]:
    """Use Google Places Text Search API."""
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": query, "region": "in", "key": GOOGLE_MAPS_API_KEY},
            timeout=15,
        )
        data = resp.json()
        results = []
        for place in data.get("results", [])[:10]:
            address = place.get("formatted_address", "")
            results.append({
                "name":     place.get("name", ""),
                "address":  address,
                "city":     city,
                "state":    address.split(",")[-2].strip() if "," in address else "",
                "rating":   place.get("rating", 0),
                "source":   "google_places",
                "verified": True,
            })
        return results
    except Exception as e:
        return [{"error": str(e), "source": "google_places"}]


def _duckduckgo_search(query: str, city: str) -> list[dict]:
    """Fallback: DuckDuckGo instant answer API for location results."""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
            headers=HEADERS,
            timeout=10,
        )
        data = resp.json()
        results = []
        for r in data.get("RelatedTopics", [])[:10]:
            text = r.get("Text", "")
            if text:
                results.append({
                    "name":     text.split(" - ")[0] if " - " in text else text[:60],
                    "address":  text,
                    "city":     city,
                    "state":    "",
                    "source":   "duckduckgo",
                    "verified": False,
                })
        return results
    except Exception as e:
        return [{"error": str(e), "source": "duckduckgo"}]


def justdial_search(brand: str, city: str) -> list[dict]:
    """
    Search Justdial for brand dealers/distributors in a city.

    Args:
        brand: Brand name
        city:  Indian city

    Returns:
        List of dealer dicts
    """
    results = []
    city_slug  = city.lower().replace(" ", "-")
    brand_slug = brand.lower().replace(" ", "-")
    url = f"https://www.justdial.com/{city_slug}/{brand_slug}-dealers"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple known Justdial selectors
        listings = (
            soup.select(".resultbox_info") or
            soup.select(".store-details") or
            soup.select(".jsx-3529314109")
        )

        for listing in listings[:15]:
            name_el = listing.select_one(".store_name, h2, .resultbox_title_anchor")
            addr_el = listing.select_one(".address-info, .jd-address, .resultbox_address")
            name    = name_el.get_text(strip=True) if name_el else ""
            address = addr_el.get_text(strip=True) if addr_el else ""
            if name:
                results.append({
                    "name":     name,
                    "address":  address,
                    "city":     city,
                    "state":    "",
                    "source":   "justdial",
                    "verified": False,
                })
    except Exception as e:
        results.append({"error": str(e), "source": "justdial"})

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
    url = f"https://www.indiamart.com/search.mp?ss={requests.utils.quote(brand)}&categ=food"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple known IndiaMart selectors
        cards = (
            soup.select(".imb-bx") or
            soup.select(".supplier-card") or
            soup.select(".listing-card")
        )

        for card in cards[:20]:
            name_el  = card.select_one(".imb_bname, .supplier-name, .lc-name")
            city_el  = card.select_one(".imb_city, .city, .lc-city")
            state_el = card.select_one(".imb_state, .state, .lc-state")

            results.append({
                "name":    name_el.get_text(strip=True)  if name_el  else "",
                "city":    city_el.get_text(strip=True)  if city_el  else "",
                "state":   state_el.get_text(strip=True) if state_el else "",
                "source":  "indiamart",
                "verified": False,
            })
    except Exception as e:
        results.append({"error": str(e), "source": "indiamart"})

    return results


# ---- Register tools list for DeepAgent ----
MAPS_TOOLS = [maps_search, justdial_search, indiamart_search]
