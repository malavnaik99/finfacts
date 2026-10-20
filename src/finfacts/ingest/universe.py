"""Company universe: a dated S&P 500 snapshot, keyed by SEC CIK."""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
UNIVERSE_DIR = Path("config/universe")
FIELDS = ["cik", "tickers", "name", "gics_sector", "gics_sub_industry"]
MAX_UNMATCHED_SHARE = 0.02


@dataclass(frozen=True)
class Company:
    cik: int
    tickers: str  # ";"-joined; multi-class companies (GOOG/GOOGL) share one CIK
    name: str
    gics_sector: str
    gics_sub_industry: str


def build_universe(constituents_csv: str, sec_tickers: dict[str, Any]) -> list[Company]:
    """Join the constituent list to SEC tickers, one row per CIK, sorted by CIK.

    Raises if too many constituent CIKs are unknown to SEC (a sign the source is stale or wrong).
    """
    sec_ciks = {int(row["cik_str"]) for row in sec_tickers.values()}
    by_cik: dict[int, list[dict[str, str]]] = {}
    for row in csv.DictReader(io.StringIO(constituents_csv)):
        by_cik.setdefault(int(row["CIK"]), []).append(row)

    unmatched = sorted(set(by_cik) - sec_ciks)
    if len(unmatched) > MAX_UNMATCHED_SHARE * len(by_cik):
        raise ValueError(f"{len(unmatched)} constituent CIKs not found at SEC: {unmatched[:10]}")

    return [
        Company(
            cik=cik,
            tickers=";".join(sorted(r["Symbol"] for r in rows)),
            name=rows[0]["Security"],
            gics_sector=rows[0]["GICS Sector"],
            gics_sub_industry=rows[0]["GICS Sub-Industry"],
        )
        for cik, rows in sorted(by_cik.items())
        if cik in sec_ciks
    ]


def write_universe(companies: list[Company], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(c.__dict__ for c in companies)


def latest_universe_path(universe_dir: Path = UNIVERSE_DIR) -> Path:
    # Filenames are sp500_YYYY-MM-DD.csv, so lexical order is date order.
    paths = sorted(universe_dir.glob("sp500_*.csv"))
    if not paths:
        raise FileNotFoundError(f"no universe file in {universe_dir}; run `make universe`")
    return paths[-1]


def load_universe(path: Path) -> list[Company]:
    with path.open(encoding="utf-8") as fh:
        return [
            Company(
                cik=int(r["cik"]),
                tickers=r["tickers"],
                name=r["name"],
                gics_sector=r["gics_sector"],
                gics_sub_industry=r["gics_sub_industry"],
            )
            for r in csv.DictReader(fh)
        ]
