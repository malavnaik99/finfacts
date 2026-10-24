# FinFacts

[![ci](https://github.com/malavnaik99/finfacts/actions/workflows/ci.yml/badge.svg)](https://github.com/malavnaik99/finfacts/actions/workflows/ci.yml)
[![daily](https://github.com/malavnaik99/finfacts/actions/workflows/daily.yml/badge.svg)](https://github.com/malavnaik99/finfacts/actions/workflows/daily.yml)
[![health page](https://img.shields.io/badge/data%20health-live-2ea44f)](https://malavnaik99.github.io/finfacts/)
[![dataset](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-Malavnaik%2Ffinfacts-yellow)](https://huggingface.co/datasets/Malavnaik/finfacts)
[![licence](https://img.shields.io/badge/code-MIT-blue)](LICENSE)

**Certified, point-in-time-correct SEC EDGAR fundamentals, so analysts, a text-to-SQL agent and an MCP server all get the same answer.**

Raw SEC XBRL data is hard to query consistently:

- **Tags vary.** "Revenue" is `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` and more, depending on company, year and sector.
- **Figures get restated.** The same period's value changes in later filings.
- **Periods don't line up.** Fiscal years end in different months, Q4 is rarely filed directly, and the `fy`/`fp` fields in `companyfacts` describe the filing, not the fact.

FinFacts turns S&P 500 filings (FY2015 to today) into a tested star schema with a semantic layer on top, runs daily on GCP for about EUR 0 a month, and publishes an eval set and embedded 10-K text for LLM work. Links: **[live health page](https://malavnaik99.github.io/finfacts/)** · **[Hugging Face dataset](https://huggingface.co/datasets/Malavnaik/finfacts)** · **[case study](docs/case-study.md)** · [PLAN.md](PLAN.md)

## Results at a glance

| | Result |
|---|---|
| Coverage | 498 S&P 500 companies, FY2015 to today, 21 certified metrics; revenue, net income and total assets for ≥ 97.7% of company-years |
| Correctness | 30/30 golden values from 10-K statements match *as known the day after filing*; semantic layer = plain SQL for 5,320 company-years |
| Point-in-time | 660k fact versions; 58k restated values kept with SEC acceptance dates |
| Text-to-SQL (150 questions, `anthropic/claude-haiku-5.5`) | **67.3%** on raw XBRL facts → **100.0%** on the FinFacts semantic layer (US$0.21 total) |
| 10-K retrieval | 87,082 chunks of Item 1A and Item 7 from 1,067 FY2024+ 10-Ks; 10/10 smoke-test queries find a relevant chunk in the top 5 |
| Reliability | Daily GitHub Actions run with write-audit-publish; a deliberate failing test left published data untouched |
| Cost | ~9 GB scanned per run (inside BigQuery's free tier), hard cap 50 GB/day, budget alerts at EUR 5/15 |

## Architecture

```mermaid
flowchart LR
  SEC["SEC EDGAR<br/>bulk zips + submissions API<br/>(8 req/s, declared User-Agent)"] --> ING["finfacts CLI<br/>backfill · incremental · flatten"]
  ING --> GCS[("GCS bronze<br/>append-only")]
  GCS -- free load jobs --> RAW[(BigQuery raw)]
  RAW --> DBT["dbt: silver<br/>(restatement history)<br/>→ gold (21 metrics)"]
  DBT --> AUD{"all tests pass<br/>in audit?"}
  AUD -- yes --> GOLD[(BigQuery gold)]
  AUD -- no --> KEEP["gold untouched<br/>+ failure email"]
  GOLD --> SL["MetricFlow<br/>semantic layer"]
  GOLD --> HP["health page<br/>(Evidence, GitHub Pages)"]
  SL --> EV["eval set + text-to-SQL<br/>before/after"]
  ING --> TXT["10-K Item 1A / 7"] --> VEC[("LanceDB + parquet<br/>bge-small embeddings")]
  EV --> HF[("Hugging Face<br/>dataset")]
  VEC --> HF
```

## Status

| Milestone | Status |
|---|---|
| 1. Foundations and bulk ingestion (local) | ✅ done |
| 2. Silver layer and daily incremental | ✅ done |
| 3. Concept mapping and gold mart | ✅ done |
| 4. GCP, write-audit-publish, scheduling | ✅ done |
| 5. Semantic layer and data-health page | ✅ done |
| 6. AI outputs (eval set, 10-K embeddings) | ✅ done |

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
make demo-query               # Apple quarterly revenue FY2015-latest from the gold mart
make ci                       # lint, types, unit tests, dbt build on offline fixtures
```

Cloud (after `gcloud auth application-default login`, with `GCP_PROJECT_ID` and `GCS_BUCKET` in `.env`):

```bash
make load-bq                  # parquet in GCS -> BigQuery raw (free load jobs)
make bq-build                 # build + test everything in the `audit` dataset
make publish                  # copy audited gold tables to `gold`
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

## Gold mart: certified, point-in-time metrics

21 certified metrics (revenue, net income, margins, free cash flow, balance-sheet totals and more) for 498 companies, FY2015 to today.

| Table | Grain |
|---|---|
| `gold.fct_financials` | company × metric × fiscal period × **version** (652k rows) |
| `gold.fct_financials_latest` | current value of each company × metric × fiscal period (view) |
| `gold.dim_concept` | metric definitions and the XBRL concepts each accepts, in priority order |
| `gold.dim_fiscal_period` | fiscal calendar: Q1–Q4, Q2_YTD, Q3_YTD and FY per company and year |
| `gold.dim_company`, `gold.dim_period` | companies (SCD2) and every reported date range |

Every value carries `source_concept` (the XBRL tag or the derivation rule), `accession_number`, `is_derived` and its validity dates. To ask what was known on a date:

```sql
select metric_id, fiscal_year, value
from gold.fct_financials
where cik = 19617 and fiscal_period = 'FY'
  and valid_from <= date '2021-06-01'
  and (valid_to is null or valid_to > date '2021-06-01')
```

Inside dbt models the same filter is `{{ as_of("'2021-06-01'") }}`.

Q4 is almost never filed as a 3-month figure, so FinFacts derives it as FY − 9M. Cash-flow quarters are derived from year-to-date figures. When an input is restated, the derived value gets a new version too. The mapping rules, every decision and its verification are in **[docs/concept_mapping.md](docs/concept_mapping.md)**.

**Verified:** 30/30 golden values read from 10-K statements match FinFacts as known the day after filing. Coverage of revenue, net income and total assets is ≥ 97.7% of company-years. Balance-sheet identity failures are 1.96% (gate 2.5%) and gross-profit identity failures 5.1% (gate 6%). The failures are listed in `quality.identity_checks`.

## Semantic layer: one definition per metric

The 21 certified metrics are defined once in dbt's semantic layer ([`dbt/models/semantic/_semantic.yml`](dbt/models/semantic/_semantic.yml), MetricFlow). Humans, the text-to-SQL agent and the MCP server all ask the same definitions:

```bash
cd dbt && DBT_PROFILES_DIR=. FINFACTS_DUCKDB_PATH=../data/finfacts.duckdb uv run mf query \
  --metrics revenue,net_income,net_margin \
  --group-by company__ticker,metric_time__year \
  --where "{{ Dimension('company__ticker') }} = 'AAPL'"
```

- **Simple metrics** (revenue, net income, total assets …) read the current certified value for the fiscal year. Quarterly variants exist for revenue, net income and operating cash flow.
- **Margins are ratio metrics** (profit ÷ revenue as a ratio of sums), so a sector's margin is weighted by revenue rather than an average of company margins.
- **Free cash flow is a derived metric**: operating cash flow − capex.
- **`metric_time__year` is the fiscal year.** Annual metrics use a fiscal-year time axis. Using period end dates would put two fiscal years into one calendar year for 25 company-years of 52/53-week companies (e.g. J&J 2023).
- **Checked in CI:** `make semantic-check` asserts that MetricFlow's revenue by company and fiscal year equals plain SQL on gold. Result: 5,320 company-years, 0 differences.

## Data-health page

[malavnaik99.github.io/finfacts](https://malavnaik99.github.io/finfacts/) is an [Evidence](https://evidence.dev) site ([`health/`](health/)) rebuilt by [`pages.yml`](.github/workflows/pages.yml) after every daily run, pass or fail. It shows:

- last run status and data freshness (hours since the newest 10-K/10-Q);
- test pass rate and BigQuery cost per run, from `ops.run_log`, which `finfacts record-run` writes after each run using bytes billed per dbt node;
- coverage of core metrics by fiscal year;
- accounting-identity failure rates against their limits;
- recent runs.

Its build-time queries scan a few MB of BigQuery. The page itself is static (no live credentials).

## AI outputs: eval set and 10-K retrieval

**Eval set** ([`eval/v1`](eval/v1/), published on [Hugging Face](https://huggingface.co/datasets/Malavnaik/finfacts)): 150 natural-language questions with gold SQL and gold answers over a frozen snapshot (2026-10-24), so answers stay valid while the pipeline keeps loading new filings.

- 110 templated questions (fixed seed): values, quarters, growth, margins, sector totals, rankings, as-originally-reported, restatement counts.
- 40 hand-written hard ones: Walmart's January fiscal year, J&J's 52/53-week years, bank revenue, ExxonMobil's pre-2025 history under its old CIK, derived Q4s, medians, CAGR, top-N.
- 15 answers (10%) cross-checked against SEC's own `companyconcept` API: 15/15 match ([`verification.csv`](eval/v1/verification.csv)).

**Text-to-SQL before vs after** (`make eval`): the same model, rules and one repair attempt; only the schema differs.

| Condition | Execution accuracy | SQL errors |
|---|---|---|
| Raw SEC XBRL facts (`raw` schema) | 67.3% | 20 |
| FinFacts semantic layer (`semantic` schema + metric definitions) | **100.0%** | 0 |

On raw facts the model scores 0% on derived Q4s, top-N rankings, sector shares and ExxonMobil's pre-2025 revenue, and 10% on sector totals. Caveat: the questions and gold SQL were written against FinFacts' schema, so the eval measures how much the certified layer helps, not a neutral benchmark of XBRL. Per-question SQL and results: [`eval/v1/results`](eval/v1/results/).

**10-K retrieval** (`make text`, `make embed`): Item 1A (Risk Factors) and Item 7 (MD&A) from 1,067 FY2024+ 10-Ks (99% of sections extracted), ~350-word chunks with company, fiscal year, item and accession, embedded with `BAAI/bge-small-en-v1.5` into LanceDB. `uv run finfacts search "Medicare Advantage medical cost trends"` returns the top chunks; [`scripts/retrieval_smoke_test.py`](scripts/retrieval_smoke_test.py) checks 10 questions: 10/10 find a chunk from a relevant company in the top 5 (a smoke test, not a ranking benchmark: for two queries the best match is at rank 2–4).

## Production: daily run on GCP with write-audit-publish

Every morning (06:30 UTC) a GitHub Actions workflow ([`daily.yml`](.github/workflows/daily.yml)) runs the same `finfacts` CLI and dbt project as your laptop:

```
SEC submissions ─► incremental load ─► flatten ─► GCS (append-only)
                                                     │  load jobs (free)
                                                     ▼
                         BigQuery raw ─► dbt build + every test in `audit`
                                                     │  only if ALL tests pass
                                                     ▼
                                     finfacts publish: copy tables to `gold`
```

- **Write-audit-publish.** Nothing reaches `gold` unless the whole build and all its tests pass in `audit`. A failed run stops before `publish`, GitHub emails the failure, and `gold` keeps its last good version. A built-in drill proves it: run the workflow with `wap_drill: true` and one test fails on purpose. Verified on 2026-10-21: publish was skipped and `gold.fct_financials` kept its timestamp.
- **No keys anywhere.** GitHub Actions signs in with Workload Identity Federation, limited to this repository's `main` branch.
- **Append-only storage.** The pipeline's service account can create and read objects in the bucket but not delete or overwrite them, so bronze is immutable by IAM, not just by convention. Even the incremental-load state is saved as a new timestamped object each run.
- **Cost guards.** Budget alerts at EUR 5 and EUR 15, a 5 GB limit per query, and a **hard daily cap of 50 GB scanned** per project (BigQuery refuses further queries that day).
- **Infrastructure as code.** Everything above is in [`infra/terraform`](infra/terraform/): 26 resources.

| Measured (2026-10-21) | Result |
|---|---|
| Daily run, end to end | ~4 min |
| BigQuery scanned per run | 9.0 GB (79 queries) → ~270 GB/month, inside the 1 TB free tier |
| Cost | EUR 0 so far (free tier) |

The plan's target of < 2 GB per run needs incremental dbt models; today every model is rebuilt daily.

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
| Full `dbt build` incl. gold (65 models/tests) | ~35 s |

## Repo layout

```
src/finfacts/      Python package and `finfacts` CLI
  sec/             rate-limited SEC client
  ingest/          universe, bulk backfill, incremental, flatten
dbt/               dbt project: staging -> intermediate (silver) -> marts (gold) -> quality
infra/terraform/   GCP: bucket, datasets, service account, Workload Identity, budget, quota
health/            Evidence data-health page (GitHub Pages)
  seeds/           metric catalogue, concept map, golden values
queries/           example SQL (`finfacts query <file>`)
config/            site URL, universe snapshots
docs/              design notes, data-quality findings, case study, demo script
eval/              eval set v1: questions, hand-written YAML, verification, results
scripts/           fixture generation
tests/             pytest (offline) + fixtures (5 real companies, trimmed)
```

## Licences

Code: [MIT](LICENSE). Data sources and their terms: [DATA_LICENSES.md](DATA_LICENSES.md).
