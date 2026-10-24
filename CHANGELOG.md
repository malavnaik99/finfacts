# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.6.0] – 2026-10-24 – Milestone 6: eval set, text-to-SQL baseline, 10-K retrieval

### Added
- Frozen eval snapshot (2026-10-24) with `raw` (SEC XBRL facts) and `semantic` (certified tables) schemas; `finfacts eval-build`.
- Eval set v1: 150 questions (110 templated, 40 hand-written), gold SQL and gold answers; 15/15 sampled answers match SEC's `companyconcept` API.
- `finfacts eval` / `make eval`: text-to-SQL execution accuracy before vs after the semantic layer, `anthropic/claude-haiku-5.5` via OpenRouter: **67.3% → 100.0%** (US$0.21).
- `finfacts text`: Item 1A and Item 7 from 1,067 FY2024+ 10-Ks (edgartools, 4 workers, write-once bronze; 99% of sections extracted).
- `finfacts embed` / `finfacts search`: 87,082 chunks embedded with `BAAI/bge-small-en-v1.5` into LanceDB + parquet; retrieval smoke test 10/10.
- Public Hugging Face dataset [Malavnaik/finfacts](https://huggingface.co/datasets/Malavnaik/finfacts) (CC BY 4.0) with dataset card.
- README results table, architecture diagram and badges; `docs/case-study.md`; `docs/demo-script.md`.

### Changed (approved)
- 10-K chunks are ~350 words (~470 tokens) with 50-word overlap instead of ~800 tokens: the embedding model reads at most 512 tokens, so longer chunks would leave their tails unsearchable.

### Fixed
- The health page is now built as the last job of the daily run; the `workflow_run` trigger could not obtain BigQuery credentials.

## [0.5.0] – 2026-10-24 – Milestone 5: semantic layer and data-health page

### Added
- MetricFlow semantic layer (`dbt/models/semantic/`): 21 certified metrics (17 simple, 3 ratio margins, derived free cash flow) plus quarterly revenue, net income and operating cash flow; time spine; current-company model.
- `scripts/check_semantic_layer.py` / `make semantic-check`: MetricFlow revenue by company and fiscal year must equal plain SQL on gold (5,320 company-years, 0 differences); runs in `make ci` on the fixtures.
- `finfacts record-run` and `ops.run_log`: status, dbt model/test outcomes, queries and bytes billed (from dbt's per-node adapter responses), and data freshness for every daily run, pass or fail (load job, parameterised SQL).
- Evidence data-health page (`health/`) and `pages.yml`: rebuilt after every daily run and deployed to https://malavnaik99.github.io/finfacts/.

### Fixed
- Annual metrics on period end dates would merge two fiscal years in one calendar year for 25 company-years of 52/53-week companies; they now use a fiscal-year time axis (`fiscal_year_date` on `fct_financials_latest`).

## [0.4.0] – 2026-10-21 – Milestone 4: GCP, write-audit-publish, daily schedule

### Added
- Terraform (`infra/terraform`, 26 resources): APIs; append-only GCS bucket (pipeline can create and read, not delete or overwrite); BigQuery `raw`, `audit`, `gold`, `ops`; pipeline service account with Workload Identity Federation limited to this repo's `main` branch; EUR 5/15 budget alerts; 50 GB/day BigQuery query quota as a hard cap.
- `finfacts load-bq`: GCS parquet → BigQuery raw with free load jobs, loading only the newest companyfacts file per company (each holds the full history), so scans stay flat as snapshots accumulate (3.8 GB → 1.9 GB on the largest model).
- `finfacts publish`: copies every audited gold model (from the dbt manifest) from `audit` to `gold`.
- dbt BigQuery target: everything builds in `audit`; contracts use types both engines understand; job labels for cost per run; 5 GB per-query limit.
- `daily.yml`: incremental → flatten → append-only upload → load → dbt build in audit → publish; state saved as new timestamped objects; dbt artifacts kept 30 days.
- WAP drill (`assert_wap_drill`, `--vars '{wap_drill: true}'`): proven on GitHub Actions that a failing test skips publish and leaves gold untouched.
- Predecessor-CIK mapping for 12 re-registered companies (`config/universe/predecessors.csv`), each checked against SEC. ExxonMobil, Disney, Broadcom, Cigna, Linde and others now have history from FY2015.

### Changed (approved)
- Airflow (local Astro DAG) and OpenLineage/Marquez removed from the plan: local-only demos. Lineage comes from `dbt docs`.

### Fixed
- BigQuery dialect issues: a CTE named like a column (`fiscal_year`), an aggregate alias reused in `HAVING`, `REGEXP_EXTRACT` arguments.

## [0.3.1] – 2026-10-21 – Review fixes

### Fixed
- Derived quarters subtracted two different XBRL concepts (e.g. FY `Revenues` minus 9M contract revenue): 909 wrong quarters, 18 with negative revenue. Quarter derivations now require the same concept on both inputs; mismatches stay empty (2,164 derived rows removed, incl. dependent FCF and margins).
- Derivations no longer chain CTEs: each layer is a stored model (`int_metric_l1_quarters` ... `int_metric_values`) and `derive()` handles all rules of a layer in one pass over its input table. The old chain referenced one CTE up to 170 times and would not run on BigQuery. Local build of the chain: 13 s → 3 s.
- Canonical period choice was nondeterministic when two date ranges tied on fact count and end date (4 groups, e.g. Deere FY2016 Q3, whose first-known date flipped by a year between builds). Ties now go to the range reported first.

## [0.3.0] – 2026-10-21 – Milestone 3: concept mapping and gold mart

### Added
- Metric catalogue (21 certified metrics + helpers) and concept map with a priority and rationale for every XBRL concept (`dbt/seeds/`), documented in `docs/concept_mapping.md`.
- `int_canonical_periods`: one date range per company fiscal period (most-facts wins), resolving near-duplicate period ends.
- Point-in-time derivation engine (`derive`, `per_period`, `fill_missing` macros): derived values are re-versioned whenever an input is restated.
- Derivations: Q2/Q3/Q4 from year-to-date figures, net income from ProfitLoss − NCI, bank revenue, gross profit, total liabilities, equity incl. NCI, long-term debt, free cash flow, margins.
- Gold: `fct_financials` (versioned), `fct_financials_latest`, `dim_fiscal_period`, `dim_concept`, all with enforced contracts; `as_of()` macro.
- Quality: `quality.identity_checks` (balance sheet and gross profit), calibrated failure-rate gates, exact FCF identity, ≥ 95% coverage test, and 30 golden values read from 10-K statements and checked as known the day after filing.
- `finfacts query <file.sql>` and `make demo-query` (Apple quarterly revenue FY2015-latest).
- CI fixtures widened to 8 companies and 20 concepts so derivations run in CI; full-data tests are tagged `full_data` and excluded there.

### Changed (approved)
- Identity gates: the plan's 1% failure cap became calibrated gates (balance sheet ≤ 2.5%, gross profit ≤ 6%) set just above measured rates.

### Fixed (found by the new tests)
- Fiscal year ends listed in the first week of a month (J&J `0103`) labelled every year one year late; now normalised to the previous month end.
- Utilities' total revenue ranked below the ASC 606 subset tags (NextEra off by $1.6 bn).
- Companies that never tag `NetIncomeLoss` (e.g. ITW) had no net income; coverage 89.5% → 97.7%.
- Missing temporary-equity concepts made balance sheets fail the identity check (4.1% → 1.96%).
- A tagged "equity incl. NCI" far below parent equity (Agilent: −$305M) is now rejected as a tagging error.

### Known limitation
- 13 companies that re-registered under a successor CIK (e.g. ExxonMobil, Disney, Broadcom, BlackRock) lack history before the reorganisation.

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
