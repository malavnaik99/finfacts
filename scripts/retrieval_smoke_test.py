"""Retrieval smoke test: 10 questions must each find a relevant 10-K chunk in the top 5.

A hit is relevant when it comes from one of the companies the question is about. Exits
non-zero unless all 10 pass. Usage: uv run python scripts/retrieval_smoke_test.py
"""

import sys
from pathlib import Path

from finfacts.ingest.text import search

LANCEDB = Path("data/lancedb")
ENERGY = {"XOM", "CVX", "COP", "OXY", "EOG", "DVN", "FANG", "APA", "HES", "MRO", "EQT", "CTRA"}
BANKS_CARDS = {"JPM", "BAC", "C", "WFC", "COF", "AXP", "SYF", "DFS", "USB", "PNC"}
MANAGED_CARE = {"UNH", "ELV", "CVS", "CI", "HUM", "CNC", "MOH"}
CHIPS = {"NVDA", "AMD", "AAPL", "QCOM", "AVGO", "MRVL", "MU", "TXN", "ADI", "INTC", "AMAT", "LRCX"}

CASES = [
    ("Reliance on contract manufacturers in Taiwan for advanced semiconductor chips", CHIPS),
    (
        "Demand for GLP-1 obesity and diabetes medicines and expanding manufacturing capacity",
        {"LLY", "NVO", "AMGN", "PFE"},
    ),
    ("737 MAX production rate, quality control and FAA oversight", {"BA", "SPR", "GE", "HWM"}),
    (
        "Paid membership growth from limiting account sharing on a streaming service",
        {"NFLX", "DIS", "WBD", "PARA", "PSKY", "SKYD"},
    ),
    ("Medicare Advantage medical cost trends and utilization pressure", MANAGED_CARE),
    ("Azure and other cloud services revenue growth driven by AI infrastructure", {"MSFT"}),
    (
        "Restaurant guest traffic, franchisees and value menu promotions",
        {"MCD", "YUM", "CMG", "SBUX", "DRI", "QSR", "DPZ"},
    ),
    ("Crude oil and natural gas price volatility affecting upstream production", ENERGY),
    ("Credit card net charge-offs and consumer credit quality", BANKS_CARDS),
    ("Electric vehicle demand, battery cell costs and regulatory credits", {"TSLA", "GM", "F"}),
]


def main() -> int:
    passed = 0
    for query, expected in CASES:
        hits = search(LANCEDB, query, k=5)
        found = [h for h in hits if (h["ticker"] or "") in expected]
        ok = bool(found)
        passed += ok
        top = ", ".join(f"{h['ticker']}/{h['item']}" for h in hits)
        print(f"{'PASS' if ok else 'FAIL'}  {query[:60]:60}  top5: {top}")
    print(
        f"retrieval smoke test: {passed}/{len(CASES)} queries found a relevant chunk in the top 5"
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
