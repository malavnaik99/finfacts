# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] – 2026-10-20 – Milestone 2: silver layer and daily incremental

### Added
- `finfacts incremental`: per-CIK high-water mark on 10-K/10-Q-type XBRL filings; pulls companyfacts only for companies with new filings; defers (up to 3 days) when companyfacts lags submissions; crash-safe state saved after each company.
- `finfacts flatten`: bronze JSON → long parquet (facts, filings, company), idempotent. *(Plan change, approved: flattening moved from dbt SQL to Python so DuckDB and BigQuery share one input.)*
- dbt project on DuckDB: `stg_companyfacts`, `stg_filings`, `stg_company`, `stg_universe`, `int_fact_versions` (restatement history), `dim_company` (SCD2), `dim_period` (fiscal/calendar labels), with enforced contracts on gold models.
- Tests: uniqueness/not-null/relationships, one open version per fact, contiguous versions, fiscal-period uniqueness (warn), and a dbt unit test for fiscal labelling (52/53-week years, Jan year ends, trailing-12-month and cover-page periods).
- Cross-engine macros (`surrogate_key`, `make_date`) ready for BigQuery.
- CI runs `dbt build` on committed fixtures (5 real companies, trimmed, 48 KB).
- `docs/silver-layer.md`: point-in-time rules, a worked JPMorgan restatement, and seven data quirks found.

### Fixed (found by the new tests)
- Proxy statements (DEF 14A pay-versus-performance) created false restatements; silver now keeps financial-statement forms only.
- Stale `filed` dates in companyfacts made versions overlap; versions now use the SEC acceptance date.

## [0.1.0] – 2026-10-20 – Milestone 1: foundations and bulk ingestion

### Added
- Project scaffold: uv, ruff, mypy (strict), pytest, pre-commit, Makefile, GitHub Actions CI.
- `finfacts` CLI: `check-env`, `universe`, `backfill`.
- SEC client with an 8 req/s token bucket, mandatory User-Agent, retries with backoff on 403/429/5xx and network errors, and atomic, cached streaming downloads.
- S&P 500 universe snapshot joined to SEC CIKs (`config/universe/`).
- Bulk backfill from `companyfacts.zip` and `submissions.zip` into immutable, gzipped, per-CIK bronze files partitioned by SEC snapshot date. Reruns are no-ops.
- `DATA_LICENSES.md`, MIT licence, `PLAN.md`.
