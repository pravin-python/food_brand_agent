"""
tools/mca/mca_tools.py
MCA & Tofler tools for the MCA Company Agent.
Uses requests + BeautifulSoup (async-safe; no sync_playwright).
"""

import requests
from bs4 import BeautifulSoup

MCA_API_URL  = "https://www.mca.gov.in/mcafoportal/findLlpMasterData.do"
TOFLER_URL   = "https://www.tofler.in/search?query="
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

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
#  MCA PORTAL SEARCH  (uses MCA public company search API)
# ─────────────────────────────────────────────────────────────────────────────

def mca_search(company_name: str, brand_name: str = "") -> list[dict]:
    """
    Search MCA portal for Indian registered companies matching EITHER the
    legal company name OR the brand name.  Both queries are run and merged.

    Args:
        company_name: Legal registered company name
        brand_name  : Consumer-facing brand name (optional fallback)

    Returns:
        Deduplicated list of Active company dicts with cin, name, state, status, source
    """
    results: list[dict] = []
    seen_cins: set[str] = set()

    queries = [(company_name, "company_name")]
    if brand_name and brand_name.strip().lower() != company_name.strip().lower():
        queries.append((brand_name, "brand_name"))

    for query, search_term in queries:
        rows = _mca_api_query(query, search_term)
        for r in rows:
            cin = r.get("cin", "")
            if cin and cin not in seen_cins:
                seen_cins.add(cin)
                results.append(r)
            elif not cin:
                results.append(r)

    return results


def _mca_api_query(query: str, search_term: str) -> list[dict]:
    """Query MCA public search API and return Active company rows."""
    results = []
    try:
        # Try MCA v3 company search (JSON endpoint)
        resp = requests.get(
            "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
            params={"companyName": query},
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tr")[1:]  # skip header

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 4:
                status = cols[3] if len(cols) > 3 else ""
                if "active" not in status.lower():
                    continue
                results.append({
                    "cin":         cols[0] if cols else "",
                    "name":        cols[1] if len(cols) > 1 else "",
                    "state":       cols[2] if len(cols) > 2 else "",
                    "status":      status,
                    "address":     "",
                    "city":        "",
                    "type":        "HQ",
                    "source":      "mca",
                    "search_term": search_term,
                })
    except Exception as e:
        results.append({
            "error":       str(e),
            "source":      "mca",
            "search_term": search_term,
        })

    return results


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
        List of Active India-only branch location dicts
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
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple known Tofler card selectors
        cards = (
            soup.select(".company-card") or
            soup.select(".search-result") or
            soup.select(".srp-card")
        )

        for card in cards:
            name_el   = card.select_one(".company-name, h2, .srp-name")
            addr_el   = card.select_one(".address, .srp-addr")
            status_el = card.select_one(".status, .srp-status")

            name    = name_el.get_text(strip=True)   if name_el   else ""
            address = addr_el.get_text(strip=True)   if addr_el   else ""
            status  = status_el.get_text(strip=True) if status_el else "active"

            if status and "active" not in status.lower():
                continue

            state, city = _parse_state_city(address)
            if not state:
                continue  # non-India → skip

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
    """Extract (state, city) from a free-text Indian address string."""
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
