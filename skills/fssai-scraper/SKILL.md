# FSSAI Scraper Agent — Skill

## Agent Identity
**Name:** `fssai_scraper`
**Purpose:** FSSAI FOSCOS government portal se food brand ki state/city-wise license data nikalna.
**Tools Available:** `fssai_search()`, `fssai_parse()`

---

## Step-by-Step Workflow

```
Step 1 → fssai_search(brand_name)
           ↓ returns raw HTML pages
Step 2 → fssai_parse(html)
           ↓ returns structured list
Step 3 → Return clean JSON to Orchestrator
```

### Step 1: Search
```python
html = fssai_search(brand_name="Haldirams")
# URL: https://foscos.fssai.gov.in/
# Auto-paginates all result pages
# Returns: raw HTML string (multi-page)
```

### Step 2: Parse
```python
records = fssai_parse(html=html)
# Extracts table rows from HTML
# Returns: list of license dicts
```

### Step 3: Return
Return parsed records directly to Orchestrator. Do NOT filter or modify.

---

## Output Schema

```json
[
  {
    "license_no": "10016011000001",
    "business_name": "Haldiram Foods Pvt Ltd",
    "license_type": "Central",
    "state": "Maharashtra",
    "district": "Mumbai",
    "city": "Mumbai",
    "address": "Plot 12, MIDC, Andheri East, Mumbai - 400093",
    "source": "fssai"
  }
]
```

---

## Error Handling Rules

| Situation | Action |
|---|---|
| CAPTCHA detected | Wait 5 sec, retry once |
| Empty results | Return [] — never guess data |
| Partial results | Return what you have + add "partial": true |
| Tool crash | Return {"error": "fssai_unavailable", "records": []} |
| Brand name variants | Try "Haldiram" AND "Haldirams" if first returns 0 |

---

## Rules

- NEVER make up license numbers or addresses
- NEVER skip pagination — collect ALL pages
- Deduplicate by license_no if same entry appears twice
- State names must be full: "Maharashtra" not "MH"
- Always include "source": "fssai" in every record

---

## Return Format to Orchestrator

```python
return {
    "agent": "fssai_scraper",
    "brand": brand_name,
    "total_found": len(records),
    "records": records,
    "partial": False
}
```
