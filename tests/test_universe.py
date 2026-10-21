from pathlib import Path

import pytest

from finfacts.ingest.universe import (
    build_universe,
    latest_universe_path,
    load_predecessor_ciks,
    load_universe,
    write_universe,
)

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


def test_predecessor_ciks(tmp_path: Path) -> None:
    p = tmp_path / "predecessors.csv"
    p.write_text(
        "successor_cik,predecessor_cik,cutoff_date,note\n2115436,34088,2026-07-01,x\n",
        encoding="utf-8",
    )
    assert load_predecessor_ciks(p) == {34088}


def test_committed_predecessors_are_distinct_from_universe() -> None:
    # A predecessor that is itself a universe company would be counted twice.
    universe_ciks = {c.cik for c in load_universe(latest_universe_path())}
    assert load_predecessor_ciks().isdisjoint(universe_ciks)
