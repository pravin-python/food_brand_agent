"""
agents/main_agent.py

Food Brand Intelligence System — India
Multi-agent system using DeepAgent framework.

Two identifiers per query:
  --company   Legal registered company name
              e.g. "GUJARAT CO-OP MILK MARKETING FEDERATION LTD."
  --brand     Consumer-facing brand name
              e.g. "AMUL"

Usage (from project root):
    python main.py --company "GUJARAT CO-OP MILK MARKETING FEDERATION LTD." --brand "AMUL"
    python main.py --company "Haldiram Foods International Pvt Ltd" --brand "Haldirams"
    python main.py --brand "Parle"
"""

import argparse
import asyncio
from langchain_core.messages import AIMessage, HumanMessage
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # must run BEFORE any tools are imported

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

# ── Import all tools AFTER dotenv load ───────────────────────────────────────
from tools.fssai.fssai_tools     import FSSAI_TOOLS
from tools.mca.mca_tools         import MCA_TOOLS
from tools.ecommerce.ecomm_tools import ECOMM_TOOLS
from tools.maps.maps_tools       import MAPS_TOOLS
from tools.report.report_tools   import REPORT_TOOLS


# ═══════════════════════════════════════════════════════════════════════════════
#  SUB-AGENT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

fssai_agent = {
    "name": "fssai_scraper",
    "description": "Finds FSSAI food-business licenses for a brand across Indian states/cities.",
    "system_prompt": (
        "You are the FSSAI Scraper Agent. Search the FSSAI FOSCOS portal using the BRAND NAME.\n"
        "1. Call fssai_search(brand_name) to get raw HTML.\n"
        "2. Call fssai_parse(html) to extract license records.\n"
        "3. Return the list as-is. Never hallucinate. Return [] if nothing found."
    ),
    "tools":  FSSAI_TOOLS,
    # NOTE: no 'skills' — skill files add thousands of tokens and slow the model
}

mca_agent = {
    "name": "mca_company",
    "description": (
        "Finds registered company HQ + branch offices via MCA and Tofler "
        "using both the legal company name and the brand name."
    ),
    "system_prompt": (
        "You are the MCA Company Agent. Search using BOTH company name and brand name.\n"
        "1. Call mca_search(company_name, brand_name) — MCA portal.\n"
        "2. Call get_branch_offices(company_name, brand_name) — Tofler branches.\n"
        "3. Combine, deduplicate by (name, city). Return only Active India locations."
    ),
    "tools":  MCA_TOOLS,
}

ecommerce_agent = {
    "name": "ecommerce_checker",
    "description": "Checks brand availability on Swiggy, Blinkit, Amazon across 20 Indian cities.",
    "system_prompt": (
        "You are the E-commerce Agent. Use the BRAND NAME for all searches.\n"
        "1. Call get_cities_list() to get the city list.\n"
        "2. For each city, call ecomm_check(platform, city, brand_name) "
        "for platforms: swiggy, blinkit, amazon.\n"
        "3. Return {city: {available_on: [...], score: N}} for all cities."
    ),
    "tools":  ECOMM_TOOLS,
}

maps_agent = {
    "name": "web_maps",
    "description": "Finds distributors/dealers via Google Maps, Justdial, IndiaMart.",
    "system_prompt": (
        "You are the Maps Agent. Use the BRAND NAME for all searches.\n"
        "1. Call maps_search('{brand} distributor', city) for major cities.\n"
        "2. Call justdial_search(brand, city) for key cities.\n"
        "3. Call indiamart_search(brand) for wholesale distributors.\n"
        "4. Return list of India-only locations with city, state, source."
    ),
    "tools":  MAPS_TOOLS,
}

