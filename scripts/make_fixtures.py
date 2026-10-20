"""Regenerate tests/fixtures/bronze from a local backfill: 5 real CIKs, trimmed to stay small.

Usage: uv run python scripts/make_fixtures.py [data/bronze]
"""

import gzip
import json
import sys
from pathlib import Path
from typing import Any

# Apple (Sep 52/53-week FYE), Microsoft (June FYE), JPMorgan (bank), Walmart (Jan FYE),
# Salesforce (Jan FYE; has the stale `filed` date quirk documented in int_fact_versions).
CIKS = [320193, 789019, 19617, 104169, 1108524]
CONCEPTS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "Assets",
    "LongTermDebt",
    "AssetsFairValueDisclosure",
    "EntityCommonStockSharesOutstanding",
}
MIN_END = "2021-01-01"
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
OUT = Path("tests/fixtures/bronze")


def _read(p: Path) -> Any:
    return json.loads(gzip.decompress(p.read_bytes()))


def _write(p: Path, doc: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), mtime=0))


def main(bronze: Path) -> None:
    for cik in CIKS:
        name = f"CIK{cik:010d}.json.gz"
        cf_path = next(bronze.glob(f"companyfacts/ingest_date=*/{name}"))
        cf = _read(cf_path)
        cf["facts"] = {
            tax: {
                concept: {
                    "units": {
                        unit: [f for f in facts if f["end"] >= MIN_END]
                        for unit, facts in body["units"].items()
                    }
                }
                for concept, body in concepts.items()
                if concept in CONCEPTS
            }
            for tax, concepts in cf["facts"].items()
        }
        _write(OUT / "companyfacts" / cf_path.parent.name / name, cf)

        sub_path = next(bronze.glob(f"submissions/ingest_date=*/{name}"))
        sub = _read(sub_path)
        recent = sub["filings"]["recent"]
        keep = [i for i, form in enumerate(recent["form"]) if form in FORMS]
        sub["filings"] = {
            "recent": {k: [v[i] for i in keep] for k, v in recent.items()},
            "files": [],
        }
        _write(OUT / "submissions" / sub_path.parent.name / name, sub)
    print(f"wrote fixtures for {len(CIKS)} CIKs to {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/bronze"))
