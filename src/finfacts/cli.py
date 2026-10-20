"""`finfacts` command-line entry point, shared by Make, Airflow and GitHub Actions."""

import logging
from datetime import date

import httpx
import typer

from finfacts.ingest import bulk, universe
from finfacts.sec.client import SecClient
from finfacts.settings import Settings

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
    with SecClient(s.sec_user_agent, s.sec_max_rps) as client:
        bulk.backfill(client, ciks, s.bronze_dir, s.cache_dir)
