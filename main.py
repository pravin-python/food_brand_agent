"""
main.py — Project root entry point
Food Brand Intelligence System — India

Usage:
    python main.py --company "GUJARAT CO-OP MILK MARKETING FEDERATION LTD." --brand "AMUL"
    python main.py --company "Haldiram Foods International Pvt Ltd" --brand "Haldirams"
    python main.py --brand "Parle-G"   # --company defaults to brand if omitted
"""

from agents.main_agent import main

if __name__ == "__main__":
    main()
