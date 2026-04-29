"""
tools/mca/mca_tools.py
MCA & Tofler tools for the MCA Company Agent.

Two search axes:
  - company_name : legal registered entity
  - brand_name   : consumer-facing brand (searched as fallback)
"""

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


TOFLER_SEARCH = "https://www.tofler.in/search?query="

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar", "Chandigarh", "Dadra and Nagar Haveli", "Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]


# ─────────────────────────────────────────────────────────────────────────────
#  MCA PORTAL SEARCH  (via data.gov.in open data or MCA21 public search)
# ─────────────────────────────────────────────────────────────────────────────

def mca_search(company_name: str, brand_name: str = "") -> list[dict]:
    """
    Search for Indian registered companies matching the legal company name
    or brand name.  Tries the MCA21 portal via Playwright, then falls back
    to a public Tofler search.

    Args:
        company_name: Legal registered company name.
        brand_name:   Consumer-facing brand name (searched separately).

    Returns:
        Deduplicated list of company dicts with: cin, name, state, status,
        address, city, type, source, search_term.
    """
    results: list[dict] = []
    seen_cins: set[str] = set()

    queries = [(company_name, "company_name")]
    if brand_name and brand_name.strip().lower() != company_name.strip().lower():
        queries.append((brand_name, "brand_name"))

    for query, label in queries:
        rows = _tofler_query_playwright(query, label)
        if not rows:
            rows = _tofler_query_requests(query, label)
        for r in rows:
            cin = r.get("cin", "")
            if cin and cin not in seen_cins:
                seen_cins.add(cin)
                results.append(r)
            elif not cin:
                results.append(r)

    return results


def _tofler_query_playwright(query: str, label: str) -> list[dict]:
    """Playwright-based Tofler company search (handles JS rendering)."""
    if not HAS_PLAYWRIGHT:
        return []
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
            url = TOFLER_SEARCH + requests.utils.quote(query)
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            cards = page.query_selector_all(
                ".company-card, .search-result-item, "
                "[class*='company'], [class*='search-result']"
            )
            for card in cards[:20]:
                name = _pw_text(card, ".company-name, h2, h3, [class*='name']")
                addr = _pw_text(card, ".address, [class*='address'], [class*='city']")
                cin  = _pw_text(card, ".cin, [class*='cin'], [data-cin]")
                stat = _pw_text(card, ".status, [class*='status']")

                if not name:
                    continue

                state, city = _parse_state_city(addr)
                if not state:
                    continue

                results.append({
                    "cin":         cin,
                    "name":        name,
                    "state":       state,
                    "city":        city,
                    "status":      stat or "Active",
                    "address":     addr,
                    "type":        "HQ",
                    "source":      "tofler",
                    "search_term": label,
                })

            browser.close()
    except Exception as exc:
        results.append({"error": str(exc), "source": "tofler", "search_term": label})
    return [r for r in results if r.get("status", "").lower() in ("active", "")]


def _tofler_query_requests(query: str, label: str) -> list[dict]:
    """Requests + BeautifulSoup fallback for Tofler (works if JS not required)."""
    results = []
    try:
        resp = requests.get(
            TOFLER_SEARCH + requests.utils.quote(query),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
                "Accept-Language": "en-IN,en;q=0.9",
            },
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(
            ".company-card, .search-result-item, "
            "[class*='company-result'], [class*='search-result']"
        )
        for card in cards[:20]:
            name_el   = card.select_one("[class*='name'], h2, h3")
            addr_el   = card.select_one("[class*='address'], [class*='city']")
            status_el = card.select_one("[class*='status']")

            name   = name_el.get_text(strip=True)   if name_el   else ""
            addr   = addr_el.get_text(strip=True)   if addr_el   else ""
            status = status_el.get_text(strip=True) if status_el else "Active"

            if not name or status.lower() not in ("active", ""):
                continue

            state, city = _parse_state_city(addr)
            if not state:
                continue

            results.append({
                "cin":         "",
                "name":        name,
                "state":       state,
                "city":        city,
                "status":      status,
                "address":     addr,
                "type":        "HQ",
                "source":      "tofler_requests",
                "search_term": label,
            })
    except Exception as exc:
        results.append({"error": str(exc), "source": "tofler_requests", "search_term": label})
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  BRANCH OFFICE SEARCH  (via Tofler company detail pages)
# ─────────────────────────────────────────────────────────────────────────────

