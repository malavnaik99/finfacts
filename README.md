# FinFacts

[![ci](https://github.com/malavnaik99/finfacts/actions/workflows/ci.yml/badge.svg)](https://github.com/malavnaik99/finfacts/actions/workflows/ci.yml)

**Certified, point-in-time-correct SEC EDGAR fundamentals, so analysts, a text-to-SQL agent and an MCP server all get the same answer.**

Raw SEC XBRL data is hard to query consistently:

- **Tags vary.** "Revenue" is `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` and more, depending on company, year and sector.
- **Figures get restated.** The same period's value changes in later filings.
- **Periods don't line up.** Fiscal years end in different months, Q4 is rarely filed directly, and the `fy`/`fp` fields in `companyfacts` describe the filing, not the fact.

FinFacts turns S&P 500 filings (FY2015 to today) into a tested star schema with a semantic layer on top. See [PLAN.md](PLAN.md) for the full design and roadmap.

## Status

| Milestone | Status |
|---|---|
| 1. Foundations and bulk ingestion (local) | ✅ done |
| 2. Silver layer and daily incremental | ✅ done |
| 3. Concept mapping and gold mart | ⏳ next |
| 4. GCP, write-audit-publish, scheduling | — |
| 5. Semantic layer and data-health page | — |
| 6. AI outputs (eval set, 10-K embeddings) | — |

## Quickstart (Windows, macOS or Linux)

Needs Python 3.11, [uv](https://docs.astral.sh/uv/) and GNU Make.

```bash
cp .env.example .env          # then set SEC_USER_AGENT="AppName/1.0 you@example.com"
make setup                    # locked env + git hooks
make check-env                # validates settings, prints no secrets
make test                     # unit tests, no network
make backfill-local           # ~3 GB download once; lands ~500 companies in data/bronze/
make incremental              # daily: pulls only companies with new 10-K/10-Q filings
make build                    # flatten to parquet + dbt build (models and tests) on DuckDB
make ci                       # lint, types, unit tests, dbt build on offline fixtures
```

`make help` lists every target.

## How ingestion works

1. **Universe.** `make universe` snapshots S&P 500 constituents and validates each CIK against SEC's `company_tickers.json`. The result is committed to [`config/universe/`](config/universe/). It is one dated snapshot, so history has survivorship bias. This is a known, documented limitation.
2. **Bulk backfill.** `make backfill-local` downloads SEC's nightly `companyfacts.zip` and `submissions.zip` and copies only in-scope CIKs into bronze:
   ```
   data/bronze/<dataset>/ingest_date=<SEC snapshot date>/CIK##########.json.gz
   ```
   Bronze is immutable: files are written once, atomically, and never overwritten. The partition is the SEC snapshot date (the zip's `Last-Modified`), not the run date, so rerunning the same snapshot writes 0 files.
3. **Daily incremental.** `make incremental` reads each company's `submissions` (500 requests) and compares its latest 10-K/10-Q-type XBRL filing with a stored high-water mark (`data/ops/ingest_state.json`, seeded from the backfill). Only companies with a newer filing get a fresh `companyfacts` pull. 8-K XBRL is cover-page only, so it never triggers a pull. If SEC's companyfacts hasn't caught up with a filing yet, the mark is not advanced and the company is retried on the next run (up to 3 days). Bronze file names include the accession, so two filings on one day never collide.
4. **Fair access.** Every request carries the `SEC_USER_AGENT` header and goes through a token bucket capped at 8 requests/second (SEC's limit is 10). 403/429/5xx and network errors are retried with exponential backoff and jitter.

## Silver layer: point-in-time history

`finfacts flatten` turns each bronze JSON file into a long parquet file (one row per fact, no logic), so DuckDB now and BigQuery later read identical input. dbt then builds:

- `stg_companyfacts`: one row per fact per filing, financial-statement forms only.
- `int_fact_versions`: **restatement history**. A new version starts only when a later filing reports a *different* value. Each version is valid from the SEC acceptance date of the filing that first reported it.
- `dim_company` (SCD2) and `dim_period`: fiscal year/quarter derived from period dates and the company's fiscal year end, never from SEC's `fy`/`fp` (which describe the filing).

Point-in-time query, "what did we know on 2021-06-01?":

```sql
select value from silver.int_fact_versions
where cik = 19617 and concept = 'Revenues' and period_start = '2019-01-01' and period_end = '2019-12-31'
  and valid_from <= '2021-06-01' and (valid_to is null or valid_to > '2021-06-01');
-- 115,399,000,000 (restated twice: 115.627 bn → 115.399 bn → 115.720 bn)
```

**[docs/silver-layer.md](docs/silver-layer.md)** explains the rules and seven real data quirks the tests caught, e.g. proxy statements whose rounded pay-versus-performance figures look like restatements.

### Measured (2026-10-20, Windows laptop, home broadband)

| | Result |
|---|---|
| Universe | 503 tickers → 500 CIKs, 0 unmatched at SEC |
| Bronze written | 500 companyfacts files (119 MB gz) + 1,373 submissions files (42 MB gz), 0 CIKs missing |
| Full backfill (2.98 GB download + extract) | 3.3 min |
| Backfill rerun, same snapshot | 8 s, 0 files written |
| Flatten (2,373 files → 12.7 M fact rows, 114 MB parquet) | 70 s |
| `dbt build` (9.5 M facts → 5.17 M versions, 37 tests) | ~40 s |
| Incremental, first run after backfill | 500 checked, 6 new 10-Q/10-K, 6 pulled, ~2 min |
| Incremental rerun | 500 checked, 0 pulled |
| Facts restated at least once | 228,594 of 4.92 M (4.6%) |

## Repo layout

```
src/finfacts/      Python package and `finfacts` CLI
  sec/             rate-limited SEC client
  ingest/          universe, bulk backfill, incremental, flatten
dbt/               dbt project: staging -> intermediate (silver) -> marts (gold)
config/            site URL, universe snapshots
docs/              design notes and data-quality findings
scripts/           fixture generation
tests/             pytest (offline) + fixtures (5 real companies, trimmed)
```

## Licences

Code: [MIT](LICENSE). Data sources and their terms: [DATA_LICENSES.md](DATA_LICENSES.md).
