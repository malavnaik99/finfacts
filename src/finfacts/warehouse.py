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


RUN_LOG_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING"),
    bigquery.SchemaField("trigger", "STRING"),
    bigquery.SchemaField("git_sha", "STRING"),
    bigquery.SchemaField("status", "STRING"),
    bigquery.SchemaField("started_at", "TIMESTAMP"),
    bigquery.SchemaField("finished_at", "TIMESTAMP"),
    bigquery.SchemaField("models_ok", "INT64"),
    bigquery.SchemaField("models_error", "INT64"),
    bigquery.SchemaField("tests_pass", "INT64"),
    bigquery.SchemaField("tests_warn", "INT64"),
    bigquery.SchemaField("tests_fail", "INT64"),
    bigquery.SchemaField("queries", "INT64"),
    bigquery.SchemaField("bytes_billed", "INT64"),
    bigquery.SchemaField("latest_filing_accepted_at", "TIMESTAMP"),
]


def dbt_counts(run_results_path: Path) -> dict[str, int]:
    """Model and test outcomes, queries and bytes billed from a dbt run_results.json.

    BigQuery reports bytes billed per node in `adapter_response`, so the cost of a run needs
    no access to project job history. Load and copy jobs outside dbt are free.
    Zeros if dbt never ran.
    """
    counts = dict.fromkeys(
        (
            "models_ok",
            "models_error",
            "tests_pass",
            "tests_warn",
            "tests_fail",
            "queries",
            "bytes_billed",
        ),
        0,
    )
    if not run_results_path.exists():
        return counts
    for r in json.loads(run_results_path.read_text(encoding="utf-8"))["results"]:
        kind, status = r["unique_id"].split(".")[0], r["status"]
        billed = (r.get("adapter_response") or {}).get("bytes_billed")
        if billed is not None:
            counts["queries"] += 1
            counts["bytes_billed"] += int(billed)
        if kind in ("model", "seed"):
            counts["models_ok" if status == "success" else "models_error"] += 1
        elif kind in ("test", "unit_test"):
            key = {"pass": "tests_pass", "warn": "tests_warn"}.get(status, "tests_fail")
            counts[key] += 1
    return counts


def record_run(client: bigquery.Client, row: dict[str, object], dataset: str = "ops") -> None:
    """Append one run to ops.run_log with a load job (free, unlike streaming inserts).

    Adds the newest periodic filing in the audited warehouse (data freshness).
    """
    fresh_sql = """
        select max(accepted_at) as latest
        from audit.stg_filings where form in ('10-K', '10-Q', '10-K/A', '10-Q/A')
    """
    try:
        latest = next(iter(client.query(fresh_sql).result())).latest
    except Exception:  # audit tables may not exist if the run failed before dbt
        latest = None
    row = {**row, "latest_filing_accepted_at": latest.isoformat() if latest else None}
    config = bigquery.LoadJobConfig(
        schema=RUN_LOG_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    client.load_table_from_json(
        [row], f"{client.project}.{dataset}.run_log", job_config=config
    ).result()
    log.info("recorded run %s: %s", row["run_id"], row["status"])
