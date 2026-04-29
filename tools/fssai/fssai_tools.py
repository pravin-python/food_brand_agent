"""
tools/fssai/fssai_tools.py
FSSAI FOSCOS portal scraper tools for the FSSAI Scraper Agent.
Uses requests + BeautifulSoup (async-safe; no sync_playwright in async context).
"""

import time
import requests
from bs4 import BeautifulSoup
from typing import Optional


FSSAI_SEARCH_URL = "https://foscos.fssai.gov.in/index.php/licensee-search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://foscos.fssai.gov.in/",
}


def fssai_search(brand_name: str, max_retries: int = 3) -> str:
    """
    Search FSSAI FOSCOS portal for a brand name using HTTP POST.
    Returns raw HTML of results table.

    Args:
        brand_name: Name of food brand to search
        max_retries: Number of retries on failure

    Returns:
        HTML string of results table, or error string on failure
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    for attempt in range(max_retries):
        try:
            # First GET to get any CSRF token / session cookie
            session.get(FSSAI_SEARCH_URL, timeout=20)

            # POST the search form
            payload = {
                "business_name": brand_name,
                "state":         "",
                "district":      "",
                "license_type":  "",
                "submit":        "Search",
            }
            resp = session.post(FSSAI_SEARCH_URL, data=payload, timeout=20)
            resp.raise_for_status()
            return resp.text

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                return f"ERROR:{str(e)}"

    return ""


def fssai_parse(html: str) -> list[dict]:
    """
    Parse FSSAI results HTML into structured list of license records.

    Args:
        html: Raw HTML from fssai_search()

    Returns:
        List of dicts with license details
    """
    if not html or html.startswith("ERROR:"):
        return []

    results = []
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 6:
                results.append({
                    "license_no":     cols[0] if len(cols) > 0 else "",
                    "business_name":  cols[1] if len(cols) > 1 else "",
                    "license_type":   cols[2] if len(cols) > 2 else "",
                    "state":          cols[3] if len(cols) > 3 else "",
                    "district":       cols[4] if len(cols) > 4 else "",
                    "address":        cols[5] if len(cols) > 5 else "",
                    "city":           _extract_city(cols[5] if len(cols) > 5 else ""),
                    "source":         "fssai",
                })

    return results


def _extract_city(address: str) -> str:
    """Best-effort city extraction from address string."""
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return parts[-3]
    elif len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


# ---- Register tools list for DeepAgent ----
FSSAI_TOOLS = [fssai_search, fssai_parse]
