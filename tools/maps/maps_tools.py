"""
tools/maps/maps_tools.py
Google Maps, Justdial, IndiaMart tools for the Web & Maps Agent.

Priority order:
  1. SerpAPI (reliable, needs SERP_API_KEY env var)
  2. Playwright-based Google Maps scraping (fragile, no key needed)
  3. Requests + BeautifulSoup for Justdial / IndiaMart
"""

import os
import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# API keys are lazy-loaded inside each function so dotenv is always applied first

MAJOR_CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
    "Surat", "Nagpur", "Indore", "Bhopal", "Kochi",
]


def maps_search(query: str, city: str) -> list[dict]:
    """
    Search Google Maps for a query in a specific Indian city.

    Uses SerpAPI if SERP_API_KEY is set, otherwise falls back to
    Playwright-based scraping of Google Maps.

    Args:
        query: Search query, e.g. "AMUL distributor".
        city:  Indian city name.

    Returns:
        List of business location dicts with: name, address, city, state,
        phone, rating, source, verified.
    """
    full_query = f"{query} {city} India"

    # Lazy-load keys every call so dotenv changes are picked up
    serp_key = os.getenv("SERP_API_KEY", "").strip()

    if serp_key:
        results = _serp_maps_search(full_query, city, serp_key)
        if results and not all("error" in r for r in results):
            return results

    if HAS_PLAYWRIGHT:
        return _playwright_maps_search(full_query, city)

    return [{"error": "no search method available — set SERP_API_KEY in .env", "city": city}]


def _serp_maps_search(query: str, city: str, serp_key: str) -> list[dict]:
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "engine": "google_maps", "api_key": serp_key},
            timeout=15,
        )
        data = resp.json()
        results = []
        for place in data.get("local_results", []):
            addr = place.get("address", "")
            parts = [p.strip() for p in addr.split(",")]
            results.append({
                "name":     place.get("title", ""),
                "address":  addr,
                "city":     parts[-2] if len(parts) >= 2 else city,
                "state":    parts[-1] if parts else "",
                "phone":    place.get("phone", ""),
                "rating":   place.get("rating", 0),
                "source":   "google_maps_serp",
                "verified": True,
            })
        return results
    except Exception as exc:
        return [{"error": str(exc), "source": "serp", "city": city}]


def _playwright_maps_search(query: str, city: str) -> list[dict]:
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                )
            )
            maps_url = (
                "https://www.google.com/maps/search/"
                + query.replace(" ", "+")
            )
            page.goto(maps_url, timeout=25_000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Google Maps renders results in a feed panel
            card_selectors = [
                '[data-result-index]',
                '[jstcache]',
                '.Nv2PK',
                '[class*="result"]',
            ]
            cards = []
            for sel in card_selectors:
                cards = page.query_selector_all(sel)
                if cards:
                    break

            for card in cards[:10]:
                name_el = card.query_selector('.qBF1Pd, [class*="fontHeadlineSmall"]')
                addr_el = card.query_selector('.W4Efsd:last-child, [class*="fontBodyMedium"]')
                name    = name_el.inner_text() if name_el else ""
                address = addr_el.inner_text() if addr_el else ""
                parts   = [p.strip() for p in address.split(",")]

                if name:
                    results.append({
                        "name":     name,
                        "address":  address,
                        "city":     parts[-2] if len(parts) >= 2 else city,
                        "state":    parts[-1] if parts else "",
                        "phone":    "",
                        "rating":   0,
                        "source":   "google_maps_playwright",
                        "verified": False,
                    })

            browser.close()
    except Exception as exc:
        results.append({"error": str(exc), "source": "google_maps_playwright", "city": city})
    return results


def justdial_search(brand: str, city: str) -> list[dict]:
    """
    Search Justdial for brand dealers/distributors in an Indian city.

    Args:
        brand: Brand name.
        city:  Indian city.

    Returns:
        List of dealer dicts with: name, address, city, phone, source.
    """
    results = []
    city_slug  = city.lower().replace(" ", "-")
    brand_slug = brand.lower().replace(" ", "-")

    # Try multiple URL patterns Justdial uses
    urls = [
        f"https://www.justdial.com/{city_slug}/{brand_slug}-dealers",
        f"https://www.justdial.com/{city_slug}/{brand_slug}-distributors",
        f"https://www.justdial.com/{city_slug}/{brand_slug}",
    ]

    for url in urls:
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Referer": "https://www.justdial.com/",
                },
                timeout=15,
            )
            soup = BeautifulSoup(resp.text, "html.parser")

            # Justdial uses several different class names across page versions
            listings = soup.select(
                ".resultbox_info, .store-details, "
                "[class*='resultbox'], [class*='jsx-'], "
                ".jdoRest, .cntanr"
            )

            for listing in listings[:15]:
                name_el  = listing.select_one(".store_name, h2, h3, [class*='name']")
                addr_el  = listing.select_one(".address-info, .jd-address, [class*='address']")
                phone_el = listing.select_one(".contact-info, [class*='phone'], [class*='tel']")

                name  = name_el.get_text(strip=True)  if name_el  else ""
                addr  = addr_el.get_text(strip=True)  if addr_el  else ""
                phone = phone_el.get_text(strip=True) if phone_el else ""

                if name:
                    results.append({
                        "name":    name,
                        "address": addr,
                        "city":    city,
                        "state":   "",
                        "phone":   phone,
                        "source":  "justdial",
                        "verified": False,
                    })

            if results:
                break  # stop trying URLs once we have results

        except Exception as exc:
            results.append({"error": str(exc), "source": "justdial", "city": city})

    return results


def indiamart_search(brand: str) -> list[dict]:
    """
    Search IndiaMart for wholesale distributors/suppliers of a brand across India.

    Args:
        brand: Brand name.

    Returns:
        List of supplier location dicts with: name, city, state, source.
    """
    results = []
    urls = [
        f"https://www.indiamart.com/search.mp?ss={_enc(brand)}&categ=food",
        f"https://www.indiamart.com/proddetail/{_enc(brand.lower())}.html",
    ]

    for url in urls:
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-IN,en;q=0.9",
                },
                timeout=15,
            )
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select(
                ".imb-bx, .supplier-card, "
                "[class*='supplier'], [class*='seller'], "
                ".bx-sl, .prd-detail"
            )

            for card in cards[:20]:
                name_el  = card.select_one("[class*='bname'], [class*='name'], h3, h4")
                city_el  = card.select_one("[class*='city'], [class*='location']")
                state_el = card.select_one("[class*='state']")

                name  = name_el.get_text(strip=True)  if name_el  else ""
                city  = city_el.get_text(strip=True)  if city_el  else ""
                state = state_el.get_text(strip=True) if state_el else ""

                if name:
                    results.append({
                        "name":    name,
                        "city":    city,
                        "state":   state,
                        "source":  "indiamart",
                        "verified": False,
                    })

            if results:
                break

        except Exception as exc:
            results.append({"error": str(exc), "source": "indiamart"})

    return results


# ─── Helper ───────────────────────────────────────────────────────────────────

def _enc(text: str) -> str:
    return text.replace(" ", "+")


# ── Tool registry ─────────────────────────────────────────────────────────────
MAPS_TOOLS = [maps_search, justdial_search, indiamart_search]
