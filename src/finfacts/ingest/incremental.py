"""Daily incremental load driven by a per-CIK high-water mark of periodic XBRL filings.

For every CIK we read ``submissions`` (cheap, ~1 request each). Only CIKs whose latest
periodic XBRL filing is newer than the stored mark get a fresh ``companyfacts`` pull.
"""

import gzip
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from finfacts.sec.client import SecClient
from finfacts.storage import bronze_path, cik10, write_once

log = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/{cik10}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/{cik10}.json"
# Forms whose XBRL lands in companyfacts. 8-K XBRL is cover-page only, so it never moves the mark.
PERIODIC_FORMS = frozenset(
    {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-QT", "20-F", "20-F/A", "40-F", "40-F/A"}
)
# companyfacts can lag submissions; retry a filing this long before accepting it is absent.
COMPANYFACTS_GRACE = timedelta(days=3)

Mark = dict[str, str]  # {"accession": ..., "accepted_at": ISO-8601 UTC}


def latest_periodic_filing(submissions: dict[str, Any]) -> Mark | None:
    recent = submissions["filings"]["recent"]
    best: Mark | None = None
    for accn, accepted, form, is_xbrl in zip(
        recent["accessionNumber"],
        recent["acceptanceDateTime"],
        recent["form"],
        recent["isXBRL"],
        strict=True,
    ):
        if is_xbrl and form in PERIODIC_FORMS and (best is None or accepted > best["accepted_at"]):
            best = {"accession": accn, "accepted_at": accepted}
    return best


def companyfacts_has_accession(doc: dict[str, Any], accession: str) -> bool:
    return any(
        f["accn"] == accession
        for concepts in doc.get("facts", {}).values()
        for body in concepts.values()
        for facts in body.get("units", {}).values()
        for f in facts
    )


def load_state(path: Path) -> dict[str, Mark]:
    if not path.exists():
        return {}
    state: dict[str, Mark] = json.loads(path.read_text(encoding="utf-8"))
    return state


def save_state(path: Path, state: dict[str, Mark]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def seed_state_from_bronze(bronze_dir: Path, ciks: set[int]) -> dict[str, Mark]:
    """Initial marks from the newest bronze submissions file per CIK (i.e. the backfill)."""
    state: dict[str, Mark] = {}
    for path in sorted(bronze_dir.glob("submissions/ingest_date=*/CIK*.json.gz")):
        if "-submissions-" in path.name:
            continue
        cik = int(path.name[3:13])
        if cik not in ciks:
            continue
        mark = latest_periodic_filing(json.loads(gzip.decompress(path.read_bytes())))
        if mark and (str(cik) not in state or mark["accepted_at"] > state[str(cik)]["accepted_at"]):
            state[str(cik)] = mark
    return state


@dataclass
class IncrementalStats:
    checked: int = 0
    new_filings: int = 0
    pulled: int = 0
    deferred: int = 0


def run_incremental(
    client: SecClient,
    ciks: set[int],
    bronze_dir: Path,
    state_path: Path,
    now: datetime | None = None,
) -> IncrementalStats:
    now = now or datetime.now(UTC)
    today = now.date().isoformat()
    state = (
        load_state(state_path) if state_path.exists() else seed_state_from_bronze(bronze_dir, ciks)
    )
    stats = IncrementalStats()

    for cik in sorted(ciks):
        stats.checked += 1
        subs = client.get_json(SUBMISSIONS_URL.format(cik10=cik10(cik)))
        mark = latest_periodic_filing(subs)
        old = state.get(str(cik))
        if mark is None or (old is not None and mark["accepted_at"] <= old["accepted_at"]):
            continue

        stats.new_filings += 1
        facts = client.get_json(COMPANYFACTS_URL.format(cik10=cik10(cik)))
        accepted = datetime.fromisoformat(mark["accepted_at"].replace("Z", "+00:00"))
        if not companyfacts_has_accession(facts, mark["accession"]):
            if now - accepted < COMPANYFACTS_GRACE:
                log.info(
                    "cik %s: %s not in companyfacts yet; retry next run", cik, mark["accession"]
                )
                stats.deferred += 1
                continue
            log.warning("cik %s: %s never reached companyfacts", cik, mark["accession"])

        # Accession in the filename: two filings on one day never collide in write-once bronze.
        name = f"{cik10(cik)}_{mark['accession']}.json.gz"
        for dataset, doc in (("companyfacts", facts), ("submissions", subs)):
            write_once(
                bronze_path(bronze_dir, dataset, today, name),
                gzip.compress(json.dumps(doc).encode(), mtime=0),
            )
        stats.pulled += 1
        state[str(cik)] = mark
        save_state(state_path, state)  # after every CIK, so a crash resumes where it stopped

    save_state(state_path, state)
    log.info("incremental: %s", stats)
    return stats
