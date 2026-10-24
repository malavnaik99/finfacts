"""Frozen evaluation database: the same facts in a `raw` and a `semantic` schema.

Questions are scored against this file, not the live warehouse, so gold answers stay valid
while the daily pipeline keeps loading new filings and restatements.

- raw:      what an analyst gets straight from SEC companyfacts (flattened XBRL facts, every
            filing, no mapping) plus a company list. The "before" condition.
- semantic: FinFacts' certified gold tables as of the snapshot date. The "after" condition.
"""

from pathlib import Path

import duckdb

SNAPSHOT_DATE = "2026-10-24"


def build_snapshot(warehouse: Path, out: Path, as_of: str = SNAPSHOT_DATE) -> None:
    """Create `out` from the local DuckDB warehouse, pinned to `as_of` (replaces `out`)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with duckdb.connect(str(out)) as con:
        con.execute(f"attach '{warehouse.as_posix()}' as wh (read_only)")
        con.execute("create schema raw")
        con.execute("create schema semantic")
        # A fact is known once its filing was accepted; nothing filed after the snapshot.
        con.execute(
            """
            create table raw.facts as
            select cik, taxonomy, concept, unit, period_start, period_end, value,
                   accession_number, form, filed_date, filing_fiscal_year, filing_fiscal_period,
                   frame
            from wh.silver.stg_companyfacts
            where filed_date <= cast(? as date)
            """,
            [as_of],
        )
        companies = """
            select cik, name, tickers, gics_sector, gics_sub_industry, fiscal_year_end
            from wh.gold.dim_company where is_current
        """
        con.execute(f"create table raw.companies as {companies}")
        con.execute(f"create table semantic.companies as {companies}")
        as_of_filter = (
            "valid_from <= cast(? as date) and (valid_to is null or valid_to > cast(? as date))"
        )
        con.execute(
            f"""
            create table semantic.financials as
            select cik, metric_id, fiscal_year, fiscal_period, period_start, period_end, value,
                   unit, is_derived, source_concept
            from wh.gold.fct_financials
            where {as_of_filter}
            """,
            [as_of, as_of],
        )
        con.execute(
            """
            create table semantic.financials_history as
            select cik, metric_id, fiscal_year, fiscal_period, period_start, period_end, value,
                   unit, version_no, valid_from, valid_to, is_restatement, is_derived,
                   source_concept, accession_number
            from wh.gold.fct_financials
            where valid_from <= cast(? as date)
            """,
            [as_of],
        )
        con.execute(
            "create table semantic.metrics as "
            "select metric_id, name, unit, period_type, statement, definition "
            "from wh.gold.dim_concept"
        )
        con.execute("detach wh")
