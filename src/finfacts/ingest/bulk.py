"""Bulk backfill: SEC nightly zips -> per-CIK gzipped JSON in bronze."""

import gzip
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from finfacts.sec.client import SecClient
from finfacts.storage import bronze_path, cik10, write_once

log = logging.getLogger(__name__)

BULK_URLS = {
    "companyfacts": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "submissions": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
}


@dataclass
class ExtractStats:
    written: int = 0
    skipped: int = 0
    missing_ciks: list[int] = field(default_factory=list)


def extract_members(
    zip_path: Path, ciks: set[int], bronze_dir: Path, dataset: str, ingest_date: str
) -> ExtractStats:
    """Copy every zip member that belongs to ``ciks`` into bronze as ``<member>.gz``.

    Members are named ``CIK##########.json`` (plus ``-submissions-NNN.json`` pages for
    submissions). Existing bronze files are left untouched, so reruns are no-ops.
    """
    wanted = {cik10(c): c for c in ciks}
    seen: set[int] = set()
    stats = ExtractStats()
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            cik = wanted.get(name[:13])
            if cik is None:
                continue
            seen.add(cik)
            dest = bronze_path(bronze_dir, dataset, ingest_date, name + ".gz")
            if dest.exists():
                stats.skipped += 1
                continue
            # mtime=0 makes the gzip bytes deterministic for identical input.
            write_once(dest, gzip.compress(zf.read(name), mtime=0))
            stats.written += 1
    stats.missing_ciks = sorted(set(ciks) - seen)
    return stats


def backfill(client: SecClient, ciks: set[int], bronze_dir: Path, cache_dir: Path) -> None:
    for dataset, url in BULK_URLS.items():
        # The SEC snapshot date, not today's date, so the same snapshot never lands twice.
        snapshot = client.last_modified_date(url)
        zip_path = client.download(url, cache_dir / f"{dataset}_{snapshot}.zip")
        stats = extract_members(zip_path, ciks, bronze_dir, dataset, snapshot)
        log.info(
            "%s snapshot %s: written=%d skipped=%d missing=%d",
            dataset,
            snapshot,
            stats.written,
            stats.skipped,
            len(stats.missing_ciks),
        )
        if stats.missing_ciks:
            log.warning("%s has no file for CIKs: %s", dataset, stats.missing_ciks)