def get_branch_offices(company_name: str, brand_name: str = "") -> list[dict]:
    """
    Find branch offices / subsidiaries of a company via Tofler.

    Args:
        company_name: Legal registered company name.
        brand_name:   Consumer-facing brand name (searched separately).

    Returns:
        Deduplicated list of branch location dicts restricted to India,
        tagged type="Branch".
    """
    results: list[dict] = []
    seen: set[str] = set()

    queries = [(company_name, "company_name")]
    if brand_name and brand_name.strip().lower() != company_name.strip().lower():
        queries.append((brand_name, "brand_name"))

    for query, label in queries:
        for record in _branch_query(query, label):
            key = f"{record.get('name','')}|{record.get('city','')}|{record.get('state','')}"
            if key not in seen:
                seen.add(key)
                results.append(record)

    return results


def _branch_query(query: str, label: str) -> list[dict]:
    """Search Tofler for branch/subsidiary data."""
    if not HAS_PLAYWRIGHT:
        return _branch_query_requests(query, label)
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
            url = TOFLER_SEARCH + requests.utils.quote(query)
            page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Try to click first result and load branch data
            first = page.query_selector("a[href*='/company/']")
            if first:
                href = first.get_attribute("href") or ""
                company_url = f"https://www.tofler.in{href}" if href.startswith("/") else href
                page.goto(company_url, timeout=15_000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                # Look for branch/subsidiary section
                branch_items = page.query_selector_all(
                    "[class*='branch'], [class*='subsidiary'], "
                    "[class*='office'], [class*='location']"
                )
                for item in branch_items[:20]:
                    text = item.inner_text()
                    state, city = _parse_state_city(text)
                    if state:
                        results.append({
                            "name":        query,
                            "address":     text[:200],
                            "state":       state,
                            "city":        city,
                            "type":        "Branch",
                            "source":      "tofler",
                            "search_term": label,
                        })

            browser.close()
    except Exception as exc:
        results.append({"error": str(exc), "source": "tofler", "search_term": label})
    return results


def _branch_query_requests(query: str, label: str) -> list[dict]:
    results = []
    try:
        resp = requests.get(
            TOFLER_SEARCH + requests.utils.quote(query),
            headers={"User-Agent": "Mozilla/5.0 Chrome/120.0"},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select(".company-card, .search-result")[:10]:
            addr_el   = card.select_one(".address, [class*='address']")
            status_el = card.select_one(".status, [class*='status']")
            addr   = addr_el.get_text(strip=True)   if addr_el   else ""
            status = status_el.get_text(strip=True) if status_el else "Active"
            if status.lower() != "active":
                continue
            state, city = _parse_state_city(addr)
            if state:
                results.append({
                    "name":        query,
                    "address":     addr,
                    "state":       state,
                    "city":        city,
                    "type":        "Branch",
                    "source":      "tofler_requests",
                    "search_term": label,
                })
    except Exception as exc:
        results.append({"error": str(exc), "source": "tofler_requests", "search_term": label})
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_state_city(address: str) -> tuple[str, str]:
    """Extract (state, city) from a free-text Indian address."""
    state = ""
    for s in INDIAN_STATES:
        if s.lower() in address.lower():
            state = s
            break
    parts = [p.strip() for p in address.split(",") if p.strip()]
    city = parts[-3] if len(parts) >= 3 else (parts[0] if parts else "")
    return state, city


def _pw_text(element, selector: str) -> str:
    """Query a selector on a Playwright element and return inner text."""
    try:
        el = element.query_selector(selector)
        return el.inner_text().strip() if el else ""
    except Exception:
        return ""


# ── Tool registry ─────────────────────────────────────────────────────────────
MCA_TOOLS = [mca_search, get_branch_offices]
