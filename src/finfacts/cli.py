"""`finfacts` command-line entry point, shared by Make, Airflow and GitHub Actions."""

import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import typer

from finfacts.ingest import bulk, flatten, incremental, universe
from finfacts.sec.client import SecClient
from finfacts.settings import Settings

if TYPE_CHECKING:
    from google.cloud import bigquery

DBT_MANIFEST = Path("dbt/target/manifest.json")

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env


@app.command("check-env")
def check_env() -> None:
    """Validate settings without printing secret values."""
    s = _settings()
    typer.echo(f"SEC_USER_AGENT set; max_rps={s.sec_max_rps}; data_dir={s.data_dir}")


@app.command("universe")
def build_universe() -> None:
    """Snapshot the S&P 500 constituents (with SEC CIKs) to config/universe/."""
    s = _settings()
    constituents = httpx.get(universe.CONSTITUENTS_URL, timeout=30).raise_for_status().text
    with SecClient(s.sec_user_agent, s.sec_max_rps) as client:
        sec_tickers = client.get_json(universe.SEC_TICKERS_URL)
    companies = universe.build_universe(constituents, sec_tickers)
    path = universe.UNIVERSE_DIR / f"sp500_{date.today().isoformat()}.csv"
    universe.write_universe(companies, path)
    typer.echo(f"wrote {len(companies)} companies to {path}")


@app.command("backfill")
def backfill() -> None:
    """Download the SEC bulk zips and land in-scope CIKs in bronze (idempotent)."""
    s = _settings()
    ciks = {c.cik for c in universe.load_universe(universe.latest_universe_path())}
    ciks |= universe.load_predecessor_ciks()
    with SecClient(s.sec_user_agent, s.sec_max_rps) as client:
        bulk.backfill(client, ciks, s.bronze_dir, s.cache_dir)


@app.command("incremental")
def incremental_cmd() -> None:
    """Pull companyfacts only for CIKs with new periodic XBRL filings (idempotent)."""
    s = _settings()
    ciks = {c.cik for c in universe.load_universe(universe.latest_universe_path())}
    with SecClient(s.sec_user_agent, s.sec_max_rps) as client:
        stats = incremental.run_incremental(client, ciks, s.bronze_dir, s.state_path)
    typer.echo(
        f"checked={stats.checked} new_filings={stats.new_filings} "
        f"pulled={stats.pulled} deferred={stats.deferred}"
    )


@app.command("flatten")
def flatten_cmd() -> None:
    """Convert new bronze JSON files to parquet for dbt (idempotent)."""
    s = _settings()
    written, skipped = flatten.flatten_all(s.bronze_dir, s.flat_dir)
    typer.echo(f"flatten: written={written} skipped={skipped}")


@app.command("query")
def query_cmd(sql_file: Path, limit: int = typer.Option(200, help="Max rows to print")) -> None:
    """Run a SQL file against the local DuckDB warehouse (read-only) and print the result."""
    import duckdb  # local import: only this command needs it

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows consoles
    db = os.environ.get("FINFACTS_DUCKDB_PATH", "data/finfacts.duckdb")
    with duckdb.connect(db, read_only=True) as con:
        con.sql(sql_file.read_text(encoding="utf-8")).show(max_rows=limit, max_width=200)


def _bq() -> "bigquery.Client":
    from google.cloud import bigquery  # local import: only the warehouse commands need it

    s = _settings()
    if not s.gcp_project_id:
        raise typer.BadParameter("set GCP_PROJECT_ID")
    return bigquery.Client(project=s.gcp_project_id, location="US")


@app.command("load-bq")
def load_bq_cmd() -> None:
    """Replace BigQuery raw tables from the flattened parquet in GCS (free load jobs)."""
    from finfacts import warehouse

    s = _settings()
    if not s.gcs_bucket:
        raise typer.BadParameter("set GCS_BUCKET")
    warehouse.load_raw(_bq(), s.gcs_bucket)


@app.command("publish")
def publish_cmd(
    manifest: Path = typer.Option(DBT_MANIFEST, help="dbt manifest of the audited build"),
) -> None:
    """Copy audited gold tables from `audit` to `gold`. Run only after dbt build passed."""
    from finfacts import warehouse

    tables = warehouse.published_models(manifest)
    warehouse.publish(_bq(), tables)
    typer.echo(f"published {len(tables)} tables: {', '.join(tables)}")


@app.command("record-run")
def record_run_cmd(
    status: str = typer.Option(..., help="success or failure"),
    started_at: str = typer.Option(..., help="UTC ISO timestamp when the run started"),
    run_id: str = typer.Option(..., help="unique run id (GitHub run id or local)"),
    trigger: str = typer.Option("local", help="schedule, workflow_dispatch or local"),
    git_sha: str = typer.Option("", help="commit the run used"),
    run_results: Path = typer.Option(Path("dbt/target/run_results.json")),
) -> None:
    """Append this pipeline run to ops.run_log (status, dbt outcomes, bytes, freshness)."""
    from datetime import UTC, datetime

    from finfacts import warehouse

    row: dict[str, object] = {
        "run_id": run_id,
        "trigger": trigger,
        "git_sha": git_sha,
        "status": status,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        **warehouse.dbt_counts(run_results),
    }
    warehouse.record_run(_bq(), row)
