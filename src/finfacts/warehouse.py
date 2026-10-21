"""BigQuery side of the pipeline: load flattened parquet into `raw`, publish audited tables.

Write-audit-publish: dbt builds and tests every model in the `audit` dataset; only if the
whole build passes does `publish` copy the gold tables into `gold`. Copy jobs are free and
atomic per table, and a failed build never reaches `publish`, so `gold` keeps the last good
version.
"""

import csv
import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path

import google.cloud.storage as storage
from google.cloud import bigquery

from finfacts.ingest.universe import UNIVERSE_DIR, latest_universe_path

log = logging.getLogger(__name__)

FLAT_TABLES = ("companyfacts", "filings", "company")
# dbt folders whose models are published to `gold`.
PUBLISHED_FOLDERS = ("marts", "quality")


_CF_NAME = re.compile(r"ingest_date=(\d{4}-\d{2}-\d{2})/(CIK\d{10})[^/]*\.parquet$")


def latest_per_cik(object_names: Iterable[str]) -> list[str]:
    """Newest companyfacts file per CIK (by ingest date, then name: `CIK_<accn>` sorts after
    the same day's `CIK` backfill file).

    Each companyfacts file holds the company's complete history, every filing with its
    accession and date, so the newest file alone rebuilds all restatement versions. Loading
    only it keeps the raw table (and the bytes each daily build scans) from growing with
    every snapshot; bronze still keeps every file.
    """
    best: dict[str, tuple[str, str]] = {}
    for name in object_names:
        m = _CF_NAME.search(name)
        if m is None:
            continue
        key = (m.group(1), name)
        if m.group(2) not in best or key > best[m.group(2)]:
            best[m.group(2)] = key
    return sorted(name for _, name in best.values())


def load_raw(client: bigquery.Client, bucket: str, dataset: str = "raw") -> None:
    """Replace raw tables from GCS parquet and the committed config CSVs (load jobs: free)."""
    gcs = storage.Client(project=client.project)
    for table in FLAT_TABLES:
        prefix = f"gs://{bucket}/flat/{table}/"
        if table == "companyfacts":
            names = (b.name for b in gcs.list_blobs(bucket, prefix=f"flat/{table}/"))
            uris: str | list[str] = [f"gs://{bucket}/{n}" for n in latest_per_cik(names)]
        else:
            uris = f"{prefix}*"  # filings and company rows are deduplicated in dbt staging
        hive = bigquery.HivePartitioningOptions()
        hive.mode = "AUTO"
        hive.source_uri_prefix = prefix
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            hive_partitioning=hive,
        )
        job = client.load_table_from_uri(
            uris, f"{client.project}.{dataset}.{table}", job_config=config
        )
        job.result()
        log.info("loaded %s.%s: %s rows", dataset, table, job.output_rows)

    csvs = {"universe": latest_universe_path(), "predecessors": UNIVERSE_DIR / "predecessors.csv"}
    for table, path in csvs.items():
        with path.open(encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[bigquery.SchemaField(col, "STRING") for col in header],
        )
        with path.open("rb") as fh:
            job = client.load_table_from_file(
                fh, f"{client.project}.{dataset}.{table}", job_config=config
            )
        job.result()
        log.info("loaded %s.%s from %s: %s rows", dataset, table, path.name, job.output_rows)


def published_models(manifest_path: Path) -> list[str]:
    """Names of the dbt models to publish, read from the manifest of the audited build."""
    nodes = json.loads(manifest_path.read_text(encoding="utf-8"))["nodes"].values()
    return sorted(
        n["name"]
        for n in nodes
        if n["resource_type"] == "model"
        and n["original_file_path"].replace("\\", "/").split("/")[1] in PUBLISHED_FOLDERS
    )


def publish(
    client: bigquery.Client, tables: list[str], src: str = "audit", dst: str = "gold"
) -> None:
    """Copy audited tables over the published ones (WRITE_TRUNCATE copy jobs: free)."""
    if not tables:
        raise ValueError("nothing to publish: no gold models found in the dbt manifest")
    config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    for table in tables:
        client.copy_table(
            f"{client.project}.{src}.{table}", f"{client.project}.{dst}.{table}", job_config=config
        ).result()
        log.info("published %s.%s -> %s.%s", src, table, dst, table)
