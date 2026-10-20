from pathlib import Path

import pytest

from finfacts.ingest.universe import build_universe, load_universe, write_universe

HEADER = (
    "Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,Date added,CIK,Founded"
)
CSV = "\n".join(
    [
        HEADER,
        'GOOGL,Alphabet Inc. (Class A),Communication Services,Interactive Media,"Mountain View, CA",2014-04-03,1652044,1998',  # noqa: E501
        'GOOG,Alphabet Inc. (Class C),Communication Services,Interactive Media,"Mountain View, CA",2006-04-03,1652044,1998',  # noqa: E501
        'AAPL,Apple Inc.,Information Technology,Hardware,"Cupertino, CA",1982-11-30,320193,1977',
    ]
)
SEC = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
}


def test_one_row_per_cik_sorted() -> None:
    companies = build_universe(CSV, SEC)
    assert [c.cik for c in companies] == [320193, 1652044]
    assert companies[1].tickers == "GOOG;GOOGL"


def test_fails_when_many_ciks_unknown_to_sec() -> None:
    with pytest.raises(ValueError, match="not found at SEC"):
        build_universe(CSV, {"0": SEC["0"]})


def test_roundtrip(tmp_path: Path) -> None:
    companies = build_universe(CSV, SEC)
    path = tmp_path / "sp500_2026-10-20.csv"
    write_universe(companies, path)
    assert load_universe(path) == companies
