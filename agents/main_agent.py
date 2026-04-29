"""
agents/main_agent.py

Food Brand Intelligence System — India
Multi-agent system using DeepAgent framework.

Two separate identifiers are accepted:
  --company   Legal registered company name
              e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD."
  --brand     Consumer-facing brand name
              e.g. "AMUL"

Usage (from project root):
    python main.py --company "GUJARAT CO-OP MILK MARKETING FEDERATION LTD." --brand "AMUL"
    python main.py --company "Haldiram Foods International Pvt Ltd" --brand "Haldirams"
    python main.py --brand "Parle" --model "google_genai:gemini-2.0-flash"
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # loads .env from project root

from deepagents import create_deep_agent          # pip install deepagents

# ── Import all tools ──────────────────────────────────────────────────────────
from tools.fssai.fssai_tools     import FSSAI_TOOLS
from tools.mca.mca_tools         import MCA_TOOLS
from tools.ecommerce.ecomm_tools import ECOMM_TOOLS
from tools.maps.maps_tools       import MAPS_TOOLS
from tools.report.report_tools   import REPORT_TOOLS


# ═══════════════════════════════════════════════════════════════════════════════
#  SUB-AGENT DEFINITIONS
#
#  KEY DISTINCTION:
#    company_name → used for MCA / legal / corporate registration searches
#    brand_name   → used for FSSAI (food licenses), e-commerce, maps searches
#
#  The orchestrator passes BOTH to every agent so each agent uses the right one.
# ═══════════════════════════════════════════════════════════════════════════════

fssai_agent = {
    "name": "fssai_scraper",
    "description": (
        "Scrapes FSSAI FOSCOS portal to find all registered food licenses "
        "for a brand across Indian states and cities."
    ),
    "system_prompt": """
You are the FSSAI Scraper Agent. You find food-business licenses on the FSSAI FOSCOS
government portal.  Food licenses are registered under the BRAND name (consumer-facing),
not the legal company name.

Steps:
1. Call fssai_search(brand_name) using the BRAND NAME from the user query
2. Call fssai_parse(html) to extract structured license records
3. Return the list of records — never hallucinate

If nothing is found, return [].
Always read your skill file first: ./skills/fssai-scraper/SKILL.md
""",
    "tools":  FSSAI_TOOLS,
    "skills": ["./skills/fssai-scraper/"],
}

mca_agent = {
    "name": "mca_company",
    "description": (
        "Searches MCA portal (by legal company name) and Tofler to find "
        "all registered HQ, branch offices, and subsidiaries of a company "
        "across India — keyed off the LEGAL company name."
    ),
    "system_prompt": """
You are the MCA Company Agent. You find company registration data from MCA and Tofler.

IMPORTANT — use the right search term:
  - mca_search(company_name, brand_name)   → searches MCA with BOTH legal name AND brand name
  - get_branch_offices(company_name, brand_name) → finds branch offices via Tofler using BOTH names

