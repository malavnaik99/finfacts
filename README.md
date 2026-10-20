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
| 2. Silver layer and daily incremental | ⏳ next |
| 3. Concept mapping and gold mart | — |
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
```

`make help` lists every target.

## How ingestion works

1. **Universe.** `make universe` snapshots S&P 500 constituents and validates each CIK against SEC's `company_tickers.json`. The result is committed to [`config/universe/`](config/universe/). It is one dated snapshot, so history has survivorship bias. This is a known, documented limitation.
2. **Bulk backfill.** `make backfill-local` downloads SEC's nightly `companyfacts.zip` and `submissions.zip` and copies only in-scope CIKs into bronze:
   ```
   data/bronze/<dataset>/ingest_date=<SEC snapshot date>/CIK##########.json.gz
   ```
   Bronze is immutable: files are written once, atomically, and never overwritten. The partition is the SEC snapshot date (the zip's `Last-Modified`), not the run date, so rerunning the same snapshot writes 0 files.
3. **Fair access.** Every request carries the `SEC_USER_AGENT` header and goes through a token bucket capped at 8 requests/second (SEC's limit is 10). 403/429/5xx and network errors are retried with exponential backoff and jitter.

### Measured (2026-10-20, Windows laptop, home broadband)

| | Result |
|---|---|
| Universe | 503 tickers → 500 CIKs, 0 unmatched at SEC |
| Bronze written | 500 companyfacts files (119 MB gz) + 1,373 submissions files (42 MB gz), 0 CIKs missing |
| Full backfill (2.98 GB download + extract) | 3.3 min |
| Rerun, same snapshot | 8 s, 0 files written |

## Repo layout

```
src/finfacts/      Python package and `finfacts` CLI
  sec/             rate-limited SEC client
  ingest/          universe + bulk backfill
config/            site URL, universe snapshots
tests/             pytest (offline)
```

## Licences

Code: [MIT](LICENSE). Data sources and their terms: [DATA_LICENSES.md](DATA_LICENSES.md).
