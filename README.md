# 🍱 Food Brand Intelligence System — India

A **multi-agent AI pipeline** to research any Indian food brand's complete national presence — government licenses, corporate registrations, e-commerce availability, and distributor/dealer network — all in one automated run.

---

## 📁 Project Structure

```
food_brand_agent/
├── main.py                        # ← Root entry point
├── pyproject.toml                 # Package config & dependencies
├── requirements.txt               # pip install list
├── .env                           # API keys (never commit this)
├── .gitignore
│
├── agents/
│   ├── __init__.py
│   └── main_agent.py              # Orchestrator + all sub-agent definitions
│
├── tools/
│   ├── __init__.py
│   ├── fssai/
│   │   ├── __init__.py
│   │   └── fssai_tools.py         # FSSAI FOSCOS portal scraper
│   ├── mca/
│   │   ├── __init__.py
│   │   └── mca_tools.py           # MCA + Tofler company search
│   ├── ecommerce/
│   │   ├── __init__.py
│   │   └── ecomm_tools.py         # Swiggy / Blinkit / Amazon checker
│   ├── maps/
│   │   ├── __init__.py
│   │   └── maps_tools.py          # Google Maps / Justdial / IndiaMart
│   └── report/
│       ├── __init__.py
│       └── report_tools.py        # Excel + heatmap report builder
│
├── skills/
│   ├── main/           SKILL.md   # Orchestrator skill
│   ├── fssai-scraper/  SKILL.md
│   ├── mca-company/    SKILL.md
│   ├── ecommerce/      SKILL.md
│   ├── web-maps/       SKILL.md
│   └── report-builder/ SKILL.md
│
└── output/                        # Generated Excel reports (git-ignored)
```

---

## 🚀 Quick Start

### 1. Create & activate virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Set API keys
Edit `.env`:
```
GEMINI_API_KEY=your_key_here
GOOGLE_MAPS_API_KEY=your_key_here   # optional
SERP_API_KEY=your_key_here          # optional
```

### 4. Run the agent
```bash
# From project root:
python main.py --brand "Haldirams"
python main.py --brand "Amul" --model "google_genai:gemini-2.0-flash"
```

---

## 🤖 Agents

| Agent | Data Source | Output |
|-------|------------|--------|
| `fssai_scraper` | FSSAI FOSCOS portal | Government food licenses by state/city |
| `mca_company` | MCA + Tofler | Company registrations & branches |
| `ecommerce_checker` | Swiggy / Blinkit / Amazon | Online availability in 20 cities |
| `web_maps` | Google Maps / Justdial / IndiaMart | Distributors & dealers |
| `report_builder` | All above | Excel report + heatmap JSON |

---

## 📊 Output

A multi-sheet Excel file is saved to `output/<brand>.xlsx`:
- **Summary** — brand overview, confidence score
- **State Presence** — color-coded state-wise breakdown
- **FSSAI Licenses** — raw government license data
- **E-commerce** — city × platform availability matrix
- **Distributors** — dealer locations with source tags

---

## ⚙️ Requirements

- Python **≥ 3.11**
- Playwright Chromium (installed via `playwright install chromium`)
- Optional: `SERP_API_KEY` for accurate Google Maps results
