"""Incremental build == full build, on real data (DuckDB).

1. "before": the 2026-10-20 snapshot files, minus newer files for a set of companies
2. "after":  the same plus those companies' 2026-10-21 snapshot files (genuinely newer data),
            including ExxonMobil's predecessor CIK to exercise the CIK mapping
3. path A: full build on "before", then an INCREMENTAL build on "after" with the vars
           finfacts.scope plans from the file manifests
4. path B: FULL build on "after"
5. every incremental model and the gold fact table must be identical (row for row)

Needs the local backfill in data/flat. Usage: uv run python scripts/check_incremental_equivalence.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

from finfacts.ingest.universe import latest_universe_path, load_universe
from finfacts.scope import changed_ciks, manifest_from, plan_scope

FLAT = Path("data/flat")
WORK = Path("build/incremental_check")
OLD_DATE, NEW_DATE = "ingest_date=2026-10-20", "ingest_date=2026-10-21"
# A spread of companies (incl. ExxonMobil's old CIK 34088) whose newer snapshot is "new data".
CHANGED = [
    320193,
    789019,
    19617,
    104169,
    200406,
    1045810,
    80424,
    753308,
    49826,
    21344,
    1018724,
    1652044,
    1326801,
    12927,
    18230,
    40545,
    51143,
    78003,
    93410,
    732717,
    70858,
    886982,
    1318605,
    2488,
    34088,
]
TABLES = [
    "silver.stg_companyfacts",
    "silver.stg_filings",
    "silver.int_fact_versions",
    "silver.int_canonical_periods",
    "silver.int_metric_reported",
    "gold.dim_period",
    "gold.fct_financials",
]


def cik_of(path: Path) -> int:
    return int(path.name[3:13])


def stage(dest: Path, include_new: bool) -> list[str]:
    """Copy parquet files into dest/flat; return the object names (as GCS would list them)."""
    shutil.rmtree(dest, ignore_errors=True)
    names = []
    for src in FLAT.rglob("*.parquet"):
        partition = src.parent.name
        if partition == OLD_DATE and "_" in src.stem:
            continue  # leave out the 2026-10-20 incremental files: one snapshot per state
        if partition == NEW_DATE and not (include_new and cik_of(src) in CHANGED):
            continue
        rel = src.relative_to(FLAT)
        (dest / "flat" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest / "flat" / rel)
        names.append(f"flat/{rel.as_posix()}")
    return names


def dbt(data_dir: Path, db: Path, *args: str) -> None:
    env = {**os.environ, "DATA_DIR": str(data_dir), "FINFACTS_DUCKDB_PATH": str(db)}
    cmd = [
        "dbt",
        "--no-use-colors",
        "build",
        "--project-dir",
        "dbt",
        "--profiles-dir",
        "dbt",
        "--exclude",
        "tag:full_data",
        *args,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    summary = [line for line in result.stdout.splitlines() if "Done. PASS=" in line]
    print("   ", summary[-1].split("  ")[-1] if summary else result.stdout[-2000:])
    if result.returncode != 0:
        raise SystemExit(f"dbt failed: {' '.join(args)}")


def main() -> int:
    universe = {c.cik for c in load_universe(latest_universe_path())}
    preds = {
        int(r["predecessor_cik"]): int(r["successor_cik"])
        for r in __import__("csv").DictReader(
            Path("config/universe/predecessors.csv").read_text(encoding="utf-8").splitlines()
        )
    }
    old_names = stage(WORK / "before", include_new=False)
    new_names = stage(WORK / "after", include_new=True)
    changed = changed_ciks(manifest_from(new_names), manifest_from(old_names))
    scope = plan_scope(changed, universe, preds)
    print(
        f"changed raw CIKs: {len(changed)}; buckets: {len(scope['changed_buckets'])}; "
        f"companies rebuilt: {len(scope['scope_ciks'])} of {len(universe)}"
    )

    db_a, db_b = (WORK / "a.duckdb").resolve(), (WORK / "b.duckdb").resolve()
    print("path A: full build on 'before'")
    dbt((WORK / "before").resolve(), db_a, "--full-refresh")
    print("path A: incremental build on 'after'")
    dbt((WORK / "after").resolve(), db_a, "--vars", json.dumps(scope))
    print("path B: full build on 'after'")
    dbt((WORK / "after").resolve(), db_b, "--full-refresh")

    with duckdb.connect(str(db_a), read_only=True) as con:
        con.execute(f"attach '{db_b.as_posix()}' as b (read_only)")
        bad = 0

        def count(sql: str) -> int:
            return int(con.sql(sql).fetchone()[0])  # type: ignore[index]

        # table names come from the TABLES constant above, never from input
        for t in TABLES:
            only_a = count(
                f"select count(*) from (select * from {t} except all select * from b.{t})"
            )
            only_b = count(
                f"select count(*) from (select * from b.{t} except all select * from {t})"
            )
            rows = count(f"select count(*) from {t}")
            print(f"  {t:32} rows={rows:>9,}  only_incremental={only_a}  only_full={only_b}")
            bad += only_a + only_b
    print("incremental == full" if bad == 0 else f"MISMATCH: {bad} differing rows")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
