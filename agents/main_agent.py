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

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from langchain_core.messages import AIMessage

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
3. Return the list of records as JSON — never hallucinate

If nothing is found, return {"records": [], "source": "fssai", "status": "no_results"}.
If a tool errors, return {"records": [], "source": "fssai", "status": "error", "error": "<msg>"}.
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

Steps:
1. Call mca_search(company_name, brand_name) — searches MCA with BOTH identifiers
2. Call get_branch_offices(company_name, brand_name) — finds branches via Tofler
3. Combine and deduplicate records by (name, city)
4. Return only Active, India-based locations as JSON

If tools fail, return {"records": [], "source": "mca", "status": "error", "error": "<msg>"}.
Only return Active companies.
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

Use the BRAND NAME (consumer-facing, e.g. "AMUL") for all searches.

Steps:
1. Get city list: get_cities_list()
2. For each city, check all 3 platforms: ecomm_check(platform, city, brand_name)
   - platforms: "swiggy", "blinkit", "amazon"
3. Build city_summary: {city: {available_on: [...], score: N/3}}
4. Return {"platform_results": [...], "city_summary": {...}, "source": "ecommerce"}

If a platform check errors, record it as not found for that city/platform and continue.
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
5. Return {"distributors": [...], "state_coverage": {...}, "source": "maps"}

If a search errors, skip that city/source and continue with others.
All results must be India-only.
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
4. Return {"excel_path": "...", "heatmap": {...}, "status": "success"}

The report must include both company-level data (MCA/branches) and
brand-level data (FSSAI licenses, e-commerce, distributors).
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
2. Dispatch ALL 4 data agents using the task tool, passing both names clearly:
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
       "mca":        [...],
       "ecommerce":  {...},
       "maps":       [...]
     },
     "confidence": 0.0-1.0
   }
5. Calculate confidence = (sources that returned data) / 4
6. Call the report_builder agent with the merged data
7. Return the full summary as plain text to the user

All results must be INDIA ONLY — discard any foreign locations.
"""


def build_agent(model: str):
    """Build and return the complete multi-agent system."""
    backend = FilesystemBackend(root_dir=Path.cwd())
    return create_deep_agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=backend,
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
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_text(msg: AIMessage) -> str:
    """Extract plain text from an AIMessage regardless of content format."""
    raw = msg.content
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    return ""


def _token_summary(messages: list) -> tuple[int, int, int]:
    """Sum token usage across all messages."""
    total_in = total_out = total = 0
    for msg in messages:
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            m = msg.usage_metadata
            total_in  += m.get("input_tokens",  0)
            total_out += m.get("output_tokens", 0)
            total     += m.get("total_tokens",  0)
    return total, total_in, total_out


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def run(company: str, brand: str, model: str):
    agent = build_agent(model)

    print(f"\n{'='*60}")
    print(f"  Company : {company}")
    print(f"  Brand   : {brand}")
    print(f"  Model   : {model}")
    print(f"{'='*60}\n")

    query = (
        f"Research the India-wide presence (all states and cities) for:\n"
        f"  Company Name : {company}\n"
        f"  Brand Name   : {brand}\n\n"
        f"Use the company name for MCA/corporate searches and "
        f"the brand name for FSSAI, e-commerce, and maps searches. "
        f"All results must be India only."
    )

    try:
        state = await agent.ainvoke({"messages": [("user", query)]})
    except Exception as exc:
        print(f"\n[ERROR] Agent invocation failed: {exc}")
        raise

    messages = state.get("messages", [])

    # ── Debug: print message trace ───────────────────────────────────────────
    print("\n--- MESSAGE TRACE ---")
    for i, msg in enumerate(messages):
        preview = str(msg.content)[:200]
        tc_count = len(getattr(msg, "tool_calls", []))
        tag = f" [{tc_count} tool_calls]" if tc_count else ""
        print(f"  [{i}] {type(msg).__name__}{tag}: {preview!r}")
    print("---------------------")

    # ── Extract last meaningful AIMessage text ───────────────────────────────
    result = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg)
            if text:
                result = text
                break

    # ── Token usage ──────────────────────────────────────────────────────────
    total, total_in, total_out = _token_summary(messages)
    token_summary = f"Total: {total} (Input: {total_in}, Output: {total_out})"

    print("\n✅  Research Complete!")
    print("\n--- OUTPUT ---")
    print(result if result else "[No text output — check MESSAGE TRACE above]")
    print("\n--- TOKEN USAGE ---")
    print(token_summary)

    # ── Log to file ──────────────────────────────────────────────────────────
    log_path = Path("agent_execution.log")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"Company: {company} | Brand: {brand} | Model: {model}\n")
        f.write(f"Tokens: {token_summary}\n")
        f.write(f"Output:\n{result}\n")
        f.write(f"{'='*50}\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Food Brand India Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py --company "GUJARAT CO-OP MILK MARKETING FEDERATION LTD." --brand "AMUL"\n'
            '  python main.py --company "Haldiram Foods International Pvt Ltd" --brand "Haldirams"\n'
            '  python main.py --brand "Parle-G"\n'
        ),
    )
    parser.add_argument(
        "--company",
        default="",
        help="Legal registered company name",
    )
    parser.add_argument(
        "--brand",
        required=True,
        help="Consumer-facing brand name (e.g. 'AMUL')",
    )
    parser.add_argument(
        "--model",
        default="google_genai:gemini-2.0-flash",
        help="LLM model (default: google_genai:gemini-2.0-flash)",
    )
    args = parser.parse_args()

    company = args.company.strip() if args.company.strip() else args.brand.strip()
    asyncio.run(run(company=company, brand=args.brand.strip(), model=args.model))


if __name__ == "__main__":
    main()
