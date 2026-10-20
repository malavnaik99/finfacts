import gzip
import json
from pathlib import Path

import pyarrow.parquet as pq

from finfacts.ingest.flatten import flatten_all

FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 391035000000,
                            "accn": "A1",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "frame": "CY2024",
                        },
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {
                            "end": "2024-09-28",
                            "val": 364980000000,
                            "accn": "A1",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                        },
                    ]
                }
            },
        }
    },
}
SUBS = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "sic": "3571",
    "fiscalYearEnd": "0926",
    "filings": {
        "recent": {
            "accessionNumber": ["A1", "A2"],
            "filingDate": ["2024-11-01", "2024-11-02"],
            "reportDate": ["2024-09-28", ""],
            "acceptanceDateTime": ["2024-11-01T10:00:00.000Z", "2024-11-02T10:00:00.000Z"],
            "form": ["10-K", "4"],
            "isXBRL": [1, 0],
            "isInlineXBRL": [1, 0],
            "primaryDocument": ["a.htm", "b.xml"],
            "primaryDocDescription": ["10-K", ""],
            "items": ["", ""],
        }
    },
}
PAGE = {
    "accessionNumber": ["OLD1"],
    "filingDate": ["2010-01-01"],
    "reportDate": [""],
    "acceptanceDateTime": ["2010-01-01T10:00:00.000Z"],
    "form": ["10-K"],
    "isXBRL": [0],
    "isInlineXBRL": [0],
    "primaryDocument": ["x.htm"],
    "primaryDocDescription": [""],
    "items": [""],
}


def _write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(doc).encode()))


def test_flattens_all_tables_and_is_idempotent(tmp_path: Path) -> None:
    bronze, flat = tmp_path / "bronze", tmp_path / "flat"
    part = "ingest_date=2026-10-20"
    _write(bronze / "companyfacts" / part / "CIK0000320193.json.gz", FACTS)
    _write(bronze / "submissions" / part / "CIK0000320193.json.gz", SUBS)
    _write(bronze / "submissions" / part / "CIK0000320193-submissions-001.json.gz", PAGE)

    assert flatten_all(bronze, flat) == (4, 0)  # facts, filings x2, company
    assert flatten_all(bronze, flat) == (0, 4)

    facts = pq.read_table(flat / "companyfacts" / part / "CIK0000320193.parquet").to_pylist()
    assert len(facts) == 2
    assets = next(f for f in facts if f["concept"] == "Assets")
    assert assets["period_start"] is None
    assert assets["value"] == 364980000000.0

    page = pq.read_table(flat / "filings" / part / "CIK0000320193-submissions-001.parquet")
    assert page.column("cik").to_pylist() == [320193]  # CIK taken from the filename
    recent = pq.read_table(flat / "filings" / part / "CIK0000320193.parquet").to_pylist()
    assert recent[1]["report_date"] is None  # "" becomes null

    company = pq.read_table(flat / "company" / part / "CIK0000320193.parquet").to_pylist()
    assert company[0]["fiscal_year_end"] == "0926"
    assert company[0]["tickers"] == "AAPL"
