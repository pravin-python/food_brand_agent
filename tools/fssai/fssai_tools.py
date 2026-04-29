"""
tools/fssai/fssai_tools.py
FSSAI FOSCOS portal scraper tools for the FSSAI Scraper Agent
"""

import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from typing import Optional


FSSAI_URL = "https://foscos.fssai.gov.in/index.php/licensee-search"


def fssai_search(brand_name: str, max_retries: int = 2) -> str:
    """
    Search FSSAI FOSCOS portal for a brand name.
    Returns raw HTML of results table.

    Args:
        brand_name: Name of food brand to search
        max_retries: Number of retries on failure

    Returns:
        HTML string of results table, or empty string if not found
    """
    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(FSSAI_URL, timeout=30000)

                # Fill search form
                page.fill('input[name="business_name"]', brand_name)
                page.click('button[type="submit"]')
                page.wait_for_selector("table", timeout=15000)

                # Collect all pages
                all_html = []
                while True:
                    all_html.append(page.content())
                    next_btn = page.query_selector("a:text('Next')")
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_load_state("networkidle")

                browser.close()
                return "\n".join(all_html)

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)
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
    # City is usually 2nd or 3rd last part
    if len(parts) >= 3:
        return parts[-3]
    elif len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


# ---- Register tools list for DeepAgent ----
FSSAI_TOOLS = [fssai_search, fssai_parse]
