import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import respx

from finfacts.ingest.incremental import (
    COMPANYFACTS_URL,
    SUBMISSIONS_URL,
    latest_periodic_filing,
    load_state,
    run_incremental,
)
from finfacts.sec.client import SecClient

CIK = 320193
UA = "FinFacts-test/0.1 test@example.com"
SUBS_URL = SUBMISSIONS_URL.format(cik10="CIK0000320193")
FACTS_URL = COMPANYFACTS_URL.format(cik10="CIK0000320193")
NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def subs(*filings: tuple[str, str, str, int]) -> dict[str, Any]:
    accn, accepted, form, xbrl = zip(*filings, strict=True) if filings else ((), (), (), ())
    return {
        "filings": {
            "recent": {
                "accessionNumber": list(accn),
                "acceptanceDateTime": list(accepted),
                "form": list(form),
                "isXBRL": list(xbrl),
            }
        }
    }


def facts_with(accn: str) -> dict[str, Any]:
    return {"cik": CIK, "facts": {"us-gaap": {"Assets": {"units": {"USD": [{"accn": accn}]}}}}}


Q3 = ("Q3", "2026-08-01T20:00:00.000Z", "10-Q", 1)
K = ("K1", "2026-10-21T10:00:00.000Z", "10-K", 1)
EIGHT_K = ("8K", "2026-10-21T11:00:00.000Z", "8-K", 1)


def test_latest_periodic_ignores_8k_and_non_xbrl() -> None:
    doc = subs(Q3, EIGHT_K, ("X", "2026-10-21T12:00:00.000Z", "10-Q", 0))
    assert latest_periodic_filing(doc) == {"accession": "Q3", "accepted_at": Q3[1]}


def _seed(bronze: Path, doc: dict[str, Any]) -> None:
    p = bronze / "submissions" / "ingest_date=2026-10-20" / "CIK0000320193.json.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(gzip.compress(json.dumps(doc).encode()))


@respx.mock
def test_pulls_only_when_new_periodic_filing_then_noop(tmp_path: Path) -> None:
    bronze, state = tmp_path / "bronze", tmp_path / "ops" / "state.json"
    _seed(bronze, subs(Q3))  # backfill knew about Q3 only
    respx.get(SUBS_URL).mock(return_value=httpx.Response(200, json=subs(Q3, K, EIGHT_K)))
    facts_route = respx.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts_with("K1")))

    with SecClient(UA) as c:
        first = run_incremental(c, {CIK}, bronze, state, now=NOW)
        second = run_incremental(c, {CIK}, bronze, state, now=NOW)

    assert (first.new_filings, first.pulled) == (1, 1)
    assert (second.new_filings, second.pulled) == (0, 0)
    assert facts_route.call_count == 1
    assert load_state(state)[str(CIK)]["accession"] == "K1"
    written = bronze / "companyfacts" / "ingest_date=2026-10-21" / "CIK0000320193_K1.json.gz"
    assert json.loads(gzip.decompress(written.read_bytes())) == facts_with("K1")


@respx.mock
def test_defers_when_companyfacts_lags_within_grace(tmp_path: Path) -> None:
    bronze, state = tmp_path / "bronze", tmp_path / "ops" / "state.json"
    _seed(bronze, subs(Q3))
    respx.get(SUBS_URL).mock(return_value=httpx.Response(200, json=subs(Q3, K)))
    respx.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts_with("Q3")))

    with SecClient(UA) as c:
        stats = run_incremental(c, {CIK}, bronze, state, now=NOW)

    assert (stats.deferred, stats.pulled) == (1, 0)
    assert load_state(state)[str(CIK)]["accession"] == "Q3"  # mark not advanced
    assert not (bronze / "companyfacts").exists()
