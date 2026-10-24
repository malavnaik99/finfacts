"""`finfacts` command-line entry point, shared by Make, Airflow and GitHub Actions."""

import json
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
    import duckdb
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


RAW_MANIFEST = Path("data/raw_manifest.json")
DBT_VARS = Path("data/dbt_vars.json")
DBT_FULL_REFRESH = Path("data/dbt_full_refresh")


@app.command("load-bq")
def load_bq_cmd(
    full_refresh: bool = typer.Option(False, help="rebuild every company (no scope vars)"),
) -> None:
    """Replace BigQuery raw tables from GCS and plan which companies dbt must rebuild.

    Writes data/dbt_vars.json (empty = full rebuild), data/dbt_full_refresh ("true" when
    there is no successful build to be incremental on, e.g. the first run or after a failed
    migration) and data/raw_manifest.json, which `finfacts mark-built` records after publish.
    """
    import google.cloud.storage as storage

    from finfacts import scope, warehouse

    s = _settings()
    if not s.gcs_bucket:
        raise typer.BadParameter("set GCS_BUCKET")
    client = _bq()
    current = warehouse.load_raw(client, s.gcs_bucket)
    built = (
        None
        if full_refresh
        else warehouse.read_built_manifest(storage.Client(project=client.project), s.gcs_bucket)
    )
    if built is None:
        dbt_vars: dict[str, list[int]] = {}
        typer.echo("dbt scope: FULL rebuild")
    else:
        universe_ciks = {c.cik for c in universe.load_universe(universe.latest_universe_path())}
        changed = scope.changed_ciks(current, built)
        dbt_vars = scope.plan_scope(changed, universe_ciks, universe.load_predecessor_map())
        typer.echo(
            f"dbt scope: {len(changed)} changed CIKs -> {len(dbt_vars['scope_ciks'])} companies "
            f"in {len(dbt_vars['changed_buckets'])} buckets"
        )
    DBT_VARS.parent.mkdir(parents=True, exist_ok=True)
    DBT_VARS.write_text(json.dumps(dbt_vars), encoding="utf-8")
    DBT_FULL_REFRESH.write_text("true" if built is None else "false", encoding="utf-8")
    RAW_MANIFEST.write_text(json.dumps({str(k): v for k, v in current.items()}), encoding="utf-8")


@app.command("mark-built")
def mark_built_cmd() -> None:
    """Record the loaded files as built. Run only after `finfacts publish` succeeded."""
    from datetime import UTC, datetime

    import google.cloud.storage as storage

    from finfacts import warehouse

    s = _settings()
    if not s.gcs_bucket or not s.gcp_project_id:
        raise typer.BadParameter("set GCS_BUCKET and GCP_PROJECT_ID")
    manifest = {int(k): v for k, v in json.loads(RAW_MANIFEST.read_text("utf-8")).items()}
    name = warehouse.write_built_manifest(
        storage.Client(project=s.gcp_project_id),
        s.gcs_bucket,
        manifest,
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    typer.echo(f"recorded built manifest gs://{s.gcs_bucket}/{name}")


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


TEXT_TARGETS_SQL = """
    select f.accession_number, f.cik, cast(f.filing_date as varchar), cast(f.report_date as varchar)
    from silver.stg_filings as f
    join silver.stg_universe as u on f.cik = u.cik
    where f.form = '10-K' and f.report_date >= date '2024-01-01'
    order by f.filing_date desc
"""
CHUNK_META_SQL = """
    select f.accession_number, split_part(c.tickers, ';', 1), c.name, p.fiscal_year
    from silver.stg_filings as f
    join gold.dim_company as c on f.cik = c.cik and c.is_current
    left join gold.dim_fiscal_period as p
        on p.cik = f.cik and p.fiscal_period = 'FY' and p.period_end = f.report_date
    where f.form = '10-K'
"""


def _warehouse() -> "duckdb.DuckDBPyConnection":
    import duckdb

    return duckdb.connect(
        os.environ.get("FINFACTS_DUCKDB_PATH", "data/finfacts.duckdb"), read_only=True
    )


@app.command("text")
def text_cmd(workers: int = typer.Option(4, help="parallel filings")) -> None:
    """Extract Item 1A and Item 7 from FY2024+ 10-Ks into bronze (idempotent)."""
    from finfacts.ingest import text

    s = _settings()
    with _warehouse() as con:
        targets = [text.Target(*r) for r in con.sql(TEXT_TARGETS_SQL).fetchall()]
    text.extract_all(targets, s.bronze_dir, s.sec_user_agent, workers)


@app.command("embed")
def embed_cmd() -> None:
    """Chunk the extracted 10-K sections and embed them into LanceDB + parquet."""
    from finfacts.ingest import text

    s = _settings()
    with _warehouse() as con:
        meta = {
            a: {"ticker": t, "company": n, "fiscal_year": fy}
            for a, t, n, fy in con.sql(CHUNK_META_SQL).fetchall()
        }
    chunks = list(text.iter_chunks(s.bronze_dir, meta))
    n = text.embed_and_store(
        chunks, s.data_dir / "lancedb", s.data_dir / "hf" / "tenk_chunks.parquet"
    )
    typer.echo(f"embedded {n} chunks")


@app.command("search")
def search_cmd(query: str, k: int = 5) -> None:
    """Top-k 10-K chunks for a question (LanceDB)."""
    from finfacts.ingest import text

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows consoles
    for h in text.search(_settings().data_dir / "lancedb", query, k):
        typer.echo(f"{h['ticker']} FY{h['fiscal_year']} Item {h['item']}  {h['text'][:160]}...")


EVAL_DIR = Path("eval/v1")
EVAL_DB = Path("data/eval/finfacts_eval_v1.duckdb")


@app.command("eval-build")
def eval_build_cmd() -> None:
    """Freeze the eval snapshot and (re)build eval/v1/questions.jsonl with gold answers."""
    from finfacts.eval import build, snapshot

    warehouse = Path(os.environ.get("FINFACTS_DUCKDB_PATH", "data/finfacts.duckdb"))
    snapshot.build_snapshot(warehouse, EVAL_DB)
    qs = build.build(EVAL_DB, EVAL_DIR / "handwritten.yaml", EVAL_DIR / "questions.jsonl")
    typer.echo(f"{len(qs)} questions written to {EVAL_DIR / 'questions.jsonl'}")


@app.command("eval")
def eval_cmd(workers: int = typer.Option(4, help="parallel questions")) -> None:
    """Text-to-SQL execution accuracy before vs after the semantic layer."""
    from finfacts.eval import run

    s = _settings()
    if not s.openrouter_api_key:
        raise typer.BadParameter("set OPENROUTER_API_KEY in .env")
    out = EVAL_DIR / "results" / s.eval_model.replace("/", "__")
    summary = run.run(
        EVAL_DIR / "questions.jsonl", EVAL_DB, out, s.eval_model, s.openrouter_api_key, workers
    )
    before, after = summary["conditions"]["before"], summary["conditions"]["after"]
    typer.echo(f"model {s.eval_model}, {summary['questions']} questions")
    typer.echo(
        f"  before (raw XBRL facts):   {before['accuracy']:6.1%}  "
        f"({before['sql_errors']} SQL errors)"
    )
    typer.echo(
        f"  after  (semantic layer):   {after['accuracy']:6.1%}  ({after['sql_errors']} SQL errors)"
    )
    for cat in after["by_category"]:
        typer.echo(
            f"    {cat:16} {before['by_category'][cat]:6.1%} -> {after['by_category'][cat]:6.1%}"
        )
    typer.echo(f"  usage: {summary['usage']}")
