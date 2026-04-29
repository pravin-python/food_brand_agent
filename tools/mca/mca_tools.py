"""
tools/mca/mca_tools.py
MCA & Tofler tools for the MCA Company Agent.

Two separate search axes:
  - company_name : legal registered entity (e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD.")
  - brand_name   : consumer-facing brand   (e.g. "AMUL")

Both are searched independently and merged so no presence data is missed.
"""

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

MCA_SEARCH_URL = "https://www.mca.gov.in/content/mca/global/en/mca/fo-llp-services/company-llp-search.html"
TOFLER_URL     = "https://www.tofler.in/search?query="

# Complete list of Indian states + UTs for address-based filtering
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
#  MCA PORTAL SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def mca_search(company_name: str, brand_name: str = "") -> list[dict]:
    """
    Search MCA portal for Indian registered companies matching EITHER the
    legal company name OR the brand name.  Both queries are run and merged.

    Args:
        company_name: Legal registered company name
                      (e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD.")
        brand_name  : Consumer-facing brand name (e.g. "AMUL").
                      Leave empty to skip brand-name search.

    Returns:
        Deduplicated list of Active company dicts, each with:
          cin, name, state, status, address, city, type, source, search_term
    """
    results: list[dict] = []
    seen_cins: set[str] = set()

    queries = [(company_name, "company_name")]
    if brand_name and brand_name.strip().lower() != company_name.strip().lower():
        queries.append((brand_name, "brand_name"))

    for query, search_term in queries:
        rows = _mca_portal_query(query, search_term)
        for r in rows:
            cin = r.get("cin", "")
            if cin and cin not in seen_cins:
                seen_cins.add(cin)
                results.append(r)
            elif not cin:
                results.append(r)   # keep if no CIN (still useful)

    return results


def _mca_portal_query(query: str, search_term: str) -> list[dict]:
    """Run one MCA portal search and return Active company rows."""
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(MCA_SEARCH_URL, timeout=30_000)
            page.fill('input[placeholder*="Company Name"]', query)
            page.keyboard.press("Enter")
            page.wait_for_selector(".company-result, table", timeout=15_000)

            rows = page.query_selector_all("tr")
            for row in rows:
                cols = row.query_selector_all("td")
                if len(cols) >= 4:
                    results.append({
                        "cin":         cols[0].inner_text().strip(),
                        "name":        cols[1].inner_text().strip(),
                        "state":       cols[2].inner_text().strip(),
                        "status":      cols[3].inner_text().strip(),
                        "address":     "",
                        "city":        "",
                        "type":        "HQ",
                        "source":      "mca",
                        "search_term": search_term,
                    })
            browser.close()
    except Exception as e:
        results.append({
            "error":       str(e),
            "source":      "mca",
            "search_term": search_term,
        })

    return [r for r in results if r.get("status", "").lower() == "active"]


# ─────────────────────────────────────────────────────────────────────────────
#  TOFLER — BRANCH OFFICE SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def get_branch_offices(company_name: str, brand_name: str = "") -> list[dict]:
    """
    Search Tofler for branch offices / subsidiaries of a company.
    Searches by BOTH company name and brand name, merges results.

    Args:
        company_name: Legal registered company name
        brand_name  : Consumer-facing brand name (optional)

    Returns:
        List of Active branch location dicts restricted to India only,
        each tagged with type="Branch" and the search_term that found it.
    """
    results: list[dict] = []
    seen: set[str] = set()

    queries = [(company_name, "company_name")]
    if brand_name and brand_name.strip().lower() != company_name.strip().lower():
        queries.append((brand_name, "brand_name"))

    for query, search_term in queries:
        for record in _tofler_query(query, search_term):
            key = f"{record.get('name','')}|{record.get('city','')}|{record.get('state','')}"
            if key not in seen:
                seen.add(key)
                results.append(record)

    return results


def _tofler_query(query: str, search_term: str) -> list[dict]:
    """Run one Tofler search, return India-only Active branch records."""
    results = []
    try:
        resp = requests.get(
            TOFLER_URL + requests.utils.quote(query),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select(".company-card, .search-result")

        for card in cards:
            name_el   = card.select_one(".company-name")
            addr_el   = card.select_one(".address")
            status_el = card.select_one(".status")

            name    = name_el.get_text(strip=True)   if name_el   else ""
            address = addr_el.get_text(strip=True)   if addr_el   else ""
            status  = status_el.get_text(strip=True) if status_el else ""

            if status.lower() != "active":
                continue

            state, city = _parse_state_city(address)

            # ── India-only filter ──────────────────────────────────
            if not state:
                continue  # no recognised Indian state → skip

            results.append({
                "name":        name,
                "address":     address,
                "state":       state,
                "city":        city,
                "type":        "Branch",
                "source":      "tofler",
                "search_term": search_term,
            })
    except Exception as e:
        results.append({
            "error":       str(e),
            "source":      "tofler",
            "search_term": search_term,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_state_city(address: str) -> tuple[str, str]:
    """
    Extract (state, city) from a free-text Indian address string.
    Returns ("", "") when no Indian state is detected (used as India-only filter).
    """
    state = ""
    for s in INDIAN_STATES:
        if s.lower() in address.lower():
            state = s
            break

    parts = [p.strip() for p in address.split(",")]
    city = parts[-3] if len(parts) >= 3 else (parts[0] if parts else "")
    return state, city


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
MCA_TOOLS = [mca_search, get_branch_offices]
