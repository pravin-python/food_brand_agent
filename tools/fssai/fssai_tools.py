"""
tools/fssai/fssai_tools.py
FSSAI FOSCOS portal scraper tools for the FSSAI Scraper Agent.

The FOSCOS portal renders via JavaScript; Playwright handles the full page load.
"""

import time
from bs4 import BeautifulSoup

# Playwright is optional — degrade gracefully if missing
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


FOSCOS_BASE  = "https://foscos.fssai.gov.in"
FOSCOS_SEARCH = f"{FOSCOS_BASE}/index.php/searchlicenseregistration"


def fssai_search(brand_name: str, max_pages: int = 5) -> str:
    """
    Search FSSAI FOSCOS portal for food-business licenses by brand/business name.

    Args:
        brand_name: Consumer-facing brand or business name to search.
        max_pages:  Maximum result pages to collect (default 5).

    Returns:
        Raw HTML of all collected result pages joined by newlines,
        or a string starting with "ERROR:" on failure.
    """
    if not HAS_PLAYWRIGHT:
        return "ERROR:playwright not installed. Run: pip install playwright && playwright install chromium"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            page = ctx.new_page()

            # ── Open search page ─────────────────────────────────────────────
            page.goto(FOSCOS_SEARCH, timeout=30_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # ── Try to fill the business-name input ─────────────────────────
            # FOSCOS uses several possible selectors across page versions
            input_selectors = [
                'input[name="business_name"]',
                'input[placeholder*="Business"]',
                'input[placeholder*="business"]',
                'input[id*="business"]',
                '#business_name',
            ]
            filled = False
            for sel in input_selectors:
                try:
                    page.fill(sel, brand_name, timeout=3000)
                    filled = True
                    break
                except Exception:
                    continue

            if not filled:
                html_snapshot = page.content()
                browser.close()
                return f"ERROR:could not locate business-name input on FOSCOS page. Snapshot length={len(html_snapshot)}"

            # ── Submit form ──────────────────────────────────────────────────
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:text("Search")',
                'button:text("search")',
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    page.click(sel, timeout=3000)
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                page.keyboard.press("Enter")

            # ── Wait for results ─────────────────────────────────────────────
            try:
                page.wait_for_selector("table, .no-records, .no-data, #noRecords", timeout=20_000)
            except PwTimeout:
                browser.close()
                return "ERROR:timeout waiting for FOSCOS search results"

            all_html = []
            for page_num in range(max_pages):
                all_html.append(page.content())

                # Check for a "Next" pagination link
                next_btn = None
                for next_sel in [
                    "a:text('Next')",
                    "a:text('next')",
                    "li.next a",
                    ".pagination .next a",
                    "a[aria-label='Next']",
                ]:
                    try:
                        btn = page.query_selector(next_sel)
                        if btn and btn.is_visible():
                            next_btn = btn
                            break
                    except Exception:
                        continue

                if not next_btn:
                    break

                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=10_000)
                page.wait_for_timeout(500)

            browser.close()
            return "\n".join(all_html)

    except Exception as exc:
        return f"ERROR:{exc}"


def fssai_parse(html: str) -> list[dict]:
    """
    Parse FSSAI FOSCOS results HTML into structured license records.

    Args:
        html: Raw HTML string returned by fssai_search().

    Returns:
        List of dicts, each representing one license entry with keys:
        license_no, business_name, license_type, state, district, city,
        address, source.
        Returns [] if html is empty or indicates an error.
    """
    if not html or html.startswith("ERROR:"):
        return []

    results: list[dict] = []
    seen: set[str] = set()

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detect header row to know column layout
        header_cells = rows[0].find_all(["th", "td"])
        headers = [h.get_text(strip=True).lower() for h in header_cells]

        col = {
            "license_no":    _find_col(headers, ["license no", "lic no", "registration no", "fssai no"]),
            "business_name": _find_col(headers, ["business name", "firm name", "company"]),
            "license_type":  _find_col(headers, ["license type", "type", "category"]),
            "state":         _find_col(headers, ["state"]),
            "district":      _find_col(headers, ["district", "dist"]),
            "address":       _find_col(headers, ["address"]),
        }

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3:
                continue

            record = {
                "license_no":    _cell(cells, col["license_no"]),
                "business_name": _cell(cells, col["business_name"]),
                "license_type":  _cell(cells, col["license_type"]),
                "state":         _cell(cells, col["state"]),
                "district":      _cell(cells, col["district"]),
                "address":       _cell(cells, col["address"]),
                "source":        "fssai",
            }
            record["city"] = _extract_city(record["address"] or record["district"])

            key = f"{record['license_no']}|{record['business_name']}|{record['state']}"
            if key not in seen and any(record[k] for k in ("license_no", "business_name", "state")):
                seen.add(key)
                results.append(record)

    # Fallback: scan div/span-based card layouts used by newer FOSCOS versions
    if not results:
        cards = soup.select(".license-card, .result-card, [class*='license'], [class*='result']")
        for card in cards:
            text = card.get_text(separator=" ", strip=True)
            if not text:
                continue
            results.append({
                "license_no":    "",
                "business_name": text[:120],
                "license_type":  "",
                "state":         _guess_state(text),
                "district":      "",
                "address":       text,
                "city":          _extract_city(text),
                "source":        "fssai",
            })

    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry", "Chandigarh",
    "Andaman and Nicobar", "Dadra and Nagar Haveli", "Daman and Diu", "Lakshadweep",
]


def _find_col(headers: list[str], candidates: list[str]) -> int | None:
    for i, h in enumerate(headers):
        for c in candidates:
            if c in h:
                return i
    return None


def _cell(cells: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx]


def _extract_city(text: str) -> str:
    if not text:
        return ""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def _guess_state(text: str) -> str:
    text_lower = text.lower()
    for state in INDIAN_STATES:
        if state.lower() in text_lower:
            return state
    return ""


# ── Tool registry ─────────────────────────────────────────────────────────────
FSSAI_TOOLS = [fssai_search, fssai_parse]