Steps:
1. Extract company_name  (legal entity, e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD.")
   and brand_name (consumer name, e.g. "AMUL") from the query
2. Call mca_search(company_name, brand_name)
3. Call get_branch_offices(company_name, brand_name)
4. Combine HQ + Branch records; deduplicate by (name, city)
5. Return only Active, India-based locations

Only return Active companies. Read skill: ./skills/mca-company/SKILL.md
""",
    "tools":  MCA_TOOLS,
    "skills": ["./skills/mca-company/"],
}

ecommerce_agent = {
    "name": "ecommerce_checker",
    "description": (
        "Checks brand product availability on Swiggy Instamart, Blinkit, "
        "and Amazon India across 20 major Indian cities."
    ),
    "system_prompt": """
You are the E-commerce Agent. You check if a food brand is available online in India.

Use the BRAND NAME (consumer-facing, e.g. "AMUL") for all searches — not the company name.

Steps:
1. Get city list: get_cities_list()
2. For each city, check all 3 platforms: ecomm_check(platform, city, brand_name)
   - platforms: "swiggy", "blinkit", "amazon"
3. Build city_summary: {city: {available_on: [...], score: N/3}}
4. Return platform_results + city_summary

Check all 3 platforms for every city. Read skill: ./skills/ecommerce/SKILL.md
""",
    "tools":  ECOMM_TOOLS,
    "skills": ["./skills/ecommerce/"],
}

maps_agent = {
    "name": "web_maps",
    "description": (
        "Finds food brand distributors and dealers across Indian cities "
        "using Google Maps, Justdial, and IndiaMart."
    ),
    "system_prompt": """
You are the Web & Maps Agent. You find distributors and retail presence across India.

Use the BRAND NAME (e.g. "AMUL") for all searches.

Steps:
1. For each major city, call maps_search("{brand_name} distributor", city)
2. Call justdial_search(brand_name, city) for key cities
3. Call indiamart_search(brand_name) for wholesale distributors
4. Cross-verify: same city appears in 2+ sources → set verified=True
5. Return distributors list + state_coverage summary

All results must be India-only. Read skill: ./skills/web-maps/SKILL.md
""",
    "tools":  MAPS_TOOLS,
    "skills": ["./skills/web-maps/"],
}

report_agent = {
    "name": "report_builder",
    "description": (
        "Takes all collected data and generates a final Excel report "
        "with multiple sheets and India heatmap data."
    ),
    "system_prompt": """
You are the Report Builder Agent. You create the final output Excel + heatmap.

Steps:
1. Receive merged data dict from orchestrator
2. Call build_excel(data, brand_name) to create the Excel file
3. Call build_heatmap(state_scores) to generate heatmap JSON
4. Return excel_path + heatmap_data + summary stats

The report must include both company-level data (MCA/branches) and
brand-level data (FSSAI licenses, e-commerce, distributors).
Read skill: ./skills/report-builder/SKILL.md
""",
    "tools":  REPORT_TOOLS,
    "skills": ["./skills/report-builder/"],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR AGENT
# ═══════════════════════════════════════════════════════════════════════════════

ORCHESTRATOR_PROMPT = """
You are the Master Orchestrator of the Food Brand Intelligence System for India.

You receive TWO identifiers for every query:
  - COMPANY NAME : legal registered entity (e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD.")
  - BRAND NAME   : consumer-facing brand   (e.g. "AMUL")

Both may be the same (e.g. a brand with no separate legal entity name provided).
Always pass BOTH identifiers to every sub-agent so each uses the right one.

Your workflow:
1. Parse company_name and brand_name from user input
2. Dispatch ALL 4 data agents in parallel, passing both names clearly:
   - fssai_scraper     → searches by BRAND NAME → government food license data
   - mca_company       → searches by COMPANY NAME (+ brand fallback) → corporate data
   - ecommerce_checker → searches by BRAND NAME → online availability data
   - web_maps          → searches by BRAND NAME → distributor & dealer data
3. Collect all results; if an agent fails, mark source as "unavailable" and continue
4. Merge into a UNIFIED India presence dict:
   {
     "company":  "<company_name>",
     "brand":    "<brand_name>",
     "states":   ["Maharashtra", "Gujarat", ...],
     "cities":   {"Maharashtra": ["Mumbai", "Pune"], ...},
     "sources":  {
       "fssai":      [...],
       "mca":        [...],      ← includes both HQ and all branch offices
       "ecommerce":  {...},
       "maps":       [...]
     },
     "confidence": 0.0–1.0
   }
5. Calculate confidence = (sources that returned data) / 4
6. Dispatch report_builder with the merged data
7. Return the full summary to the user

All results must be INDIA ONLY — discard any foreign locations.
Always read your skill: ./skills/main/SKILL.md
"""


def build_agent(model: str):
    """Build and return the complete multi-agent system."""
    return create_deep_agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        skills=["./skills/main/"],
        subagents=[
            fssai_agent,
            mca_agent,
            ecommerce_agent,
            maps_agent,
            report_agent,
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def run(company: str, brand: str, model: str):
    agent = build_agent(model)

    print(f"\n{'='*60}")
    print(f"  🏭  Company : {company}")
    print(f"  🍱  Brand   : {brand}")
    print(f"  🤖  Model   : {model}")
    print(f"{'='*60}\n")

    query = (
        f"Research the India-wide presence (all states and cities) for:\n"
        f"  Company Name : {company}\n"
        f"  Brand Name   : {brand}\n\n"
        f"Use the company name for MCA/corporate searches and "
        f"the brand name for FSSAI, e-commerce, and maps searches. "
        f"All results must be India only."
    )

    result = await agent.run(query)

    print("\n✅  Research Complete!")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Food Brand India Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py --company "GUJARAT CO-OP MILK MARKETING FEDERATION LTD." --brand "AMUL"\n'
            '  python main.py --company "Haldiram Foods International Pvt Ltd" --brand "Haldirams"\n'
            '  python main.py --brand "Parle-G"   # company defaults to brand if omitted\n'
        ),
    )
    parser.add_argument(
        "--company",
        default="",
        help="Legal registered company name (e.g. 'GUJARAT CO-OP MILK MARKETING FEDERATION LTD.')",
    )
    parser.add_argument(
        "--brand",
        required=True,
        help="Consumer-facing brand name (e.g. 'AMUL')",
    )
    parser.add_argument(
        "--model",
        default="google_genai:gemini-2.0-flash",
        help="LLM model to use (default: google_genai:gemini-2.0-flash)",
    )
    args = parser.parse_args()

    # If company not given, fall back to brand name
    company = args.company.strip() if args.company.strip() else args.brand.strip()

    asyncio.run(run(company=company, brand=args.brand.strip(), model=args.model))


if __name__ == "__main__":
    main()