report_agent = {
    "name": "report_builder",
    "description": "Generates Excel report + India heatmap from merged data.",
    "system_prompt": (
        "You are the Report Builder Agent.\n"
        "1. Call build_excel(data, brand_name) to create the Excel file.\n"
        "2. Call build_heatmap(state_scores) to generate heatmap JSON.\n"
        "3. Return {excel_path, heatmap, status}."
    ),
    "tools":  REPORT_TOOLS,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR PROMPT  (kept short to save tokens)
# ═══════════════════════════════════════════════════════════════════════════════

ORCHESTRATOR_PROMPT = """You are the Master Orchestrator of the Food Brand Intelligence System for India.

Input always contains TWO identifiers:
  COMPANY NAME — legal registered entity (e.g. "Haldiram Foods International Pvt Ltd")
  BRAND NAME   — consumer-facing brand   (e.g. "Haldirams")

Workflow:
1. Parse company_name and brand_name from user input.
2. Dispatch these agents (pass the right identifier to each):
   - fssai_scraper     → use brand_name
   - mca_company       → use company_name + brand_name
   - ecommerce_checker → use brand_name
   - web_maps          → use brand_name
3. Wait for all results. Mark failed agents as "unavailable".
4. Merge results into:
   {
     "company": "<company_name>",
     "brand":   "<brand_name>",
     "states":  ["Gujarat", "Maharashtra", ...],
     "cities":  {"Gujarat": ["Anand", "Ahmedabad"], ...},
     "sources": {"fssai": [...], "mca": [...], "ecommerce": {...}, "maps": [...]},
     "confidence": 0.0-1.0
   }
5. Call report_builder with the merged data.
6. Print a clear plain-text summary to the user.

INDIA ONLY — discard any non-Indian locations.
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILD AGENT
# ═══════════════════════════════════════════════════════════════════════════════

def build_agent(model: str):
    """Build and return the complete multi-agent system."""
    # virtual_mode=True: suppresses deprecation warning; uses virtual path semantics
    backend = FilesystemBackend(root_dir=Path.cwd(), virtual_mode=True)
    return create_deep_agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=backend,
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

def _extract_final_answer(messages: list) -> str:
    """
    Walk the LangGraph message list in reverse and return the last
    non-empty AIMessage text.  Handles both str and list-of-blocks
    content formats (Gemini returns list-of-blocks).
    """
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        raw = msg.content
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            parts = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw
                if (isinstance(block, dict) and block.get("type") == "text")
                or isinstance(block, str)
            ]
            text = "\n".join(p for p in parts if p).strip()
            if text:
                return text
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  RUNNER WITH RETRY
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_with_retry(agent, query: str, max_retries: int = 3) -> str:
    """
    Invoke the LangGraph CompiledStateGraph via ainvoke() — the correct API.
    create_deep_agent() returns a CompiledStateGraph which has no .run();
    the right call is: state = await agent.ainvoke({"messages": [...]})
    Retries automatically on RESOURCE_EXHAUSTED / rate-limit errors.
    Wait schedule: 15s -> 30s -> 60s
    """
    wait_seconds = [15, 30, 60]
    last_error = None
    input_state = {"messages": [HumanMessage(content=query)]}

    for attempt in range(max_retries):
        try:
            state    = await agent.ainvoke(input_state)
            messages = state.get("messages", [])

            # Print message trace so we can see what the agent did
            print("\n--- Message Trace ---")
            for i, m in enumerate(messages):
                tc      = len(getattr(m, "tool_calls", []))
                tag     = f" [{tc} tool_calls]" if tc else ""
                preview = str(m.content)[:120].replace("\n", " ")
                print(f"  [{i}] {type(m).__name__}{tag}: {preview!r}")
            print("---------------------")

            return _extract_final_answer(messages)

        except Exception as exc:
            msg_str   = str(exc)
            last_error = exc

            is_rate_limit = any(x in msg_str for x in [
                "RESOURCE_EXHAUSTED", "429", "quota", "rate_limit",
                "RateLimitError", "TooManyRequests",
            ])

            if is_rate_limit and attempt < max_retries - 1:
                wait = wait_seconds[attempt]
                print(f"\n  Rate limit (attempt {attempt + 1}/{max_retries})."
                      f" Retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue

            # Unknown error or final attempt
            raise

    raise last_error


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def run(company: str, brand: str, model: str) -> str:
    # ── Pre-flight: check API keys ────────────────────────────────────────────
    gemini_key   = os.getenv("GEMINI_API_KEY", "")
    serp_key     = os.getenv("SERP_API_KEY", "")
    maps_key     = os.getenv("GOOGLE_MAPS_API_KEY", "")

    print(f"\n{'='*62}")
    print(f"  Company : {company}")
    print(f"  Brand   : {brand}")
    print(f"  Model   : {model}")
    print(f"{'='*62}")
    print(f"  Keys    : Gemini={'SET' if gemini_key else 'MISSING'} | "
          f"SERP={'SET' if serp_key else 'missing'} | "
          f"Maps={'SET' if maps_key else 'missing'}")
    print(f"{'='*62}\n")

    if not gemini_key:
        print("  ❌  GEMINI_API_KEY not set in .env — cannot proceed.")
        return ""

    agent = build_agent(model)

    query = (
        f"Research the complete India presence (all states and cities) for:\n"
        f"  Company Name : {company}\n"
        f"  Brand Name   : {brand}\n\n"
        f"IMPORTANT:\n"
        f"- Pass '{company}' as company_name to mca_company agent\n"
        f"- Pass '{brand}' as brand_name to fssai_scraper, ecommerce_checker, web_maps agents\n"
        f"- All results must be INDIA ONLY"
    )

    print("🔍  Starting research...")
    start = time.time()

    try:
        result = await _run_with_retry(agent, query)
    except Exception as exc:
        print(f"\n  ❌  Agent failed after retries: {exc}")
        raise

    elapsed = time.time() - start
    print(f"\n✅  Research complete in {elapsed:.1f}s")
    print("\n" + "─" * 62)
    print(result if result else "[Agent returned no output]")
    print("─" * 62)

    # ── Save log ──────────────────────────────────────────────────────────────
    log_path = Path("agent_execution.log")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"Company : {company}\nBrand : {brand}\nModel : {model}\n")
        f.write(f"Elapsed : {elapsed:.1f}s\n")
        f.write(f"Output  :\n{result}\n")
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
        "--company", default="",
        help="Legal registered company name",
    )
    parser.add_argument(
        "--brand", required=True,
        help="Consumer-facing brand name (e.g. 'AMUL')",
    )
    parser.add_argument(
        "--model",
        default="google_genai:gemini-2.5-flash",
        help="LLM model (default: google_genai:gemini-2.5-flash)",
    )
    args = parser.parse_args()
    company = args.company.strip() if args.company.strip() else args.brand.strip()
    asyncio.run(run(company=company, brand=args.brand.strip(), model=args.model))


if __name__ == "__main__":
    main()
