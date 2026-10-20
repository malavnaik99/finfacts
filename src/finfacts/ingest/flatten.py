"""Bronze JSON -> long parquet, one row per fact or filing. Pure reshaping, no business logic.

All dedup, restatement and period logic lives in dbt so DuckDB and BigQuery share it.
"""

import gzip
import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

FACT_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("entity_name", pa.string()),
        ("taxonomy", pa.string()),
        ("concept", pa.string()),
        ("unit", pa.string()),
        ("period_start", pa.string()),  # ISO dates kept as strings; cast in dbt
        ("period_end", pa.string()),
        ("value", pa.float64()),
        ("accn", pa.string()),
        ("fy", pa.int64()),
        ("fp", pa.string()),
        ("form", pa.string()),
        ("filed", pa.string()),
        ("frame", pa.string()),
        ("source_file", pa.string()),
    ]
)

FILING_FIELDS = {
    "accessionNumber": "accession_number",
    "filingDate": "filing_date",
    "reportDate": "report_date",
    "acceptanceDateTime": "acceptance_datetime",
    "form": "form",
    "isXBRL": "is_xbrl",
    "isInlineXBRL": "is_inline_xbrl",
    "primaryDocument": "primary_document",
    "primaryDocDescription": "primary_doc_description",
    "items": "items",
}
FILING_SCHEMA = pa.schema(
    [("cik", pa.int64())]
    + [
        (col, pa.int64() if col.startswith("is_") else pa.string())
        for col in FILING_FIELDS.values()
    ]
    + [("source_file", pa.string())]
)

COMPANY_SCHEMA = pa.schema(
    [
        ("cik", pa.int64()),
        ("name", pa.string()),
        ("tickers", pa.string()),
        ("exchanges", pa.string()),
        ("sic", pa.string()),
        ("sic_description", pa.string()),
        ("fiscal_year_end", pa.string()),
        ("state_of_incorporation", pa.string()),
        ("category", pa.string()),
        ("entity_type", pa.string()),
        ("source_file", pa.string()),
    ]
)


def flatten_companyfacts(doc: dict[str, Any], source_file: str) -> pa.Table:
    cols: dict[str, list[Any]] = {name: [] for name in FACT_SCHEMA.names}
    cik, entity = int(doc["cik"]), doc.get("entityName")
    for taxonomy, concepts in doc.get("facts", {}).items():
        for concept, body in concepts.items():
            for unit, facts in body.get("units", {}).items():
                for f in facts:
                    cols["cik"].append(cik)
                    cols["entity_name"].append(entity)
                    cols["taxonomy"].append(taxonomy)
                    cols["concept"].append(concept)
                    cols["unit"].append(unit)
                    cols["period_start"].append(f.get("start"))
                    cols["period_end"].append(f["end"])
                    cols["value"].append(float(f["val"]))
                    cols["accn"].append(f["accn"])
                    cols["fy"].append(f.get("fy"))
                    cols["fp"].append(f.get("fp"))
                    cols["form"].append(f.get("form"))
                    cols["filed"].append(f["filed"])
                    cols["frame"].append(f.get("frame"))
                    cols["source_file"].append(source_file)
    return pa.table(cols, schema=FACT_SCHEMA)


def flatten_filings(columnar: dict[str, list[Any]], cik: int, source_file: str) -> pa.Table:
    """``columnar`` is SEC's column-oriented block (``filings.recent`` or a page file)."""
    n = len(columnar["accessionNumber"])
    cols: dict[str, list[Any]] = {"cik": [cik] * n}
    for src, dst in FILING_FIELDS.items():
        values = columnar.get(src, [None] * n)
        cols[dst] = [v if v != "" else None for v in values]
    cols["source_file"] = [source_file] * n
    return pa.table(cols, schema=FILING_SCHEMA)


def flatten_company(doc: dict[str, Any], source_file: str) -> pa.Table:
    row = {
        "cik": int(doc["cik"]),
        "name": doc.get("name"),
        "tickers": ";".join(doc.get("tickers") or []),
        "exchanges": ";".join(e for e in doc.get("exchanges") or [] if e),
        "sic": doc.get("sic") or None,
        "sic_description": doc.get("sicDescription") or None,
        "fiscal_year_end": doc.get("fiscalYearEnd") or None,
        "state_of_incorporation": doc.get("stateOfIncorporation") or None,
        "category": doc.get("category") or None,
        "entity_type": doc.get("entityType") or None,
        "source_file": source_file,
    }
    return pa.table({k: [v] for k, v in row.items()}, schema=COMPANY_SCHEMA)


@dataclass(frozen=True)
class Job:
    table: str
    src: Path
    dest: Path


def _jobs(bronze_dir: Path, flat_dir: Path) -> Iterator[Job]:
    for src in sorted(bronze_dir.glob("*/ingest_date=*/*.json.gz")):
        dataset, partition = src.parent.parent.name, src.parent.name
        stem = src.name.removesuffix(".json.gz")
        tables = ["companyfacts"] if dataset == "companyfacts" else ["filings"]
        if dataset == "submissions" and "-submissions-" not in stem:
            tables.append("company")  # main submissions files also carry company attributes
        for table in tables:
            yield Job(table, src, flat_dir / table / partition / f"{stem}.parquet")


def _build(job: Job) -> pa.Table:
    doc = json.loads(gzip.decompress(job.src.read_bytes()))
    source_file = job.src.as_posix()
    if job.table == "companyfacts":
        return flatten_companyfacts(doc, source_file)
    if job.table == "company":
        return flatten_company(doc, source_file)
    cik = int(job.src.name[3:13])  # page files carry no CIK inside
    columnar = doc["filings"]["recent"] if "filings" in doc else doc
    return flatten_filings(columnar, cik, source_file)


def flatten_all(bronze_dir: Path, flat_dir: Path) -> tuple[int, int]:
    """Flatten every bronze file that has no parquet yet. Returns (written, skipped)."""
    written = skipped = 0
    for job in _jobs(bronze_dir, flat_dir):
        if job.dest.exists():
            skipped += 1
            continue
        job.dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = job.dest.with_name(job.dest.name + ".tmp")
        pq.write_table(_build(job), tmp, compression="zstd")
        os.replace(tmp, job.dest)
        written += 1
    log.info("flatten: written=%d skipped=%d", written, skipped)
    return written, skipped
