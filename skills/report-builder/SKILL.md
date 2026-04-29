# Report Builder Agent — Skill

## Agent Identity
**Name:** `report_builder`
**Purpose:** Saare agents ka data leke final Excel report aur India heatmap banana.
**Tools Available:** `build_excel()`, `build_heatmap()`

---

## Step-by-Step Workflow

```
Step 1 → Receive merged_data dict from Orchestrator
Step 2 → build_excel(merged_data, brand_name)
           ↓ creates .xlsx with 5 sheets
Step 3 → build_heatmap(state_scores)
           ↓ returns color-coded state data
Step 4 → Return final paths + summary to Orchestrator
```

### Step 1: Receive Data
```python
# Orchestrator sends merged_data with:
merged_data = {
    "brand": "Haldirams",
    "confidence": 0.85,
    "fssai_data": [...],          # from fssai_scraper
    "mca_data": {...},            # from mca_company
    "ecommerce_data": {...},      # from ecommerce_checker
    "maps_data": {...},           # from web_maps
    "states_summary": {...},      # merged state presence
    "summary": {...}              # stats
}
```

### Step 2: Build Excel
```python
result = build_excel(
    data=merged_data,
    filename="Haldirams_India_Report"
)
# Creates: ./output/Haldirams_India_Report.xlsx
# Sheets: Summary | State Presence | FSSAI | E-commerce | Distributors
```

### Step 3: Build Heatmap
```python
# First prepare state scores from merged data:
state_scores = {
    "Maharashtra": 0.95,   # high confidence
    "Delhi": 0.80,
    "Gujarat": 0.70,
    "Bihar": 0.20,         # low confidence
    "Arunachal Pradesh": 0.0  # not found
}
heatmap = build_heatmap(state_scores)
```

---

## Excel Sheet Structure

| Sheet | Contents |
|---|---|
| `Summary` | Brand name, total states, cities, confidence, strongest state |
| `State Presence` | State × Sources × Confidence — color coded |
| `FSSAI Licenses` | All raw FSSAI license records |
| `E-commerce` | City × Platform matrix (Swiggy/Blinkit/Amazon) |
| `Distributors` | All distributor locations from Maps agent |

### Color Coding in "State Presence" Sheet
- Green (confidence ≥ 70%): Strong presence
- Amber (confidence 40–69%): Medium presence  
- Red (confidence < 40%): Weak presence

---

## Output Schema

```json
{
  "agent": "report_builder",
  "brand": "Haldirams",
  "excel_path": "./output/Haldirams_India_Report.xlsx",
  "heatmap_data": {
    "Maharashtra": {"score": 0.95, "intensity": "Strong",  "color": "#1D9E75"},
    "Delhi":       {"score": 0.80, "intensity": "Strong",  "color": "#1D9E75"},
    "Bihar":       {"score": 0.20, "intensity": "Weak",    "color": "#E24B4A"},
    "Mizoram":     {"score": 0.0,  "intensity": "Not found","color": "#D3D1C7"}
  },
  "top_states": ["Maharashtra", "Delhi", "Gujarat", "Karnataka", "Rajasthan"],
  "summary": {
    "total_states": 22,
    "total_cities": 67,
    "strongest_state": "Maharashtra",
    "confidence": 0.85
  },
  "status": "success"
}
```

---

## State Score Calculation

```
score = (sources confirming this state) / (total sources used)

Example — Maharashtra found in:
  fssai    ✓  (+0.25)
  mca      ✓  (+0.25)
  ecommerce ✓  (+0.25)
  maps     ✓  (+0.25)
  ──────────────────
  score = 1.0 (Strong)

Example — Bihar found in:
  fssai    ✗
  mca      ✗
  ecommerce ✓  (+0.25)
  maps     ✗
  ──────────────────
  score = 0.25 (Weak)
```

---

## Error Handling Rules

| Situation | Action |
|---|---|
| openpyxl not installed | Return error message with install command |
| Output folder missing | Create it automatically before writing |
| Empty data from one source | Leave that sheet empty, note in Summary |
| Filename has special chars | Sanitize: remove `/`, `\`, `:`, `*`, `?` |

---

## Rules

- Always create `./output/` folder if it does not exist
- Filename format: `{BrandName}_India_Report.xlsx` — no spaces, use underscore
- All 5 sheets must be created even if some are empty
- Confidence shown as percentage: 0.85 → "85%"
- Top states = top 5 by score
